"""Utilidades de texto compartidas entre skills."""

import unicodedata
from functools import lru_cache


@lru_cache(maxsize=4096)
def normalize(text: str) -> str:
    """NFKD + mayúsculas + sin acentos. Cache LRU: los nombres/keywords se repiten."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", text.upper()) if not unicodedata.combining(c)
    )
