import pytest
from backend.services.formula_tokenizer import extract_refs, is_pure_passthrough


def test_simple_ref():
    refs = extract_refs("Sheet1", "=A1+B2")
    assert "Sheet1!A1" in refs
    assert "Sheet1!B2" in refs


def test_cross_sheet_ref():
    refs = extract_refs("Summary", "=Input!C12")
    assert "Input!C12" in refs


def test_quoted_sheet_name():
    refs = extract_refs("Summary", "='Sales Data'!B5")
    assert "Sales Data!B5" in refs


def test_range_ref():
    refs = extract_refs("Sheet1", "=SUM(A1:A10)")
    assert any("A1:A10" in r for r in refs)


def test_pure_passthrough_simple():
    assert is_pure_passthrough("=Input!C12") is True


def test_pure_passthrough_with_dollar():
    assert is_pure_passthrough("='My Sheet'!$C$12") is True


def test_not_passthrough_sum():
    assert is_pure_passthrough("=SUM(Sheet1!A1:A10)") is False


def test_not_passthrough_formula():
    assert is_pure_passthrough("=Input!C12+1") is False


def test_empty_formula():
    refs = extract_refs("Sheet1", "=")
    assert refs == []
