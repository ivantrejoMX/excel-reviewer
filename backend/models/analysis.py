from __future__ import annotations
from pydantic import BaseModel


class CellEntry(BaseModel):
    sheet: str
    coord: str
    formula: str
    cached_value: str | None = None


class WorkbookAnalysis(BaseModel):
    sheet_names: list[str]
    formula_cells: list[CellEntry]
    error_cells: list[CellEntry]
    volatile_cells: list[dict]
    vlookup_cells: list[CellEntry]
    hardcoded_candidates: list[dict]
    circular_references: list[list[str]]
    redundant_links: list[CellEntry]
    relay_chains: list[list[str]]
    total_formula_count: int
    total_error_count: int
