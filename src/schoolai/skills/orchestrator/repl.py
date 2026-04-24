"""Python REPL restringido para el Bot Agente.

El LLM puede escribir código Python con acceso de solo lectura a la DB:
  - await query(sql)  → list[dict]  (solo SELECT / WITH)
  - today             → date de hoy
  - now               → datetime de ahora
  - print(...)        → capturado en el output

Restricciones de seguridad:
  - __builtins__ reducido a un whitelist explícito
  - import restringido: solo datetime, math, collections, re, json, decimal
  - No hay acceso a open(), exec(), eval(), __import__ libre, os, sys, subprocess
  - El código del LLM se envuelve en async def para permitir await query(...)
  - Timeout configurable (default 5s) via asyncio.wait_for
"""

from __future__ import annotations

import asyncio
import builtins
import io
import re
import resource
import textwrap
from datetime import date, datetime
from typing import Any

from loguru import logger

# ── Helpers de builtins seguros ───────────────────────────────────────────────

_MAX_POW_EXPONENT = 10_000
_MAX_STR_LEN = 50_000
_MAX_MEMORY_BYTES = 256 * 1024 * 1024  # 256 MB


def _safe_pow(base: Any, exp: Any, mod: Any = None) -> Any:
    """pow() que rechaza exponentes enormes para prevenir agotamiento de CPU."""
    if isinstance(exp, int) and abs(exp) > _MAX_POW_EXPONENT:
        raise ValueError(f"exponente {exp} excede el límite de {_MAX_POW_EXPONENT}")
    return builtins.pow(base, exp, mod)


def _safe_repr(obj: Any) -> str:
    """repr() con límite de longitud para prevenir agotamiento de memoria."""
    s = builtins.repr(obj)
    if len(s) > _MAX_STR_LEN:
        return s[:_MAX_STR_LEN] + f"... (truncado, {len(s)} chars)"
    return s


def _safe_format(value: Any, fmt: str = "") -> str:
    """format() con límite de longitud."""
    s = builtins.format(value, fmt)
    if len(s) > _MAX_STR_LEN:
        return s[:_MAX_STR_LEN] + "... (truncado)"
    return s


# ── Builtins permitidos ────────────────────────────────────────────────────────

_SAFE_BUILTINS: dict[str, Any] = {
    "abs": abs,
    "all": all,
    "any": any,
    "bin": bin,
    "bool": bool,
    "chr": chr,
    "dict": dict,
    "divmod": divmod,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "format": _safe_format,
    "frozenset": frozenset,
    # getattr / hasattr / type / isinstance / issubclass EXCLUIDOS intencionalmente:
    # permiten sandbox escape via __class__.__bases__[0].__subclasses__()
    "hash": hash,
    "hex": hex,
    "int": int,
    "iter": iter,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "next": next,
    "oct": oct,
    "ord": ord,
    "pow": _safe_pow,
    "range": range,
    "repr": _safe_repr,
    "reversed": reversed,
    "round": round,
    "set": set,
    "slice": slice,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
    "True": True,
    "False": False,
    "None": None,
    # Excepciones comunes
    "Exception": Exception,
    "ValueError": ValueError,
    "KeyError": KeyError,
    "IndexError": IndexError,
    "TypeError": TypeError,
    "AttributeError": AttributeError,
    "StopIteration": StopIteration,
}

_ALLOWED_MODULES = frozenset({"datetime", "math", "collections", "re", "json", "decimal"})

# Tablas que el REPL puede consultar — las demás contienen datos sensibles
_ALLOWED_TABLES = frozenset(
    {
        "people",
        "students",
        "grades",
        "subjects",
        "attendance",
        "homework",
        "homework_submissions",
        "actividades",
        "actividad_participantes",
        "actividad_pagos",
    }
)


def _check_tables(sql: str) -> None:
    """Verifica que solo se referencien tablas permitidas en la consulta."""
    # Strip SQL comments before analysis
    cleaned = re.sub(r"--[^\n]*", "", sql)
    cleaned = re.sub(r"/\*.*?\*/", "", cleaned, flags=re.DOTALL)

    # Extract CTE names defined in WITH clause to exclude them
    cte_names = set(
        m.group(1).lower()
        for m in re.finditer(
            r"\b(\w+)\s*\bas\b\s*\(",
            cleaned,
            re.IGNORECASE,
        )
    )

    # Extract table identifiers after FROM, JOIN, INTO, UPDATE
    found = re.findall(
        r"(?:FROM|JOIN|INTO|UPDATE)\s+([a-zA-Z_][a-zA-Z0-9_]*)",
        cleaned,
        re.IGNORECASE,
    )
    for table in found:
        tlower = table.lower()
        if tlower in cte_names:
            continue
        if tlower not in _ALLOWED_TABLES:
            raise PermissionError(f"REPL: tabla '{table}' no permitida")


