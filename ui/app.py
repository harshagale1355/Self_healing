"""
Streamlit UI: upload or select project, view errors and suggested fixes.
Run: streamlit run ui/app.py
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import streamlit as st

import config
from workflows.graph import run_analysis


st.set_page_config(page_title="AI Log Error Analyzer", layout="wide")
st.title("AI-Powered Log Error Analyzer")
st.caption("Analyze logs, classify errors, and get suggested fixes (JSON output).")

with st.sidebar:
    st.subheader("Options")
    use_rag = st.checkbox("Enable RAG (Chroma)", value=config.ENABLE_RAG)
    llm_cls = st.checkbox("LLM classifier", value=False)
    st.markdown("Set `OPENAI_API_KEY` or `GROQ_API_KEY` for full LLM analysis.")

uploaded = st.file_uploader("Upload a log file", type=["log", "txt", "out", "err"])
project_dir = st.text_input("Or enter project directory path (scans for logs)", value=str(Path.cwd()))

col_a, col_b = st.columns(2)
with col_a:
    run_upload = st.button("Analyze uploaded file")
with col_b:
    run_project = st.button("Analyze project directory")

if run_upload and uploaded is not None:
    d = Path(tempfile.mkdtemp())
    (d / "uploaded.log").write_bytes(uploaded.getvalue())
    with st.spinner("Running pipeline…"):
        results = run_analysis(str(d), use_rag=use_rag, use_llm_classifier=llm_cls)
    st.success(f"Found {len(results)} result(s)")
    st.json(results)
    st.download_button(
        "Download JSON",
        data=json.dumps(results, ensure_ascii=False, indent=2),
        file_name="analysis.json",
        mime="application/json",
    )

elif run_project:
    root = Path(project_dir).expanduser().resolve()
    if not root.is_dir():
        st.error("Not a directory")
    else:
        with st.spinner("Running pipeline…"):
            results = run_analysis(str(root), use_rag=use_rag, use_llm_classifier=llm_cls)
        st.success(f"Found {len(results)} result(s)")
        st.json(results)
        st.download_button(
            "Download JSON",
            data=json.dumps(results, ensure_ascii=False, indent=2),
            file_name="analysis.json",
            mime="application/json",
        )
else:
    st.info("Upload a log file or enter a project path and click Analyze.")
