from __future__ import annotations
from enum import Enum
from typing import Any
from pydantic import BaseModel


class JobStatus(str, Enum):
    UPLOADED = "UPLOADED"
    ANALYZING = "ANALYZING"
    READY = "READY"
    APPLYING = "APPLYING"
    DONE = "DONE"
    ERROR = "ERROR"


class IssueSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class IssueType(str, Enum):
    CIRCULAR_REFERENCE = "circular_reference"
    FORMULA_ERROR = "formula_error"
    HARDCODED_VALUE = "hardcoded_value"
    BROKEN_LOOKUP = "broken_lookup"
    SIMPLIFICATION = "simplification_opportunity"
    VOLATILE_FUNCTION = "volatile_function"
    DUPLICATE_FORMULA = "duplicate_formula"
    REDUNDANT_LINK = "redundant_link"


class FixBucket(str, Enum):
    AUTO_FIX = "AUTO_FIX"
    REQUIRES_VALIDATION = "REQUIRES_VALIDATION"


class AutoFixAction(str, Enum):
    ADD_IFERROR = "add_iferror"
    REPLACE_FORMULA = "replace_formula"
    REPLACE_VLOOKUP_XLOOKUP = "replace_vlookup_xlookup"
    ADD_COMMENT = "add_comment"
    NONE = "none"


class SimplificationOptions(BaseModel):
    a_direct_ref: str | None = None
    b_named_range: str | None = None
    c_structured_ref: str | None = None


class Issue(BaseModel):
    issue_id: str
    issue_type: IssueType
    severity: IssueSeverity
    sheet_name: str
    cell_range: str
    description: str
    original_formula: str | None = None
    suggested_fix: str | None = None
    fix_bucket: FixBucket
    auto_fix_action: AutoFixAction = AutoFixAction.NONE
    simplification_options: SimplificationOptions | None = None


class ApplyRequest(BaseModel):
    approved_fix_ids: list[str] = []
    rejected_fix_ids: list[str] = []
    named_range_choices: dict[str, str] = {}  # fix_id -> range name chosen by user


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    filename: str
    progress_message: str = ""
    auto_fixes: list[Issue] = []
    validation_queue: list[Issue] = []
    summary: str = ""
    error: str | None = None
    partial_analysis: bool = False
