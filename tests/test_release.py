"""Exercise file boundaries, offline execution and the optional API contract."""

import json
from dataclasses import replace
from unittest.mock import patch

import pytest

from context_signal.cli import main
from context_signal.llm import build_review_prompt, request_review
from context_signal.models import Finding
from context_signal.pipeline import analyze_file, load_trace


@pytest.mark.parametrize(
    "change",
    [
        {"messages": []},
        {"messages": [{"role": [], "content": "hello"}]},
        {"messages": [{"role": "user", "content": {"nested": "text"}}]},
        {"budget_tokens": True},
        {"budget_tokens": -1},
        {"tools": [{"name": "lookup", "parameters": []}]},
        {"expect": {"must_include": "required"}},
    ],
)
def test_invalid_traces_are_rejected(tmp_path, change):
    data = {"messages": [{"role": "user", "content": "hello"}], **change}
    path = tmp_path / "input.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        load_trace(path)


def test_scan_confines_output_to_directory(tmp_path):
    data = {"id": "../../escape", "messages": [{"role": "user", "content": "hi"}]}
    path = tmp_path / "input.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    output = tmp_path / "reports"
    with pytest.raises(SystemExit) as result:
        main(["scan", str(path), "--out-dir", str(output)])
    assert result.value.code == 0
    files = list(output.iterdir())
    assert len(files) == 2
    assert {file.suffix for file in files} == {".json", ".md"}
    assert not list(tmp_path.glob("escape*"))


def test_default_analysis_never_calls_network():
    with patch("urllib.request.urlopen", side_effect=AssertionError("offline")) as network:
        assert analyze_file("examples/trace.json").score == 100
    network.assert_not_called()


def test_model_prompt_excludes_private_text_and_is_bounded():
    report = analyze_file("examples/trace.json")
    finding = Finding("TEST", "warning", "private title", "private detail", ("private evidence",))
    report = replace(report, trace_id="private id", findings=(finding,) * 1000)
    prompt = build_review_prompt(report)
    assert "private" not in prompt
    assert prompt.count("TEST") == 40
    assert len(prompt) < 3000


def test_optional_model_review_makes_one_bounded_request(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-value")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("CONTEXT_SIGNAL_MAX_OUTPUT_TOKENS", "180")
    monkeypatch.setenv("CONTEXT_SIGNAL_MODEL", "test-model")
    with patch("urllib.request.urlopen") as network:
        network.return_value.__enter__.return_value.read.return_value = json.dumps(
            {"choices": [{"message": {"content": "Review tool names."}}]}
        ).encode()
        report = analyze_file("examples/trace.json", use_llm=True)
    assert report.llm_review == "Review tool names."
    network.assert_called_once()
    request = network.call_args.args[0]
    payload = json.loads(request.data)
    assert payload["max_tokens"] == 180
    assert "09:10" not in request.data.decode()


def test_output_limit_rejected_before_network(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-test-value")
    monkeypatch.setenv("CONTEXT_SIGNAL_MAX_OUTPUT_TOKENS", "99999")
    with patch("urllib.request.urlopen") as network, pytest.raises(ValueError):
        request_review(analyze_file("examples/trace.json"))
    network.assert_not_called()


def test_regression_exit_status():
    with pytest.raises(SystemExit) as result:
        main(
            [
                "compare",
                "examples/trace.json",
                "examples/trace-regressed.json",
                "--fail-on-regression",
            ]
        )
    assert result.value.code == 1


def test_privacy_detector_does_not_put_matched_secret_in_finding(tmp_path):
    secret = "sk-synthetic123456789012345"
    path = tmp_path / "trace.json"
    path.write_text(json.dumps({"messages": [{"role": "user", "content": secret}]}))
    report = analyze_file(path)
    assert any(item.code == "PRIVACY-API-KEY" for item in report.findings)
    assert secret not in json.dumps(report.to_dict())


def test_budget_and_duplicate_context_are_detected(tmp_path):
    path = tmp_path / "trace.json"
    path.write_text(
        json.dumps(
            {
                "budget_tokens": 1,
                "messages": [{"role": "user", "content": "identical repeated instruction"}] * 2,
            }
        )
    )
    codes = {item.code for item in analyze_file(path).findings}
    assert {"CONTEXT-BUDGET", "CONTEXT-DUPLICATE"} <= codes
