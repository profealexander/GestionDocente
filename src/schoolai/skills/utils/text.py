"""Utilidades de texto compartidas entre skills."""
import unicodedata


def normalize(text: str) -> str:
    """NFKD + mayúsculas + sin acentos."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", text.upper())
        if not unicodedata.combining(c)
    )
