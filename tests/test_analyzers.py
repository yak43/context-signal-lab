import json

from context_signal.analyzers import estimate_tokens, run_analyzers
from context_signal.pipeline import analyze_file, compare_traces, load_trace


def test_clean_trace_has_no_findings():
    trace = load_trace("examples/trace.json")
    assert run_analyzers(trace) == ()
    assert estimate_tokens(trace) > 0


def test_regressed_trace_reports_drift_and_schema_issues():
    trace = load_trace("examples/trace-regressed.json")
    codes = {finding.code for finding in run_analyzers(trace)}
    assert {"DRIFT-MULTI-SYSTEM", "DRIFT-DUP-TOOL", "DRIFT-EXPECTATION", "TOOL-SCHEMA"} <= codes


def test_compare_surfaces_introduced_findings():
    result = compare_traces(
        load_trace("examples/trace.json"),
        load_trace("examples/trace-regressed.json"),
    )
    assert result["score_delta"] < 0
    assert "DRIFT-DUP-TOOL" in result["introduced"]


def test_analyze_file_writes_serializable_report(tmp_path):
    report = analyze_file("examples/trace.json")
    output = tmp_path / "report.json"
    output.write_text(json.dumps(report.to_dict()), encoding="utf-8")
    assert json.loads(output.read_text(encoding="utf-8"))["score"] == 100
