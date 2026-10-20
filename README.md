# Context Signal Lab

Context Signal Lab is a local-first quality gate for LLM conversation traces. It turns a small JSON trace into a repeatable report about context cost, privacy exposure, prompt drift, tool contracts, and regression risk.

The default path is deterministic and offline. It does not require an API key, a vector database, a server process, or a model call. An optional OpenAI-compatible review uses one short request after the local analysis has finished.

## Quick start

~~~bash
python -m pip install -e .
context-signal scan examples/trace.json --out-dir reports
~~~

The command writes reports/support-triage.report.json and reports/support-triage.report.md.

~~~bash
context-signal compare examples/trace.json examples/trace-regressed.json
context-signal budget examples/trace.json --max-tokens 700
~~~

The input format is intentionally small:

~~~json
{
  "id": "support-triage",
  "version": "2026-10-01",
  "budget_tokens": 700,
  "messages": [
    {"role": "system", "content": "Answer with evidence."},
    {"role": "user", "content": "Summarize the incident."},
    {"role": "assistant", "content": "The incident started at 09:10."}
  ],
  "tools": [
    {"name": "incident_lookup", "description": "Find an incident by id.", "parameters": {"type": "object"}}
  ],
  "expect": {"must_include": ["09:10"]}
}
~~~

## Optional model review

The local report is the source of truth for CI. To add one compact second opinion, set an OpenAI-compatible endpoint and pass --llm:

~~~powershell
$env:OPENAI_API_KEY = "..."
$env:CONTEXT_SIGNAL_MODEL = "gpt-4o-mini"
context-signal scan examples/trace.json --llm
~~~

The client sends numeric metrics and at most 40 analyzer code/severity pairs. Trace text, tool names, finding details and evidence are excluded. CONTEXT_SIGNAL_MAX_OUTPUT_TOKENS defaults to 180 (allowed range: 1–512), and only one request is made per scan. OPENAI_BASE_URL can point to another compatible provider. Provider compatibility has been tested with mocked responses, not paid live API calls.

## Scope and limits

This is a small portfolio prototype, with standard-library-only runtime dependencies. Token counts use a character/4 heuristic, not a model tokenizer; multilingual text, tool serialization and message overhead can differ substantially. Scores are hand-set rule penalties, not calibrated measures of model quality. Multiple system messages are a review signal rather than proof of conflicting instructions. Privacy patterns can miss identifiers or flag benign strings, and local report evidence can contain trace content. Keep reports private and use synthetic traces for public examples.

Comparison reports added/removed rule codes and score changes; it does not compare semantic correctness or detect every change within an existing rule. CI thresholds are project choices. The CLI accepts one JSON trace per file.

## Development

~~~bash
python -m pip install -e . pytest ruff
python -m pytest -q
python -m ruff check src tests
~~~

## Architecture

- models.py contains the stable trace, finding, and report contracts.
- analyzers.py contains deterministic, independently testable checks.
- pipeline.py orchestrates loading, analysis, scoring, and report rendering.
- llm.py is an optional, one-call adapter for an OpenAI-compatible endpoint.
- cli.py exposes scan, compare, and budget commands for local use and CI.

## Upstream and license

This repository started from Microsoft's MIT-licensed mcp-interviewer project. The original MCP server inspection and execution modules were removed and replaced with the trace analysis architecture documented above. See DERIVATION.md for the upstream link and the scope of the rewrite. The upstream MIT license is retained in LICENSE.
