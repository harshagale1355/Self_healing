"""
Streamlit UI: upload or project path, cards for errors, patches, metrics.
Run: streamlit run ui/app.py
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import streamlit as st

import config
from workflows.graph import run_analysis

st.set_page_config(page_title="AI Log Error Analyzer", layout="wide", initial_sidebar_state="expanded")

st.markdown(
    """
<style>
    .stMetric { background: linear-gradient(90deg, #1e1e2e 0%, #252536 100%); padding: 12px; border-radius: 8px; }
    div[data-testid="stExpander"] { border: 1px solid #333; border-radius: 8px; }
</style>
""",
    unsafe_allow_html=True,
)

st.title("AI Log Error Analyzer")
st.caption("Codebase-aware debugging, RAG memory, patches, and severity.")

with st.sidebar:
    st.subheader("Options")
    use_rag = st.checkbox("Enable RAG (Chroma)", value=config.ENABLE_RAG)
    llm_cls = st.checkbox("LLM classifier", value=False)
    st.markdown(
        "Put `GROQ_API_KEY` (or `OPENAI_API_KEY`) in project **`.env`** — Groq is used automatically when that key is set."
    )

uploaded = st.file_uploader("Upload a log file", type=["log", "txt", "out", "err"])
project_dir = st.text_input("Or project directory (scans for logs)", value=str(Path.cwd()))

col_a, col_b = st.columns(2)
with col_a:
    run_upload = st.button("Analyze upload", type="primary")
with col_b:
    run_project = st.button("Analyze project", type="primary")


def show_payload(payload: dict) -> None:
    results = payload.get("results") or []
    metrics = payload.get("metrics") or {}
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Errors", metrics.get("errors_processed", len(results)))
    c2.metric("LLM OK", metrics.get("llm_success", 0))
    c3.metric("LLM fail", metrics.get("llm_failures", 0))
    c4.metric("Wall (s)", f"{metrics.get('wall_clock_seconds', 0):.2f}")

    for i, item in enumerate(results, 1):
        sev = item.get("severity", "unknown")
        color = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(sev, "⚪")
        with st.expander(f"{color} **#{i}** · {sev.upper()} · {item.get('type', '')}", expanded=i <= 3):
            st.markdown(f"**Error** `{item.get('error', '')[:500]}`")
            st.markdown(f"**Cause:** {item.get('cause', '')}")
            st.markdown(f"**Fix:** {item.get('fix', '')}")
            ctx = item.get("context") or {}
            if ctx.get("file") or ctx.get("line"):
                st.caption(f"📍 {ctx.get('file')}:{ctx.get('line')} {ctx.get('function') or ''}")

            code = (item.get("code") or "").strip()
            if code:
                st.code(code, language="python")

            patch = (item.get("patch") or "").strip()
            if patch:
                st.markdown("**Patch**")
                st.code(patch, language="diff")

    st.download_button(
        "Download JSON (results + metrics)",
        data=json.dumps(payload, ensure_ascii=False, indent=2),
        file_name="analysis.json",
        mime="application/json",
    )


if run_upload and uploaded is not None:
    d = Path(tempfile.mkdtemp())
    (d / "uploaded.log").write_bytes(uploaded.getvalue())
    with st.spinner("Running pipeline…"):
        payload = run_analysis(str(d), use_rag=use_rag, use_llm_classifier=llm_cls)
    st.success(f"Done — {len(payload['results'])} item(s)")
    show_payload(payload)

elif run_project:
    root = Path(project_dir).expanduser().resolve()
    if not root.is_dir():
        st.error("Not a directory")
    else:
        with st.spinner("Running pipeline…"):
            payload = run_analysis(str(root), use_rag=use_rag, use_llm_classifier=llm_cls)
        st.success(f"Done — {len(payload['results'])} item(s)")
        show_payload(payload)
else:
    st.info("Upload a log or choose a project directory, then click **Analyze**.")
