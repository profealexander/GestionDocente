"""Extracción de contenido para documentos de contexto.

Estrategia única: Gemini lee cualquier archivo (PDF, Excel, Word, imágenes)
como dato inline base64. Para URLs se obtiene el texto con httpx.

Formatos soportados por Gemini vía inline base64:
  - Imágenes: image/jpeg, image/png, image/webp, image/gif
  - PDF: application/pdf
  - Excel: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
  - Word: application/vnd.openxmlformats-officedocument.wordprocessingml.document
  - Texto plano, CSV, Markdown, código fuente
"""

from __future__ import annotations

import asyncio
import base64
import re
from html.parser import HTMLParser


# ── Texto plano ────────────────────────────────────────────────────────────────

async def extract_from_text(text: str) -> str:
    return text.strip()


# ── Archivo → Gemini multimodal ────────────────────────────────────────────────

_FILE_PROMPT = (
    "Extrae y transcribe TODO el contenido de este archivo de forma precisa y completa. "
    "Si contiene tablas, horarios, calendarios o formularios, conserva la estructura "
    "usando texto plano con columnas separadas por '|' o guiones. "
    "Si contiene listas, mantenlas con viñetas. "
    "Devuelve únicamente el contenido extraído, sin comentarios ni explicaciones."
)


async def extract_from_file(file_bytes: bytes, mime_type: str) -> str:
    """Envía cualquier archivo a Gemini para extracción de texto."""
    from schoolai.config import settings
    from schoolai.skills.llm.client import get_client

    if not settings.google_api_key:
        return ""

    b64 = base64.b64encode(file_bytes).decode()
    client = get_client("google", timeout=60.0)

    def _call():
        return client.chat.completions.create(
            model="gemini-2.5-flash-lite",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{b64}"},
                        },
                        {"type": "text", "text": _FILE_PROMPT},
                    ],
                },
            ],
            temperature=0,
        )

    response = await asyncio.to_thread(_call)
    return (response.choices[0].message.content or "").strip()


# ── URL → httpx + limpieza HTML ────────────────────────────────────────────────

class _HTMLStripper(HTMLParser):
    """Parser mínimo que extrae texto visible de HTML."""

    _SKIP_TAGS = {"script", "style", "head", "nav", "footer", "aside", "noscript"}

    def __init__(self):
        super().__init__()
        self._text: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self._SKIP_TAGS:
            self._skip += 1

    def handle_endtag(self, tag):
        if tag.lower() in self._SKIP_TAGS and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip:
            stripped = data.strip()
            if stripped:
                self._text.append(stripped)

    def get_text(self) -> str:
        return "\n".join(self._text)


async def extract_from_url(url: str) -> str:
    """Descarga una página web y extrae su texto visible."""
    import httpx

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; SchoolAI/1.0; +https://schoolai.app)"
        ),
    }
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()

    content_type = response.headers.get("content-type", "")

    if "text/html" in content_type:
        parser = _HTMLStripper()
        parser.feed(response.text)
        raw = parser.get_text()
        # Colapsar líneas en blanco múltiples
        text = re.sub(r"\n{3,}", "\n\n", raw).strip()
        return text

    if "text/" in content_type or "json" in content_type:
        return response.text.strip()

    # Archivo binario (PDF, Excel, etc.) → delegar a Gemini
    mime = content_type.split(";")[0].strip() or "application/octet-stream"
    return await extract_from_file(response.content, mime)
