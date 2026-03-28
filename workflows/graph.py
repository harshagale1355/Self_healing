"""
LangGraph pipeline: log read → filter → per-error classify → context → RAG → solution → validate.
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph import END, StateGraph

import config
from agents.classifier import classify_error
from agents.context_extractor import extract_context
from agents.error_filter import filter_error_lines
from agents.log_reader import read_logs
from agents.solution_generator import generate_solution
from agents.validator import validate_solution
from rag.retriever import ErrorRAGRetriever


class AnalysisState(TypedDict, total=False):
    project_path: str
    use_rag: bool
    use_llm_classifier: bool
    log_paths: list[str]
    raw_lines: list[str]
    error_lines: list[str]
    queue: list[str]
    current_line: str
    classification: dict[str, Any]
    context_payload: dict[str, Any]
    rag_snippets: list[str]
    last_solution: dict[str, Any]
    results: Annotated[list[dict[str, Any]], operator.add]
    status: str
    skip_reason: str | None


def node_log_reader(state: AnalysisState) -> dict[str, Any]:
    path = state.get("project_path", ".")
    data = read_logs(path)
    return {
        "log_paths": data["log_paths"],
        "raw_lines": data["raw_lines"],
        "status": "read",
    }


def node_error_filter(state: AnalysisState) -> dict[str, Any]:
    raw = state.get("raw_lines") or []
    fe = filter_error_lines(raw)
    lines = fe["error_lines"]
    return {
        "error_lines": lines,
        "queue": list(lines),
        "status": "filtered",
    }


def route_after_filter(state: AnalysisState) -> Literal["dequeue", "empty_end"]:
    if not state.get("queue"):
        return "empty_end"
    return "dequeue"


def node_empty_end(state: AnalysisState) -> dict[str, Any]:
    raw = state.get("raw_lines") or []
    if not raw:
        return {
            "results": [],
            "skip_reason": "no_log_files_or_empty",
            "status": "done",
        }
    return {
        "results": [
            {
                "error": "(no error lines matched filters)",
                "type": "unknown",
                "cause": "No lines matched error keywords. Try lowering filters or check log content.",
                "fix": "Ensure logs contain ERROR/Exception/traceback or enable warnings in error_filter.",
                "code": "",
                "confidence": 0.0,
            }
        ],
        "skip_reason": "no_error_lines",
        "status": "done",
    }


def node_dequeue(state: AnalysisState) -> dict[str, Any]:
    q = list(state.get("queue") or [])
    if not q:
        return {"status": "done"}
    line = q[0]
    rest = q[1:]
    return {"current_line": line, "queue": rest, "status": "processing"}


def node_classifier(state: AnalysisState) -> dict[str, Any]:
    line = state.get("current_line", "")
    use_llm = bool(state.get("use_llm_classifier"))
    c = classify_error(line, use_llm=use_llm)
    return {"classification": c}


def node_context(state: AnalysisState) -> dict[str, Any]:
    line = state.get("current_line", "")
    proj = state.get("project_path", ".")
    payload = extract_context(line, project_path=proj)
    return {"context_payload": payload}


def node_rag(state: AnalysisState) -> dict[str, Any]:
    rag_on = bool(state.get("use_rag")) or config.ENABLE_RAG
    if not rag_on:
        return {"rag_snippets": []}
    line = state.get("current_line", "")
    retriever = ErrorRAGRetriever(enabled=True)
    snippets = retriever.similar(line, k=4)
    return {"rag_snippets": snippets}


def node_solution(state: AnalysisState) -> dict[str, Any]:
    line = state.get("current_line", "")
    cls = state.get("classification") or {}
    ctx = state.get("context_payload") or {}
    rag = state.get("rag_snippets") or []
    sol = generate_solution(line, cls, ctx, rag_snippets=rag)
    return {"last_solution": sol}  # type: ignore[typeddict-item]


def node_validator(state: AnalysisState) -> dict[str, Any]:
    line = state.get("current_line", "")
    sol = state.get("last_solution") or {}
    validated = validate_solution(line, sol)
    if state.get("use_rag") or config.ENABLE_RAG:
        try:
            r = ErrorRAGRetriever(enabled=True)
            r.add_error(
                line,
                metadata={"fix": str(validated.get("fix", ""))[:2000], "type": str(validated.get("type", ""))},
            )
        except Exception:
            pass
    # strip heavy context from final output for JSON size
    slim = {k: v for k, v in validated.items() if k != "context"}
    if "context" in validated:
        slim["context"] = {
            "file": (validated.get("context") or {}).get("file"),
            "line": (validated.get("context") or {}).get("line"),
            "function": (validated.get("context") or {}).get("function"),
        }
    return {"results": [slim]}


def route_continue(state: AnalysisState) -> Literal["dequeue", "end"]:
    if state.get("queue"):
        return "dequeue"
    return "end"


def node_finalize(_: AnalysisState) -> dict[str, Any]:
    return {"status": "done"}


def build_analysis_graph():
    g = StateGraph(AnalysisState)
    g.add_node("log_reader", node_log_reader)
    g.add_node("error_filter", node_error_filter)
    g.add_node("empty_end", node_empty_end)
    g.add_node("dequeue", node_dequeue)
    g.add_node("classifier", node_classifier)
    g.add_node("context_extractor", node_context)
    g.add_node("rag", node_rag)
    g.add_node("solution_generator", node_solution)
    g.add_node("validator", node_validator)
    g.add_node("finalize", node_finalize)

    g.set_entry_point("log_reader")
    g.add_edge("log_reader", "error_filter")
    g.add_conditional_edges(
        "error_filter",
        route_after_filter,
        {"dequeue": "dequeue", "empty_end": "empty_end"},
    )
    g.add_edge("empty_end", "finalize")
    g.add_edge("dequeue", "classifier")
    g.add_edge("classifier", "context_extractor")
    g.add_edge("context_extractor", "rag")
    g.add_edge("rag", "solution_generator")
    g.add_edge("solution_generator", "validator")
    g.add_conditional_edges(
        "validator",
        route_continue,
        {"dequeue": "dequeue", "end": "finalize"},
    )
    g.add_edge("finalize", END)
    return g.compile()


def run_analysis(
    project_path: str,
    *,
    use_rag: bool | None = None,
    use_llm_classifier: bool = False,
) -> list[dict[str, Any]]:
    """
    Execute the compiled graph and return the list of result dicts.
    """
    graph = build_analysis_graph()
    initial: AnalysisState = {
        "project_path": project_path,
        "use_rag": bool(use_rag if use_rag is not None else config.ENABLE_RAG),
        "use_llm_classifier": use_llm_classifier,
        "results": [],
    }
    out = graph.invoke(initial)
    res = list(out.get("results") or [])
    if not res and out.get("skip_reason"):
        res = [
            {
                "error": "",
                "type": "unknown",
                "cause": str(out["skip_reason"]),
                "fix": "Add readable .log/.txt files under the project or check LOG_EXTENSIONS.",
                "code": "",
                "confidence": 0.0,
            }
        ]
    return res
