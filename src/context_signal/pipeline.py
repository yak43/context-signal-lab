"""Input loading, scoring, comparison, and report rendering."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .analyzers import estimate_tokens, run_analyzers
from .models import Finding, Message, Report, ToolSpec, Trace


def _trace_from_dict(data: dict[str, Any]) -> Trace:
    if not isinstance(data, dict):
        raise ValueError("Trace must be a JSON object")
    raw_messages = data.get("messages")
    if not isinstance(raw_messages, list) or not raw_messages:
        raise ValueError("messages must be a non-empty list")
    for item in raw_messages:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("role"), str)
            or item.get("role") not in {"system", "developer", "user", "assistant", "tool"}
            or not isinstance(item.get("content"), str)
        ):
            raise ValueError("Each message needs a valid role and string content")
    raw_tools = data.get("tools", [])
    if not isinstance(raw_tools, list):
        raise ValueError("tools must be a list")
    for item in raw_tools:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("name"), str)
            or not item["name"].strip()
            or not isinstance(item.get("description", ""), str)
            or not isinstance(item.get("parameters", {}), dict)
        ):
            raise ValueError("Invalid tool specification")
    expected = data.get("expect", {})
    if not isinstance(expected, dict) or not isinstance(expected.get("must_include", []), list):
        raise ValueError("expect.must_include must be a list")
    if any(not isinstance(item, str) for item in expected.get("must_include", [])):
        raise ValueError("Expected signals must be strings")
    budget = data.get("budget_tokens", 1200)
    if type(budget) is not int or budget <= 0:
        raise ValueError("budget_tokens must be a positive integer")
    if not isinstance(data.get("metadata", {}), dict):
        raise ValueError("metadata must be an object")
    messages = tuple(
        Message(
            role=str(item["role"]),
            content=str(item.get("content", "")),
            name=item.get("name"),
        )
        for item in data.get("messages", [])
    )
    tools = tuple(
        ToolSpec(
            name=str(item["name"]),
            description=str(item.get("description", "")),
            parameters=dict(item.get("parameters", {})),
        )
        for item in data.get("tools", [])
    )
    return Trace(
        trace_id=str(data.get("id", "unnamed-trace")),
        version=str(data.get("version", "0")),
        messages=messages,
        tools=tools,
        budget_tokens=int(data.get("budget_tokens", 1200)),
        expected=dict(data.get("expect", {})),
        metadata=dict(data.get("metadata", {})),
    )


def load_trace(path: str | Path) -> Trace:
    source = Path(path)
    raw = source.read_text(encoding="utf-8").strip()
    if not raw:
        raise ValueError(f"Trace file is empty: {source}")
    return _trace_from_dict(json.loads(raw))


def _score(findings: tuple[Finding, ...]) -> int:
    penalties = {"error": 28, "warning": 14, "info": 4}
    return max(0, 100 - sum(penalties.get(item.severity, 0) for item in findings))


def analyze_trace(trace: Trace) -> Report:
    findings = run_analyzers(trace)
    return Report(
        trace_id=trace.trace_id,
        version=trace.version,
        score=_score(findings),
        estimated_tokens=estimate_tokens(trace),
        findings=findings,
    )


def analyze_file(path: str | Path, use_llm: bool = False) -> Report:
    report = analyze_trace(load_trace(path))
    if use_llm:
        from .llm import request_review

        review = request_review(report)
        report = Report(
            trace_id=report.trace_id,
            version=report.version,
            score=report.score,
            estimated_tokens=report.estimated_tokens,
            findings=report.findings,
            llm_review=review,
        )
    return report


def compare_traces(before: Trace, after: Trace) -> dict[str, Any]:
    left = analyze_trace(before)
    right = analyze_trace(after)
    before_codes = {item.code for item in left.findings}
    after_codes = {item.code for item in right.findings}
    return {
        "before": left.to_dict(),
        "after": right.to_dict(),
        "score_delta": right.score - left.score,
        "resolved": sorted(before_codes - after_codes),
        "introduced": sorted(after_codes - before_codes),
    }


def render_markdown(report: Report) -> str:
    lines = [
        f"# Context Signal Report: {report.trace_id}",
        "",
        f"- Version: {report.version}",
        f"- Score: **{report.score}/100**",
        f"- Estimated tokens: {report.estimated_tokens}",
        "",
        "## Findings",
        "",
    ]
    if not report.findings:
        lines.append("No deterministic findings.")
    for finding in report.findings:
        lines.extend(
            [
                f"### {finding.severity.upper()} {finding.code}: {finding.title}",
                finding.detail,
                "",
                f"Suggestion: {finding.suggestion}",
                "",
            ]
        )
    if report.llm_review:
        lines.extend(["## Optional model review", "", report.llm_review, ""])
    return "\n".join(lines)