def _safe_import(name: str, *args: Any, **kwargs: Any) -> Any:
    """__import__ restringido — solo módulos de _ALLOWED_MODULES."""
    top = name.split(".")[0]
    if top not in _ALLOWED_MODULES:
        raise ImportError(f"Import '{name}' no permitido en el REPL")
    return builtins.__import__(name, *args, **kwargs)


# ── Motor de ejecución ─────────────────────────────────────────────────────────


async def _exec_code(code: str) -> str:
    """Ejecuta el código en un entorno restringido y devuelve el output."""
    output_buf = io.StringIO()

    def _print(*args: Any, **kwargs: Any) -> None:
        """print() con auto-serialización JSON para listas y dicts."""
        import json as _json

        formatted = []
        for a in args:
            if isinstance(a, (list, dict)):
                formatted.append(_json.dumps(a, ensure_ascii=False, default=str))
            else:
                formatted.append(str(a))
        kwargs["file"] = output_buf
        builtins.print(*formatted, **kwargs)

    # Guarda el último resultado de query() — fallback si el LLM no llama print()
    _last_query: list[dict] = []

    async def _query(sql: str, params: dict | None = None) -> list[dict]:
        """Ejecuta una consulta SELECT y devuelve lista de dicts.

        Args:
            sql:    Sentencia SELECT o WITH. Cualquier otra sentencia lanza PermissionError.
            params: Parámetros bind opcionales, e.g. {"grade_id": 3}.

        Returns:
            list[dict] — cada fila como diccionario columna→valor.
        """
        from sqlalchemy import text as sa_text

        from schoolai.db.connection import get_db_session

        upper = sql.strip().upper()
        if not (upper.startswith("SELECT") or upper.startswith("WITH")):
            raise PermissionError("REPL: solo se permiten consultas SELECT/WITH")
        _check_tables(sql)

        async with get_db_session() as session:
            result = await session.execute(sa_text(sql), params or {})
            cols = list(result.keys())
            rows = [dict(zip(cols, row)) for row in result.fetchall()]

        _last_query.clear()
        _last_query.extend(rows)
        return rows

    safe_globals: dict[str, Any] = {
        **_SAFE_BUILTINS,
        "__builtins__": {**_SAFE_BUILTINS, "__import__": _safe_import},
        "__import__": _safe_import,
        "print": _print,
        "query": _query,
        "today": date.today(),  # noqa: DTZ011
        "now": datetime.now(),  # noqa: DTZ005
    }

    # Envolver el código en async def para que el LLM pueda usar await
    dedented = textwrap.dedent(code)
    indented = textwrap.indent(dedented, "    ")
    wrapped = f"async def __main__():\n{indented}\n"

    try:
        # Limitar memoria del proceso hijo para prevenir agotamiento
        soft, hard = resource.getrlimit(resource.RLIMIT_AS)
        resource.setrlimit(resource.RLIMIT_AS, (_MAX_MEMORY_BYTES, hard))
        try:
            exec(compile(wrapped, "<repl>", "exec"), safe_globals)  # noqa: S102
        finally:
            resource.setrlimit(resource.RLIMIT_AS, (soft, hard))
    except SyntaxError as e:
        return f"SyntaxError: {e}"

    try:
        await safe_globals["__main__"]()
    except PermissionError as e:
        return f"Permiso denegado: {e}"
    except Exception as e:  # noqa: BLE001
        return f"Error: {type(e).__name__}: {e}"

    output = output_buf.getvalue().strip()

    # Fallback: si el LLM generó `await query(...)` sin print(), devolver el último resultado
    if not output and _last_query:
        import json as _json

        output = _json.dumps(_last_query, ensure_ascii=False, default=str)

    return output or "(sin output)"


async def run_repl(code: str, timeout: float = 5.0) -> str:
    """Entry point público: ejecuta el REPL con timeout.

    Args:
        code:    Código Python a ejecutar.
        timeout: Segundos máximos de ejecución (default 5).

    Returns:
        String con el output capturado o mensaje de error.
    """
    logger.debug(f"[repl] ejecutando ({len(code)} chars)")
    try:
        result = await asyncio.wait_for(_exec_code(code), timeout=timeout)
        logger.debug(f"[repl] output: {result[:200]!r}")
        return result
    except asyncio.TimeoutError:
        logger.warning("[repl] timeout excedido")
        return f"Error: timeout ({timeout:.0f}s excedido)"
    except Exception as e:  # noqa: BLE001
        logger.error(f"[repl] error inesperado: {e}")
        return f"Error interno: {e}"
