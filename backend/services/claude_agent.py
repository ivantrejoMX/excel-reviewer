from __future__ import annotations
import json
import uuid

import anthropic

from backend.config import ANTHROPIC_API_KEY, MODEL, MAX_AGENT_ITERATIONS
from backend.models.analysis import WorkbookAnalysis
from backend.models.job import (
    Issue, IssueType, IssueSeverity, FixBucket, AutoFixAction, SimplificationOptions
)
from backend.services.tool_handlers import (
    handle_get_workbook_summary,
    handle_get_cell_formula,
    handle_get_range_formulas,
    handle_get_dependent_cells,
)

def _get_client(api_key: str = "") -> anthropic.Anthropic:
    """Return a client using the provided key, falling back to the server .env key."""
    return anthropic.Anthropic(api_key=api_key or ANTHROPIC_API_KEY)

TOOLS: list[dict] = [
    {
        "name": "get_workbook_summary",
        "description": "Returns sheet names, formula counts, error counts, and other high-level stats.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_cell_formula",
        "description": "Returns the formula string and cached value for a specific cell.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sheet_name": {"type": "string"},
                "cell_address": {"type": "string", "description": "e.g. A1, B12"},
            },
            "required": ["sheet_name", "cell_address"],
        },
    },
    {
        "name": "get_range_formulas",
        "description": "Returns formula strings and cached values for a rectangular range. Useful for spotting duplicate or inconsistent formulas.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sheet_name": {"type": "string"},
                "range_address": {"type": "string", "description": "e.g. B2:B50"},
            },
            "required": ["sheet_name", "range_address"],
        },
    },
    {
        "name": "get_dependent_cells",
        "description": "Returns all cells whose formulas reference the given cell.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sheet_name": {"type": "string"},
                "cell_address": {"type": "string"},
            },
            "required": ["sheet_name", "cell_address"],
        },
    },
    {
        "name": "flag_issue",
        "description": "Record a discovered issue. Call once per distinct problem.",
        "input_schema": {
            "type": "object",
            "properties": {
                "issue_type": {
                    "type": "string",
                    "enum": [t.value for t in IssueType],
                },
                "severity": {"type": "string", "enum": ["error", "warning", "info"]},
                "sheet_name": {"type": "string"},
                "cell_range": {"type": "string", "description": "e.g. A1 or B2:B20"},
                "description": {"type": "string"},
                "original_formula": {"type": "string"},
                "suggested_fix": {"type": "string"},
                "fix_bucket": {"type": "string", "enum": ["AUTO_FIX", "REQUIRES_VALIDATION"]},
                "auto_fix_action": {
                    "type": "string",
                    "enum": [a.value for a in AutoFixAction],
                },
                "simplification_options": {
                    "type": "object",
                    "description": "Only for redundant_link issues. Provide three alternatives.",
                    "properties": {
                        "a_direct_ref": {"type": "string"},
                        "b_named_range": {"type": "string"},
                        "c_structured_ref": {"type": "string"},
                    },
                },
            },
            "required": ["issue_type", "severity", "sheet_name", "cell_range", "description", "fix_bucket"],
        },
    },
    {
        "name": "finish_analysis",
        "description": "Call when the full analysis is complete. Signals the agent loop to stop.",
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Plain-English paragraph summarising what was found and fixed."},
            },
            "required": ["summary"],
        },
    },
]

# Add cache_control to the last tool so tools + system prompt are cached together
_TOOLS_WITH_CACHE = [t.copy() for t in TOOLS]
_TOOLS_WITH_CACHE[-1] = {**_TOOLS_WITH_CACHE[-1], "cache_control": {"type": "ephemeral"}}


def _build_system_prompt(analysis: WorkbookAnalysis) -> str:
    # Truncate large formula lists to keep the prompt manageable
    MAX_CELLS = 200

    def _trim_cells(lst, limit=MAX_CELLS):
        """Trim a list of Pydantic CellEntry objects; serialises each to dict."""
        items = [e.model_dump() for e in lst[:limit]]
        if len(lst) > limit:
            items.append({"truncated": True, "remaining": len(lst) - limit})
        return items

    def _trim_dicts(lst, limit=MAX_CELLS):
        """Trim a list that is already plain dicts."""
        items = lst[:limit]
        if len(lst) > limit:
            items = list(items) + [{"truncated": True, "remaining": len(lst) - limit}]
        return items

    analysis_dict = {
        "sheet_names": analysis.sheet_names,
        "total_formula_count": analysis.total_formula_count,
        "total_error_count": analysis.total_error_count,
        "circular_references": analysis.circular_references,
        "error_cells": _trim_cells(analysis.error_cells),
        "volatile_cells": _trim_dicts(analysis.volatile_cells),
        "vlookup_cells": _trim_cells(analysis.vlookup_cells),
        "hardcoded_candidates": _trim_dicts(analysis.hardcoded_candidates, 50),
        "redundant_links": _trim_cells(analysis.redundant_links),
        "relay_chains": analysis.relay_chains,
        "formula_cells_sample": _trim_cells(analysis.formula_cells, 100),
    }

    return f"""You are an expert Excel model auditor with deep knowledge of financial modelling best practices.

Your job is to review an Excel workbook and flag every issue you find using the available tools.
Use `get_cell_formula` and `get_range_formulas` to inspect cells before flagging them.
When you have finished reviewing all issues, call `finish_analysis` with a plain-English summary.

RULES FOR FIX BUCKETS:
- AUTO_FIX: Only safe, mechanical changes the user need not review:
    * #DIV/0!, #VALUE!, #N/A, #NAME? → add_iferror (ONLY if the formula has no existing IFERROR/IFNA and no self-reference)
    * Volatile function in a static context → add_comment annotation only
- REQUIRES_VALIDATION (everything else — user must approve):
    * Circular references
    * #REF! errors
    * VLOOKUP/HLOOKUP → XLOOKUP/INDEX-MATCH conversion
    * Nested IF simplification (to IFS or SWITCH)
    * Hardcoded value → formula replacement
    * Redundant tab links (pure passthroughs) — provide three simplification options (a/b/c)
    * Duplicate formula consolidation
    * Any fix touching 20+ cells

REDUNDANT LINK RULES:
For every redundant_link or relay_chain, flag it as issue_type=redundant_link and include simplification_options:
  a_direct_ref: the formula pointing directly to the original source cell
  b_named_range: a suggestion to name the source cell and use the name
  c_structured_ref: a table-reference suggestion (or "Not applicable" if source is not tabular)

DO NOT flag style preferences. Only flag real errors, logic risks, or genuine simplification opportunities.
Inspect complex-looking formulas before flagging them as simplification opportunities.

<workbook_analysis>
{json.dumps(analysis_dict, indent=2, default=str)}
</workbook_analysis>"""


