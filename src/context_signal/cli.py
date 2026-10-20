"""Command line interface for local scans and CI checks."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from .analyzers import estimate_tokens
from .pipeline import analyze_file, compare_traces, load_trace, render_markdown


def _scan(args: argparse.Namespace) -> int:
    report = analyze_file(args.trace, use_llm=args.llm)
    output_dir = Path(args.out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    # A trace id is data, never a filesystem path (including Windows paths).
    stem = re.sub(r"[^A-Za-z0-9_-]", "_", report.trace_id)[:80] or "trace"
    (output_dir / f"{stem}.report.json").write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (output_dir / f"{stem}.report.md").write_text(render_markdown(report), encoding="utf-8")
    print(f"{report.trace_id}: score={report.score}/100 tokens={report.estimated_tokens}")
    for finding in report.findings:
        print(f"[{finding.severity}] {finding.code}: {finding.title}")
    return 2 if args.fail_on and report.score < args.fail_on else 0


def _compare(args: argparse.Namespace) -> int:
    result = compare_traces(load_trace(args.before), load_trace(args.after))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if result["score_delta"] < 0 and args.fail_on_regression else 0


def _budget(args: argparse.Namespace) -> int:
    trace = load_trace(args.trace)
    tokens = estimate_tokens(trace)
    print(f"estimated_tokens={tokens} budget_tokens={args.max_tokens}")
    return 1 if tokens > args.max_tokens else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="context-signal")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="Analyze one trace and write reports")
    scan.add_argument("trace", type=Path)
    scan.add_argument("--out-dir", default="reports")
    scan.add_argument("--llm", action="store_true", help="Use one optional model review call")
    scan.add_argument("--fail-on", type=int, default=0, help="Exit non-zero below this score")
    scan.set_defaults(handler=_scan)

    compare = subparsers.add_parser("compare", help="Compare two trace versions")
    compare.add_argument("before", type=Path)
    compare.add_argument("after", type=Path)
    compare.add_argument("--fail-on-regression", action="store_true")
    compare.set_defaults(handler=_compare)

    budget = subparsers.add_parser("budget", help="Check a trace against a token budget")
    budget.add_argument("trace", type=Path)
    budget.add_argument("--max-tokens", type=int, required=True)
    budget.set_defaults(handler=_budget)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if hasattr(args, "fail_on") and not 0 <= args.fail_on <= 100:
        parser.error("--fail-on must be between 0 and 100")
    if hasattr(args, "max_tokens") and args.max_tokens <= 0:
        parser.error("--max-tokens must be positive")
    try:
        result = args.handler(args)
    except (OSError, ValueError, RuntimeError):
        # Do not echo raw payloads, paths, or provider error bodies.
        parser.exit(
            2,
            "context-signal: invalid input, configuration, or failed I/O; check the trace and endpoint.\n",
        )
    sys.exit(result)
