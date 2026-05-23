from __future__ import annotations
import re
from openpyxl.formula.translate import Tokenizer

_CELL_ADDR_RE = re.compile(r"^\$?[A-Z]{1,3}\$?[0-9]{1,7}$", re.IGNORECASE)
_RANGE_ADDR_RE = re.compile(r"^\$?[A-Z]{1,3}\$?[0-9]{1,7}:\$?[A-Z]{1,3}\$?[0-9]{1,7}$", re.IGNORECASE)
_CROSS_SHEET_RE = re.compile(r"^(?:'([^']+)'|([A-Za-z0-9_\.\-]+))!")
_PURE_PASSTHROUGH_RE = re.compile(
    r"^=(?:'[^']+'|[A-Za-z0-9_\.\-]+)!\$?[A-Z]{1,3}\$?[0-9]{1,7}$",
    re.IGNORECASE,
)


def is_pure_passthrough(formula: str) -> bool:
    return bool(_PURE_PASSTHROUGH_RE.match(formula))


def extract_refs(sheet_name: str, formula: str) -> list[str]:
    """
    Return a list of normalized cell IDs ("SheetName!A1") referenced by the formula.
    Ranges like B2:B20 are returned as a single range ref (not expanded to individual cells).
    """
    try:
        tok = Tokenizer(formula)
    except Exception:
        return []

    refs: list[str] = []
    for token in tok.items:
        if token.subtype != "RANGE":
            continue
        raw: str = token.value.strip()
        m = _CROSS_SHEET_RE.match(raw)
        if m:
            ref_sheet = m.group(1) or m.group(2)
            cell_part = raw[m.end():]
        else:
            ref_sheet = sheet_name
            cell_part = raw

        cell_part = cell_part.replace("$", "").upper()
        refs.append(f"{ref_sheet}!{cell_part}")

    return refs
