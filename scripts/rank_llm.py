"""
SchoolAI LLM Ranking — Multi-criteria scorer sobre benchmark JSONs existentes.

Roles alineados con el Agent Runtime de schoolai2 (config.py):

  classifier  → llm_router     (gateway/router.py — classify intent+domain en cada mensaje)
                                JSON: {domain, intent, entities} — response_format=json_object
  planner     → llm_orchestrator (agent/planner.py — genera plan [{tool, params}])
                                JSON array — response_format=json_object, NO tool_choice=auto
  synthesizer → llm_router     (agent/synthesizer.py — respuesta final en español al docente)
                                Conversacional, sin JSON

Nota: llm_router sirve dos funciones distintas (classifier + synthesizer).
      llm_chat y llm_orchestrator nativo (tool_choice=auto) no se usan en schoolai2.

Pesos (classifier):
  score = json_noex  × 0.28   (clasifica sin schema explícito → criterio #1)
        + json_full  × 0.22   (fiabilidad parse JSON completo)
        + costo      × 0.20   (cada mensaje = mayor volumen)
        + latencia   × 0.12   (suma a la latencia de cada respuesta)
        + disponib   × 0.10
        + ttft       × 0.05   (no streaming en classify)
        + español    × 0.03   (output es JSON, no texto)

Pesos (planner):
  score = json_full  × 0.35   (plan incorrecto = ejecución incorrecta → criterio #1)
        + json_noex  × 0.22   (flexibilidad sin schema estricto)
        + disponib   × 0.15   (no puede fallar a mitad de respuesta)
        + costo      × 0.12
        + ttft       × 0.08
        + latencia   × 0.06
        + español    × 0.02   (output es JSON, no texto)

Pesos (synthesizer):
  score = español    × 0.35   (genera el texto que lee el docente → criterio #1)
        + ttft       × 0.25   (docente esperando → velocidad percibida → criterio #2)
        + latencia   × 0.18
        + costo      × 0.12
        + disponib   × 0.08
        + json_full  × 0.01   (no aplica — respuesta conversacional)
        + json_noex  × 0.01

Tests cubiertos por criterio:
  json_full  → *_json, *_nat (native tool calling), TOON sin sufijo (ej: att_absent)
  json_noex  → *_json_noex, *_noex (TOON sin ejemplo de formato)
  latencia   → simple, format, multilang, spanish_input (avg total_ms)
  ttft       → idem (avg TTFT)
  español    → spanish_input (ok/fail)
  disponib   → % tests no-skipped que terminaron ok

No añade tests nuevos — trabaja 100% sobre los JSONs de benchmark existentes.

Uso:
    uv run python scripts/rank_llm.py
    uv run python scripts/rank_llm.py --json scripts/benchmark-*.json
    uv run python scripts/rank_llm.py --role classifier
    uv run python scripts/rank_llm.py --role planner
    uv run python scripts/rank_llm.py --role synthesizer
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

# ── Tier de costo por proveedor ───────────────────────────────────────────────
# 1.0 = free tier confirmado
# 0.80 = low cost (<$0.50/1M tok) o acceso freemium con key gratuita
# 0.55 = paid moderado ($0.5-5/1M tok)
# 0.30 = paid premium o sin info de precio
COST_TIER: dict[str, float] = {
    "HuggingFace":   1.00,  # nscale / cerebras / sambanova — gratis con HF_TOKEN
    "Google":        1.00,  # AI Studio free tier
    "Groq":          1.00,  # free tier (rate limited, modelos rotativos)
    "Kilo AI":       1.00,  # :free models confirmados
    "Ollama Cloud":  1.00,  # ollama.com cloud inference gratuito
    "Ollama":        1.00,  # local
    "OpenRouter":    0.85,  # mix: :free existen pero no todos; algunos paid
    "MuleRouter":    0.80,  # OpenAI-compat, key gratuita en prueba; precio por definir
    "Mistral":       0.55,  # mistral-small ~$0.10, medium ~$0.40, large ~$2/1M
    "DeepSeek":      0.55,  # chat $0.28, reasoner $0.55/1M
    "NVIDIA":        0.55,  # NIM — free tier limitado, luego $0.40/1M
    "Z.AI":          0.55,  # ZAI / GLM — precios similares a DeepSeek
    "ZhipuAI":       0.40,  # legacy China endpoint
    "MiniMax":       0.40,  # sin saldo disponible actualmente
    "Moonshot":      0.30,  # key inválida actualmente
}

# Mezcla de roles para ranking global (distribución de tráfico en schoolai2)
# classifier se llama en cada mensaje; planner y synthesizer en cada respuesta del agente
GLOBAL_MIX = {"classifier": 0.40, "planner": 0.35, "synthesizer": 0.25}

# ── Pesos por rol ────────────────────────────────────────────────────────────
WEIGHTS: dict[str, dict[str, float]] = {
    "classifier": {
        # gateway/router.py — classify {domain, intent, entities} en cada mensaje
        "costo":     0.20,  # mayor volumen → costo importa
        "json_noex": 0.28,  # clasifica sin schema explícito → criterio #1
        "json_full": 0.22,  # fiabilidad parse JSON completo
        "latencia":  0.12,  # suma a la latencia de toda respuesta
        "ttft":      0.05,  # no streaming en classify
        "español":   0.03,  # output es JSON, no texto
        "disponib":  0.10,
    },
    "planner": {
        # agent/planner.py — genera [{tool, params}] con response_format=json_object
        # plan incorrecto = ejecución incorrecta; no usa tool_choice=auto
        "costo":     0.12,
        "json_noex": 0.22,  # flexibilidad sin schema estricto
        "json_full": 0.35,  # fiabilidad del plan → criterio #1
        "latencia":  0.06,
        "ttft":      0.08,
        "español":   0.02,  # output es JSON, no texto
        "disponib":  0.15,  # no puede fallar a mitad de respuesta
    },
    "synthesizer": {
        # agent/synthesizer.py — respuesta final en español al docente
        # llm_router también sirve este rol en la arquitectura actual
        "costo":     0.12,
        "json_noex": 0.01,  # no aplica — respuesta conversacional
        "json_full": 0.01,  # no aplica
        "latencia":  0.18,
        "ttft":      0.25,  # docente esperando → velocidad percibida → criterio #2
        "español":   0.35,  # genera el texto que lee el docente → criterio #1
        "disponib":  0.08,
    },
}

LATENCY_TESTS = {"simple", "format", "multilang", "spanish_input"}
SPANISH_TEST  = "spanish_input"

# json_full: tests que requieren JSON correcto y completo.
#   *_json       — JSON text tests con ejemplo de formato
#   *_nat        — native OpenAI tool calling
#   pln_*        — planner [{tool,params}] tests (schoolai2 agent/planner.py)
#   TOON sin sufijo (ej: att_absent) — catch-all, excluye latencia y compound.
# El filtro toon_valid is not None excluye tests de latencia automáticamente.
JSON_FULL_SFXS = lambda t: (
    (t.endswith("_json") and not t.endswith("_noex"))       # JSON text tests
    or t.endswith("_nat")                                    # native OpenAI tool calling
    or t.startswith("pln_")                                  # planner JSON plan tests
    or (not t.endswith(("_json", "_noex", "_nat"))
        and not t.startswith("pln_")
        and t not in LATENCY_TESTS)                         # TOON full (sin sufijo)
)

# json_noex: tests sin ejemplo de formato — *_json_noex, *_noex (TOON noex)
JSON_NOEX_SFXS = lambda t: (
    t.endswith("_json_noex")
    or (t.endswith("_noex") and not t.endswith("_json_noex"))
)


def load_results(paths: list[Path]) -> list[dict]:
    results = []
    for p in paths:
        data = json.loads(p.read_text())
        results.extend(data["results"])
    return results


def _avg(vals: list[float]) -> Optional[float]:
    return sum(vals) / len(vals) if vals else None


def score_models(results: list[dict], role: str) -> list[dict]:
    w = WEIGHTS[role]

    # ── Agrupar por model_name ────────────────────────────────────────────────
    by_name: dict[str, list[dict]] = {}
    for r in results:
        by_name.setdefault(r["model_name"], []).append(r)

    records = []
    for name, rows in by_name.items():
        provider = rows[0]["provider"]
        pool     = rows[0]["pool"]
        role_tag = rows[0]["role"]

        # ── Latencia: avg total_ms en tests latencia con status ok ────────────
        lat_vals  = [r["total_ms"] for r in rows
                     if r["test_id"] in LATENCY_TESTS and r["status"] == "ok"]
        ttft_vals = [r["ttft_ms"] for r in rows
                     if r["test_id"] in LATENCY_TESTS and r["status"] == "ok"
                     and r["ttft_ms"] is not None]

        lat_avg  = _avg(lat_vals)
        ttft_avg = _avg(ttft_vals)

        # ── JSON-full score ───────────────────────────────────────────────────
        jf_rows = [r for r in rows if JSON_FULL_SFXS(r["test_id"])
                   and r["status"] != "skipped" and r.get("toon_valid") is not None]
        jf_score = _avg([1.0 if r.get("correct_tool") else 0.0 for r in jf_rows])

        # ── JSON-noex score ───────────────────────────────────────────────────
        jn_rows = [r for r in rows if JSON_NOEX_SFXS(r["test_id"])
                   and r["status"] != "skipped" and r.get("toon_valid") is not None]
        jn_score = _avg([1.0 if r.get("correct_tool") else 0.0 for r in jn_rows])

        # ── Español: ok en spanish_input ──────────────────────────────────────
        sp_rows = [r for r in rows if r["test_id"] == SPANISH_TEST]
        sp_score: Optional[float] = None
        if sp_rows:
            best = next((r for r in sp_rows if r["status"] == "ok"), None)
            sp_score = 1.0 if best else 0.0

        # ── Disponibilidad: % ok sobre no-skipped ─────────────────────────────
        non_skip = [r for r in rows if r["status"] != "skipped"]
        avail_score = _avg([1.0 if r["status"] == "ok" else 0.0 for r in non_skip])

        # ── Costo ─────────────────────────────────────────────────────────────
        cost = COST_TIER.get(provider, 0.50)

        records.append({
            "name":     name,
            "provider": provider,
            "pool":     pool,
            "role_tag": role_tag,
            "lat_avg":  lat_avg,
            "ttft_avg": ttft_avg,
            "jf_score": jf_score,
            "jn_score": jn_score,
            "sp_score": sp_score,
            "avail":    avail_score,
            "cost":     cost,
        })

    # ── Normalizar latencia y TTFT (invertir — menor es mejor) ───────────────
    lat_vals_all  = [r["lat_avg"]  for r in records if r["lat_avg"]  is not None]
    ttft_vals_all = [r["ttft_avg"] for r in records if r["ttft_avg"] is not None]
    max_lat  = max(lat_vals_all,  default=1)
    max_ttft = max(ttft_vals_all, default=1)

    # ── Calcular score final ──────────────────────────────────────────────────
    for r in records:
        lat_norm  = (1 - r["lat_avg"]  / max_lat)  if r["lat_avg"]  is not None else 0.0
        ttft_norm = (1 - r["ttft_avg"] / max_ttft) if r["ttft_avg"] is not None else 0.0
        jf  = r["jf_score"]  if r["jf_score"]  is not None else 0.0
        jn  = r["jn_score"]  if r["jn_score"]  is not None else 0.0
        sp  = r["sp_score"]  if r["sp_score"]  is not None else 0.5  # sin dato → neutral
        av  = r["avail"]     if r["avail"]      is not None else 0.5
        co  = r["cost"]

        r["score"] = (
            co       * w["costo"]
            + jn     * w["json_noex"]
            + lat_norm * w["latencia"]
            + ttft_norm * w["ttft"]
            + jf     * w["json_full"]
            + sp     * w["español"]
            + av     * w["disponib"]
        )

    # Para roles JSON (classifier/planner) excluir modelos que no corrieron JSON tests.
    # Para synthesizer los scores JSON son None por diseño — no filtrar.
    _json_roles = {"classifier", "planner", "extractor", "orchestrator"}
    if role in _json_roles:
        records = [r for r in records if r["jf_score"] is not None or r["jn_score"] is not None]

    records.sort(key=lambda r: -r["score"])
    return records


def fmt(val: Optional[float], pct: bool = True, dec: int = 0) -> str:
    if val is None:
        return "—"
    if pct:
        return f"{val * 100:.{dec}f}%"
    return f"{val:.{dec}f}"


def print_ranking(records: list[dict], role: str, w: dict) -> None:
    print(f"\n{'═'*110}")
    print(f"  RANKING SCHOOLAI — rol: {role.upper()}")
    print(f"  Pesos: costo {w['costo']*100:.0f}% · JSON-noex {w['json_noex']*100:.0f}% · "
          f"lat {w['latencia']*100:.0f}% · TTFT {w['ttft']*100:.0f}% · "
          f"JSON-full {w['json_full']*100:.0f}% · español {w['español']*100:.0f}% · "
          f"disponib {w['disponib']*100:.0f}%")
    print(f"{'═'*110}")
    hdr = (f"  {'#':>3}  {'Modelo':<36} {'Proveedor':<14} "
           f"{'Costo':>6} {'JSON%':>6} {'noex%':>6} "
           f"{'Lat':>7} {'TTFT':>6} {'ES':>4} {'Disp':>5} {'Score':>7}  Bar")
    print(hdr)
    print(f"  {'─'*107}")

    for i, r in enumerate(records, 1):
        bar  = "█" * int(r["score"] * 20)
        lat  = f"{r['lat_avg']:.0f}ms"  if r["lat_avg"]  is not None else "—"
        ttft = f"{r['ttft_avg']:.0f}ms" if r["ttft_avg"] is not None else "—"
        cost_tier = {1.0: "free", 0.85: "free~", 0.80: "low$", 0.75: "low$",
                     0.55: "paid", 0.50: "paid", 0.40: "paid+", 0.30: "paid+"}.get(r["cost"], f"{r['cost']:.2f}")
        print(
            f"  {i:>3}. {r['name']:<36} {r['provider']:<14} "
            f"{cost_tier:>6} {fmt(r['jf_score']):>6} {fmt(r['jn_score']):>6} "
            f"{lat:>7} {ttft:>6} {fmt(r['sp_score'], dec=0):>4} {fmt(r['avail'], dec=0):>5} "
            f"{r['score']*100:>6.1f}%  {bar}"
        )

    # ── Destacados por criterio ───────────────────────────────────────────────
    print(f"\n  Destacados:")
    best_cost  = min(records, key=lambda r: -r["cost"])
    best_noex  = max((r for r in records if r["jn_score"] is not None), key=lambda r: (r["jn_score"], -(r["lat_avg"] or 0)))
    best_lat   = min((r for r in records if r["lat_avg"] is not None), key=lambda r: r["lat_avg"])
    best_ttft  = min((r for r in records if r["ttft_avg"] is not None), key=lambda r: r["ttft_avg"])
    print(f"  + Mejor costo:      #{records.index(best_cost)+1:>2} {best_cost['name']} ({best_cost['provider']})")
    print(f"  + Mejor noex:       #{records.index(best_noex)+1:>2} {best_noex['name']} — {fmt(best_noex['jn_score'])}")
    print(f"  + Menor latencia:   #{records.index(best_lat)+1:>2} {best_lat['name']} — {best_lat['lat_avg']:.0f}ms")
    print(f"  + Menor TTFT:       #{records.index(best_ttft)+1:>2} {best_ttft['name']} — {best_ttft['ttft_avg']:.0f}ms")


def main() -> None:
    parser = argparse.ArgumentParser(description="SchoolAI LLM Multi-criteria Ranking")
    parser.add_argument("--json", nargs="+", help="Benchmark JSON files (default: last 2)")
    parser.add_argument(
        "--role", default="global",
        choices=list(WEIGHTS.keys()) + ["global"],
        help="Rol a evaluar: classifier | planner | synthesizer | global (default: global)",
    )
    args = parser.parse_args()

    scripts_dir = Path(__file__).parent
    if args.json:
        paths = [Path(p) for p in args.json]
    else:
        # Últimos 2 JSONs por fecha
        paths = sorted(scripts_dir.glob("benchmark-schoolai-*.json"))[-2:]

    print(f"  Cargando {len(paths)} archivo(s):")
    for p in paths:
        print(f"    · {p.name}")

    results = load_results(paths)
    print(f"  Total resultados: {len(results)}")

    if args.role == "global":
        # Calcula score por rol, luego pondera por GLOBAL_MIX
        per_role: dict[str, dict[str, float]] = {}
        for role, weight in GLOBAL_MIX.items():
            for r in score_models(results, role):
                per_role.setdefault(r["name"], {"_meta": r, "_score": 0.0})
                per_role[r["name"]]["_score"] += r["score"] * weight

        global_records = []
        for name, d in per_role.items():
            rec = dict(d["_meta"])
            rec["score"] = d["_score"]
            global_records.append(rec)
        global_records.sort(key=lambda r: -r["score"])

        # Peso efectivo combinado para el header
        eff_w = {k: sum(WEIGHTS[r][k] * w for r, w in GLOBAL_MIX.items()) for k in WEIGHTS["classifier"]}
        print_ranking(global_records, "GLOBAL (classifier×40% + planner×35% + synthesizer×25%)", eff_w)
    else:
        records = score_models(results, args.role)
        print_ranking(records, args.role, WEIGHTS[args.role])


if __name__ == "__main__":
    main()
