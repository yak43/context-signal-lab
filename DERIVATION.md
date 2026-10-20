# Derivation note

## Upstream

- Project: Microsoft mcp-interviewer
- URL: https://github.com/microsoft/mcp-interviewer
- License: MIT
- Retrieved: 2026-10-01
- Starting commit: 17e352f551838a0e0d09518402208530122528f6

## Rewrite scope

The upstream package inspected and executed MCP servers, generated functional tests, and optionally asked an LLM to judge tool behavior. This version removes those server-side execution paths and introduces a new package named context_signal with:

1. A stable JSON trace contract.
2. Offline token, privacy, duplication, drift, and tool-schema analyzers.
3. A scored report with machine-readable findings and Markdown output.
4. A two-version comparator for regression checks.
5. A bounded OpenAI-compatible review adapter that is opt-in and limited to one request.

This is an independent trace-analysis rewrite, not a drop-in replacement for MCP Interviewer. The upstream attribution and license remain; Microsoft does not sponsor this modified project.
