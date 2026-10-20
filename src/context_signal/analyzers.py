"""Deterministic checks. They are intentionally independent of any model API."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from .models import Finding, Trace

_SECRET_PATTERNS = {
    "api-key": re.compile(r"(?:sk-|key-|ghp_|xox[baprs]-)[A-Za-z0-9_-]{12,}"),
    "email": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
}


def estimate_tokens(trace: Trace) -> int:
    """Use a stable character heuristic so a scan works without tokenizer packages."""
    text = "\n".join(message.content for message in trace.messages)
    tool_text = "\n".join(
        f"{tool.name} {tool.description} {tool.parameters}" for tool in trace.tools
    )
    return max(1, (len(text) + len(tool_text)) // 4)


def analyze_privacy(trace: Trace) -> list[Finding]:
    findings: list[Finding] = []
    for index, message in enumerate(trace.messages):
        for label, pattern in _SECRET_PATTERNS.items():
            if pattern.search(message.content):
                findings.append(
                    Finding(
                        code="PRIVACY-" + label.upper(),
                        severity="error" if label != "email" else "warning",
                        title=f"Possible {label} exposed in message",
                        detail=f"Message {index} contains a value matching the {label} detector.",
                        evidence=(f"message[{index}].role={message.role}",),
                        suggestion="Replace the value with a stable placeholder before storing or sending the trace.",
                    )
                )
    return findings


def analyze_context(trace: Trace) -> list[Finding]:
    tokens = estimate_tokens(trace)
    findings: list[Finding] = []
    if tokens > trace.budget_tokens:
        findings.append(
            Finding(
                code="CONTEXT-BUDGET",
                severity="error",
                title="Trace exceeds its context budget",
                detail=f"Estimated {tokens} tokens against a {trace.budget_tokens}-token budget.",
                evidence=(f"estimated_tokens={tokens}", f"budget_tokens={trace.budget_tokens}"),
                suggestion="Summarize repeated context or move stable instructions into a versioned prompt.",
            )
        )
    if len(trace.messages) >= 2:
        normalized = [
            re.sub(r"\s+", " ", message.content.strip().lower()) for message in trace.messages
        ]
        repeats = [value for value, count in Counter(normalized).items() if value and count > 1]
        if repeats:
            findings.append(
                Finding(
                    code="CONTEXT-DUPLICATE",
                    severity="warning",
                    title="Repeated message content increases context cost",
                    detail=f"Found {len(repeats)} repeated normalized message(s).",
                    evidence=tuple(repeats[:3]),
                    suggestion="Keep one canonical instruction and attach a trace reference for later turns.",
                )
            )
    if trace.messages:
        largest = max(len(message.content) for message in trace.messages)
        total = sum(len(message.content) for message in trace.messages)
        if total and largest / total >= 0.65 and largest >= 800:
            findings.append(
                Finding(
                    code="CONTEXT-HOTSPOT",
                    severity="info",
                    title="One message dominates the context",
                    detail="A single message accounts for at least 65% of trace characters.",
                    evidence=(f"largest_chars={largest}", f"total_chars={total}"),
                    suggestion="Split the payload into retrievable facts or a compact structured object.",
                )
            )
    return findings


def analyze_drift(trace: Trace) -> list[Finding]:
    findings: list[Finding] = []
    system_messages = [message for message in trace.messages if message.role == "system"]
    if len(system_messages) > 1:
        findings.append(
            Finding(
                code="DRIFT-MULTI-SYSTEM",
                severity="warning",
                title="Multiple system messages can create instruction drift",
                detail=f"The trace contains {len(system_messages)} system messages.",
                evidence=tuple(
                    f"system[{i}]={message.content[:80]}"
                    for i, message in enumerate(system_messages)
                ),
                suggestion="Compose one explicit system contract and version it with the trace.",
            )
        )
    names = [tool.name for tool in trace.tools]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        findings.append(
            Finding(
                code="DRIFT-DUP-TOOL",
                severity="error",
                title="Tool names are not unique",
                detail="Duplicate names make tool selection ambiguous.",
                evidence=tuple(duplicates),
                suggestion="Rename tools with a stable namespace and add a schema regression test.",
            )
        )
    expected = trace.expected.get("must_include", [])
    assistant_text = "\n".join(
        message.content for message in trace.messages if message.role == "assistant"
    )
    missing = [str(item) for item in expected if str(item) not in assistant_text]
    if missing:
        findings.append(
            Finding(
                code="DRIFT-EXPECTATION",
                severity="warning",
                title="Expected answer signals are missing",
                detail=f"The assistant output misses {len(missing)} required signal(s).",
                evidence=tuple(missing),
                suggestion="Keep expectations as assertions and add a regression fixture for each critical signal.",
            )
        )
    return findings


def analyze_tools(trace: Trace) -> list[Finding]:
    findings: list[Finding] = []
    for index, tool in enumerate(trace.tools):
        if not tool.description.strip():
            findings.append(
                Finding(
                    code="TOOL-DESCRIPTION",
                    severity="warning",
                    title="Tool description is empty",
                    detail=f"Tool {tool.name!r} has no description for model selection.",
                    evidence=(f"tools[{index}].name={tool.name}",),
                    suggestion="Describe purpose, side effects, and the shape of a successful result.",
                )
            )
        if tool.parameters.get("type") != "object":
            findings.append(
                Finding(
                    code="TOOL-SCHEMA",
                    severity="warning",
                    title="Tool parameters should declare an object schema",
                    detail=f"Tool {tool.name!r} does not declare parameters.type=object.",
                    evidence=(f"tools[{index}].parameters.type={tool.parameters.get('type')}",),
                    suggestion="Use a JSON Schema object with explicit properties and required fields.",
                )
            )
    return findings


def run_analyzers(trace: Trace) -> tuple[Finding, ...]:
    groups: Iterable[list[Finding]] = (
        analyze_privacy(trace),
        analyze_context(trace),
        analyze_drift(trace),
        analyze_tools(trace),
    )
    return tuple(finding for group in groups for finding in group)
