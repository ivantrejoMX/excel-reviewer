from __future__ import annotations
import json
from openpyxl import load_workbook
from backend.models.analysis import WorkbookAnalysis


def _load_wb_values(file_path: str):
    return load_workbook(file_path, data_only=True)


def handle_get_workbook_summary(analysis: WorkbookAnalysis) -> dict:
    sheet_stats = {}
    from collections import Counter
    sheet_formula_counts: Counter = Counter()
    for c in analysis.formula_cells:
        sheet_formula_counts[c.sheet] += 1
    for sheet in analysis.sheet_names:
        sheet_stats[sheet] = {"formula_count": sheet_formula_counts.get(sheet, 0)}
    return {
        "sheet_names": analysis.sheet_names,
        "total_formulas": analysis.total_formula_count,
        "total_errors": analysis.total_error_count,
        "circular_reference_cycles": len(analysis.circular_references),
        "redundant_links": len(analysis.redundant_links),
        "relay_chains": len(analysis.relay_chains),
        "volatile_cells": len(analysis.volatile_cells),
        "vlookup_cells": len(analysis.vlookup_cells),
        "sheet_stats": sheet_stats,
    }


def handle_get_cell_formula(analysis: WorkbookAnalysis, sheet_name: str, cell_address: str) -> dict:
    addr_upper = cell_address.upper().replace("$", "")
    for entry in analysis.formula_cells:
        if entry.sheet == sheet_name and entry.coord.upper() == addr_upper:
            return {
                "sheet": entry.sheet,
                "cell": entry.coord,
                "formula": entry.formula,
                "cached_value": entry.cached_value,
            }
    return {"error": f"Cell {sheet_name}!{cell_address} not found or has no formula"}


def handle_get_range_formulas(analysis: WorkbookAnalysis, sheet_name: str, range_address: str) -> dict:
    # Parse range like B2:B50
    import re
    m = re.match(r"^\$?([A-Z]+)\$?(\d+):\$?([A-Z]+)\$?(\d+)$", range_address.upper().replace("$", ""))
    if not m:
        return {"error": f"Cannot parse range '{range_address}'"}

    col_start, row_start, col_end, row_end = m.group(1), int(m.group(2)), m.group(3), int(m.group(4))

    def col_index(col: str) -> int:
        result = 0
        for ch in col:
            result = result * 26 + (ord(ch) - ord('A') + 1)
        return result

    def col_letters(idx: int) -> str:
        result = ""
        while idx > 0:
            idx, rem = divmod(idx - 1, 26)
            result = chr(65 + rem) + result
        return result

    cs = col_index(col_start)
    ce = col_index(col_end)

    results = []
    for entry in analysis.formula_cells:
        if entry.sheet != sheet_name:
            continue
        em = re.match(r"([A-Z]+)(\d+)", entry.coord.upper())
        if not em:
            continue
        ec, er = em.group(1), int(em.group(2))
        if row_start <= er <= row_end and cs <= col_index(ec) <= ce:
            results.append({"cell": entry.coord, "formula": entry.formula, "cached_value": entry.cached_value})

    return {"sheet": sheet_name, "range": range_address, "cells": results, "count": len(results)}


def handle_get_dependent_cells(analysis: WorkbookAnalysis, sheet_name: str, cell_address: str) -> dict:
    target_id = f"{sheet_name}!{cell_address.upper().replace('$', '')}"
    dependents = []
    for entry in analysis.formula_cells:
        formula = entry.formula or ""
        # Simple check: does the formula mention the target?
        if sheet_name in formula and cell_address.replace("$", "") in formula.upper():
            dependents.append({"sheet": entry.sheet, "cell": entry.coord, "formula": entry.formula})
    return {"target": target_id, "dependents": dependents, "count": len(dependents)}