def _dispatch_tool(name: str, inputs: dict, analysis: WorkbookAnalysis) -> str:
    if name == "get_workbook_summary":
        return json.dumps(handle_get_workbook_summary(analysis))
    if name == "get_cell_formula":
        return json.dumps(handle_get_cell_formula(analysis, inputs["sheet_name"], inputs["cell_address"]))
    if name == "get_range_formulas":
        return json.dumps(handle_get_range_formulas(analysis, inputs["sheet_name"], inputs["range_address"]))
    if name == "get_dependent_cells":
        return json.dumps(handle_get_dependent_cells(analysis, inputs["sheet_name"], inputs["cell_address"]))
    if name in ("flag_issue", "finish_analysis"):
        return json.dumps({"status": "recorded"})
    return json.dumps({"error": f"Unknown tool: {name}"})


def _parse_flag_issue(inputs: dict) -> Issue:
    simp = inputs.get("simplification_options")
    simp_obj = SimplificationOptions(**simp) if simp else None
    return Issue(
        issue_id=str(uuid.uuid4()),
        issue_type=IssueType(inputs["issue_type"]),
        severity=IssueSeverity(inputs["severity"]),
        sheet_name=inputs["sheet_name"],
        cell_range=inputs["cell_range"],
        description=inputs["description"],
        original_formula=inputs.get("original_formula"),
        suggested_fix=inputs.get("suggested_fix"),
        fix_bucket=FixBucket(inputs["fix_bucket"]),
        auto_fix_action=AutoFixAction(inputs.get("auto_fix_action", AutoFixAction.NONE.value)),
        simplification_options=simp_obj,
    )


async def run_agent_loop(
    job_id: str,
    analysis: WorkbookAnalysis,
    api_key: str = "",
) -> tuple[list[Issue], list[Issue], str, bool]:
    """
    Runs the Claude agentic loop. Returns (auto_fixes, validation_queue, summary, partial).
    """
    import asyncio

    _client = _get_client(api_key)
    system_prompt = _build_system_prompt(analysis)
    messages: list[dict] = [
        {"role": "user", "content": "Please analyse this Excel workbook and flag all issues you find."}
    ]

    all_issues: list[Issue] = []
    summary = ""
    partial = False
    iterations = 0

    def _sync_loop() -> None:
        nonlocal summary, partial, iterations

        while iterations < MAX_AGENT_ITERATIONS:
            iterations += 1

            response = _client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=[
                    {
                        "type": "text",
                        "text": system_prompt,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                tools=_TOOLS_WITH_CACHE,
                messages=messages,
            )

            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                break

            if response.stop_reason != "tool_use":
                break

            tool_results = []
            should_stop = False

            for block in response.content:
                if block.type != "tool_use":
                    continue

                result_str = _dispatch_tool(block.name, block.input, analysis)

                if block.name == "flag_issue":
                    try:
                        all_issues.append(_parse_flag_issue(block.input))
                    except Exception:
                        pass

                if block.name == "finish_analysis":
                    summary = block.input.get("summary", "")
                    should_stop = True

                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_str,
                    }
                )

            messages.append({"role": "user", "content": tool_results})

            if should_stop:
                break
        else:
            partial = True

    await asyncio.to_thread(_sync_loop)

    auto_fixes = [i for i in all_issues if i.fix_bucket == FixBucket.AUTO_FIX]
    validation_queue = [i for i in all_issues if i.fix_bucket == FixBucket.REQUIRES_VALIDATION]

    if not summary:
        summary = (
            f"Analysis complete. Found {len(all_issues)} issue(s): "
            f"{len(auto_fixes)} auto-fixable, {len(validation_queue)} requiring your review."
        )

    return auto_fixes, validation_queue, summary, partial
