"""Parse a list of names (one per line) into structured dicts.

Supports:
- Optional numbering prefix: "1.", "1)", "-", "•", "*"
- Cédula ecuatoriana (10 digits) anywhere in the line
- 1–5+ word names → first_name, middle_name, last_name, second_last_name
"""

import re

# Ecuador cédula: exactly 10 digits
CEDULA_RE = re.compile(r"\b(\d{10})\b")
# Leading numbering / bullet prefix
PREFIX_RE = re.compile(r"^\s*\d+[.)]\s*|^[-•*]\s*")


def parse_line(line: str) -> dict | None:
    """Parse a single line into a name dict. Returns None for blank lines."""
    line = PREFIX_RE.sub("", line).strip()
    if not line:
        return None

    cedula_match = CEDULA_RE.search(line)
    national_id = cedula_match.group(1) if cedula_match else None
    name_part = CEDULA_RE.sub("", line).strip() if cedula_match else line

    parts = name_part.split()
    if not parts:
        return None

    result: dict = {"national_id": national_id}

    match len(parts):
        case 1:
            result |= {"first_name": parts[0]}
        case 2:
            result |= {"first_name": parts[0], "last_name": parts[1]}
        case 3:
            # In Ecuador: nombre apellido1 apellido2 is most common in school lists
            result |= {
                "first_name": parts[0],
                "last_name": parts[1],
                "second_last_name": parts[2],
            }
        case 4:
            result |= {
                "first_name": parts[0],
                "middle_name": parts[1],
                "last_name": parts[2],
                "second_last_name": parts[3],
            }
        case _:
            # 5+ words: first two = first names, last two = last names
            result |= {
                "first_name": parts[0],
                "middle_name": " ".join(parts[1:-2]),
                "last_name": parts[-2],
                "second_last_name": parts[-1],
            }

    return result


def parse_list(text: str) -> list[dict]:
    """Parse a multiline string into a list of name dicts."""
    results = []
    for line in text.splitlines():
        parsed = parse_line(line)
        if parsed:
            results.append(parsed)
    return results


def format_name(parsed: dict) -> str:
    """Return a display string for a parsed name dict."""
    parts = [
        parsed.get("first_name", ""),
        parsed.get("middle_name", ""),
        parsed.get("last_name", ""),
        parsed.get("second_last_name", ""),
    ]
    name = " ".join(p for p in parts if p)
    if parsed.get("national_id"):
        name += f" [{parsed['national_id']}]"
    return name
