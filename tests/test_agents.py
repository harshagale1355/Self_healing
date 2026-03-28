"""Basic tests for parsers, filters, and classifier heuristics."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.error_filter import filter_error_lines
from agents.classifier import classify_error_line_rules
from agents.code_context import enrich_code_context
from agents.context_extractor import extract_context
from utils.parser import parse_stack_line


def test_parse_python_file_line():
    line = '  File "/app/services/user.py", line 42, in fetch_user'
    d = parse_stack_line(line)
    assert d.get("file") == "/app/services/user.py"
    assert d.get("line") == 42
    assert d.get("function") == "fetch_user"


def test_parse_node_at():
    line = "    at callApi (/app/dist/api.js:88:15)"
    d = parse_stack_line(line)
    assert "api.js" in (d.get("file") or "")
    assert d.get("line") == 88


def test_error_filter_finds_errors():
    raw = [
        "INFO ok",
        "ERROR something failed",
        "all good",
    ]
    out = filter_error_lines(raw)
    assert len(out["error_lines"]) >= 1
    assert "ERROR" in out["error_lines"][0]


def test_classifier_rules_database():
    line = "psycopg2.OperationalError: connection refused"
    c = classify_error_line_rules(line)
    assert c["type"] == "database"


def test_context_extractor(tmp_path: Path):
    p = tmp_path / "mod.py"
    p.write_text("\n" * 4 + "def foo():\n    raise RuntimeError('x')\n")
    line = f'  File "{p}", line 5, in foo'
    payload = extract_context(line, project_path=tmp_path)
    enriched = enrich_code_context(tmp_path, payload)
    assert enriched["context"].get("line") == 5
    snip = enriched["context"].get("codebase_snippet")
    assert snip and "def foo" in snip


def test_expected_json_shape():
    """Document expected output keys for pipeline results."""
    sample = {
        "error": "ERROR x",
        "type": "runtime",
        "cause": "…",
        "fix": "…",
        "code": "",
        "patch": "--- a/x\n+++ b/x\n",
        "severity": "high",
        "confidence": 0.85,
    }
    parsed = json.loads(json.dumps(sample))
    for k in ("error", "type", "cause", "fix", "code", "patch", "severity", "confidence"):
        assert k in parsed


def test_run_analysis_returns_metrics(tmp_path: Path):
    (tmp_path / "t.log").write_text("ERROR boom\n", encoding="utf-8")
    from workflows.graph import run_analysis

    out = run_analysis(str(tmp_path), use_rag=False)
    assert "results" in out and "metrics" in out
    assert isinstance(out["metrics"], dict)
