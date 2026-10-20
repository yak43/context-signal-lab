"""Small, serializable contracts shared by analyzers and report renderers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Message:
    role: str
    content: str
    name: str | None = None


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Trace:
    trace_id: str
    version: str
    messages: tuple[Message, ...]
    tools: tuple[ToolSpec, ...] = ()
    budget_tokens: int = 1200
    expected: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    title: str
    detail: str
    evidence: tuple[str, ...] = ()
    suggestion: str = ""


@dataclass(frozen=True)
class Report:
    trace_id: str
    version: str
    score: int
    estimated_tokens: int
    findings: tuple[Finding, ...]
    llm_review: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
