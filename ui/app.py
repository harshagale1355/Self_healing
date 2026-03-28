"""
Streamlit UI — v3 (AI Log Error Analyzer)

New sections per error card:
  • Explainability   : reason (immediate / root / why fix works)
  • Root cause depth : 3-level expandable tree
  • Confidence       : 4 progress bars
  • Fix risk badge   : colour-coded pill
  • Similar cases    : collapsible RAG memory panel
  • Apply Fix        : one-click patch application with backup

Plus: Live Monitoring tab in sidebar.

Run: streamlit run ui/app.py
"""
from __future__ import annotations

import json
import tempfile
import time
import threading
from pathlib import Path

import streamlit as st

import config
from workflows.graph import run_analysis

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AI Log Error Analyzer",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ────────────────────────────────────────────────────────────────
st.markdown(
    """
<style>
/* ── Base ── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

[data-testid="stAppViewContainer"] {
    background: linear-gradient(135deg, #0f0f1a 0%, #13131f 50%, #0a0a14 100%);
    min-height: 100vh;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #141428 0%, #0e0e1e 100%);
    border-right: 1px solid #2a2a45;
}

/* ── Metric tiles ── */
[data-testid="stMetric"] {
    background: linear-gradient(135deg, #1a1a2e 0%, #212140 100%);
    border: 1px solid #2a2a50;
    border-radius: 12px;
    padding: 16px 20px;
}

/* ── Expander ── */
div[data-testid="stExpander"] {
    border: 1px solid #2a2a45;
    border-radius: 10px;
    background: #12122a;
    margin-bottom: 8px;
}

/* ── Custom severity badges ── */
.badge {
    display: inline-block;
    padding: 3px 12px;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
}
.badge-high   { background: #ff2d2d22; color: #ff6b6b; border: 1px solid #ff2d2d55; }
.badge-medium { background: #ffaa0022; color: #ffcc44; border: 1px solid #ffaa0055; }
.badge-low    { background: #00cc4422; color: #44ff88; border: 1px solid #00cc4455; }
.badge-risk-high   { background: #cc000022; color: #ff5555; border: 1px solid #cc000055; }
.badge-risk-medium { background: #aa660022; color: #ffaa33; border: 1px solid #aa660055; }
.badge-risk-low    { background: #006633aa; color: #55ff99; border: 1px solid #00663355; }

/* ── Section divider ── */
.section-title {
    font-size: 0.8rem;
    font-weight: 600;
    color: #8888aa;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin: 12px 0 6px 0;
    border-bottom: 1px solid #2a2a45;
    padding-bottom: 4px;
}

/* ── Similarity chip ── */
.sim-chip {
    display: inline-block;
    background: #1e1e38;
    border: 1px solid #3a3a60;
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 0.72rem;
    color: #9999cc;
    font-family: monospace;
    margin-left: 6px;
}

/* ── Apply Fix button ── */
div[data-testid="stButton"] button {
    border-radius: 8px;
    font-weight: 600;
    transition: all 0.2s ease;
}

/* ── Code blocks ── */
.stCodeBlock { border-radius: 8px !important; border: 1px solid #2a2a45 !important; }

/* ── Info / success / error boxes ── */
div[data-testid="stAlert"] { border-radius: 10px; }
</style>
""",
    unsafe_allow_html=True,
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Options")
    use_rag = st.checkbox("Enable RAG memory (ChromaDB)", value=config.ENABLE_RAG)
    llm_cls = st.checkbox("Use LLM classifier", value=False)
    st.divider()

    st.markdown("### 🔑 LLM Provider")
    provider_label = (
        f"✅ **{config.LLM_PROVIDER.upper()}** — `{config.GROQ_MODEL if config.LLM_PROVIDER == 'groq' else config.OPENAI_MODEL}`"
        if config.has_llm_credentials()
        else "⚠️ No API key — using rule-based fallback"
    )
    st.markdown(provider_label)
    st.caption("Set `GROQ_API_KEY` or `OPENAI_API_KEY` in project `.env`.")
    st.divider()

    # ── Live monitoring ─────────────────────────────────────
    st.markdown("### 📡 Live Monitoring")
    log_watch_path = st.text_input("Log file to watch", placeholder="/var/log/app.log")
    watch_interval = st.slider("Poll interval (s)", 1.0, 10.0, 2.0, 0.5)
    start_watch = st.button("▶ Start Live Monitor", use_container_width=True)
    stop_watch = st.button("⏹ Stop", use_container_width=True)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(
    """
    <div style="padding: 28px 0 8px 0;">
      <h1 style="font-size:2.2rem; font-weight:700; color:#e0e0ff; margin:0;">
        🔍 AI Log Error Analyzer
      </h1>
      <p style="color:#8888aa; margin:6px 0 0 2px; font-size:0.95rem;">
        Codebase-aware debugging · RAG memory · Explainable root cause · One-click fixes
      </p>
    </div>
    """,
    unsafe_allow_html=True,
)
st.divider()

# ── Input section ─────────────────────────────────────────────────────────────
tab_upload, tab_project, tab_monitor = st.tabs(["📁 Upload Log", "📂 Project Directory", "📡 Live Monitor"])

# ── Helper: render confidence breakdown ──────────────────────────────────────

def _conf_color(v: float) -> str:
    if v >= 0.8:
        return "#44ff88"
    if v >= 0.5:
        return "#ffcc44"
    return "#ff6b6b"


def _render_confidence(conf: dict | float) -> None:
    if not isinstance(conf, dict):
        v = float(conf or 0)
        conf = {"overall": v, "pattern_match": v, "llm_reasoning": v, "context_match": v}

    labels = {
        "overall": "Overall",
        "pattern_match": "Pattern Match",
        "llm_reasoning": "LLM Reasoning",
        "context_match": "Context Match",
    }
    for key, label in labels.items():
        val = float(conf.get(key, 0))
        col1, col2, col3 = st.columns([2, 5, 1])
        col1.markdown(f"<span style='color:#9999cc;font-size:0.8rem'>{label}</span>", unsafe_allow_html=True)
        col2.progress(val)
        col3.markdown(
            f"<span style='color:{_conf_color(val)};font-weight:600;font-size:0.85rem'>{val:.0%}</span>",
            unsafe_allow_html=True,
        )


# ── Helper: risk badge ───────────────────────────────────────────────────────

def _risk_badge(level: str) -> str:
    l = (level or "medium").lower()
    cls = f"badge-risk-{l}" if l in ("low", "medium", "high") else "badge-risk-medium"
    icon = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(l, "⚪")
    return f'<span class="badge {cls}">{icon} {l.upper()} RISK</span>'


# ── Helper: severity badge ───────────────────────────────────────────────────

def _sev_badge(sev: str) -> str:
    s = (sev or "unknown").lower()
    cls = f"badge-{s}" if s in ("low", "medium", "high") else "badge"
    icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(s, "⚪")
    return f'<span class="badge {cls}">{icon} {s.upper()}</span>'


# ── Helper: apply patch UI ───────────────────────────────────────────────────

def _render_apply_fix(patch: str, project_path: str, key_suffix: str) -> None:
    if not patch or not patch.strip():
        return
    btn_col, _ = st.columns([2, 5])
    if btn_col.button("⚡ Apply Fix", key=f"apply_{key_suffix}", type="primary"):
        from utils.patch_applier import apply_patch
        result = apply_patch(patch, project_root=project_path)
        if result["success"]:
            st.success(f"✅ {result['message']}")
        else:
            st.error(f"❌ {result['message']}")
            if result.get("backup_path"):
                st.caption(f"Backup created at: `{result['backup_path']}`")


# ── Helper: similar cases panel ──────────────────────────────────────────────

def _render_similar_cases(cases: list[dict]) -> None:
    if not cases:
        return
    st.markdown('<p class="section-title">🔍 Similar Issues Found (RAG Memory)</p>', unsafe_allow_html=True)
    for i, c in enumerate(cases, 1):
        sim = float(c.get("similarity", 0))
        sim_label = f"{sim:.0%}"
        with st.expander(
            f"Match #{i} — similarity {sim_label}",
            expanded=False,
        ):
            err_txt = c.get("error", "")
            fix_txt = c.get("fix", "")
            if err_txt:
                st.markdown(f"**Error:** `{err_txt[:300]}`")
            if fix_txt:
                st.markdown(f"**Past fix:** {fix_txt[:300]}")


# ── Main: render metrics ──────────────────────────────────────────────────────

def _render_metrics(metrics: dict) -> None:
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("🪲 Errors", metrics.get("errors_processed", 0))
    c2.metric("✅ LLM OK", metrics.get("llm_success", 0))
    c3.metric("❌ LLM Fail", metrics.get("llm_failures", 0))
    sr = metrics.get("llm_success", 0) + metrics.get("llm_failures", 0)
    rate = f"{metrics.get('llm_success', 0) / sr:.0%}" if sr else "—"
    c4.metric("📈 Success Rate", rate)
    c5.metric("⏱ Wall (s)", f"{metrics.get('wall_clock_seconds', 0):.2f}")

    sev_hist = metrics.get("errors_by_severity", {})
    if sev_hist:
        st.caption(
            " · ".join(
                f"{s.upper()}: {n}" for s, n in sorted(sev_hist.items())
            )
        )


# ── Main: render single error card ───────────────────────────────────────────

def _render_error_card(index: int, item: dict, project_path: str) -> None:
    sev = item.get("severity", "unknown")
    err_type = item.get("type", "unknown")
    priority = item.get("priority", "—")
    fix_risk = item.get("fix_risk") or {}
    risk_level = fix_risk.get("level", "medium")

    # Card label
    card_label = (
        f"{'🔴' if sev=='high' else '🟡' if sev=='medium' else '🟢'} "
        f"**#{index}** · {err_type.upper()} · Severity: {sev.upper()} · Priority: {priority}"
    )

    with st.expander(card_label, expanded=index <= 2):

        # ── Top badges row ──────────────────────────────────
        badge_cols = st.columns([1, 1, 4])
        badge_cols[0].markdown(_sev_badge(sev), unsafe_allow_html=True)
        badge_cols[1].markdown(_risk_badge(risk_level), unsafe_allow_html=True)

        # ── Error line ──────────────────────────────────────
        err_txt = (item.get("error") or "")[:500]
        if err_txt:
            st.markdown(f"**Error:** `{err_txt}`")

        # ── Location ────────────────────────────────────────
        ctx = item.get("context") or {}
        if ctx.get("file"):
            st.caption(f"📍 `{ctx.get('file')}:{ctx.get('line', '?')}` {ctx.get('function') or ''}")

        st.divider()

        # ── Cause & Fix ─────────────────────────────────────
        col_l, col_r = st.columns(2)
        col_l.markdown("**🔎 Cause**")
        col_l.info(item.get("cause", "") or "—")
        col_r.markdown("**🛠 Fix**")
        col_r.success(item.get("fix", "") or "—")

        # ── Explainability ─────────────────────────────────
        reason = item.get("reason") or {}
        if any(reason.values()):
            st.markdown('<p class="section-title">💡 Explainability</p>', unsafe_allow_html=True)
            e_c1, e_c2, e_c3 = st.columns(3)
            e_c1.markdown("**Immediate Trigger**")
            e_c1.markdown(reason.get("immediate") or "—")
            e_c2.markdown("**Root Cause**")
            e_c2.markdown(reason.get("root") or "—")
            e_c3.markdown("**Why Fix Works**")
            e_c3.markdown(reason.get("why_fix_works") or "—")

        # ── Root cause depth ────────────────────────────────
        rc = item.get("root_cause") or {}
        if any(rc.values()):
            with st.expander("🌱 Root Cause — Multi-Layer Analysis", expanded=False):
                rc_col1, rc_col2, rc_col3 = st.columns(3)
                rc_col1.markdown("**Level 1 — Immediate Error**")
                rc_col1.warning(rc.get("level_1") or "—")
                rc_col2.markdown("**Level 2 — Code Issue**")
                rc_col2.warning(rc.get("level_2") or "—")
                rc_col3.markdown("**Level 3 — Design Issue**")
                rc_col3.warning(rc.get("level_3") or "—")

        # ── Fix risk ────────────────────────────────────────
        if fix_risk.get("reason"):
            st.markdown('<p class="section-title">⚠️ Fix Risk</p>', unsafe_allow_html=True)
            risk_col1, risk_col2 = st.columns([1, 4])
            risk_col1.markdown(_risk_badge(risk_level), unsafe_allow_html=True)
            risk_col2.markdown(fix_risk.get("reason", ""))

        # ── Confidence breakdown ─────────────────────────────
        conf = item.get("confidence")
        if conf:
            st.markdown('<p class="section-title">📊 Confidence Breakdown</p>', unsafe_allow_html=True)
            _render_confidence(conf)

        # ── Code suggestion ─────────────────────────────────
        code_txt = (item.get("code") or "").strip()
        if code_txt:
            st.markdown('<p class="section-title">💻 Suggested Code</p>', unsafe_allow_html=True)
            st.code(code_txt, language="python")

        # ── Patch ───────────────────────────────────────────
        patch_txt = (item.get("patch") or "").strip()
        if patch_txt:
            st.markdown('<p class="section-title">📋 Patch (diff)</p>', unsafe_allow_html=True)
            st.code(patch_txt, language="diff")
            _render_apply_fix(patch_txt, project_path, key_suffix=f"{index}_{hash(err_txt)}")

        # ── Validation notes ────────────────────────────────
        val = item.get("validation") or {}
        if val.get("notes"):
            st.caption(f"🔬 Validation: {val.get('notes')}")

        # ── Similar cases (RAG memory) ───────────────────────
        sim_cases = item.get("similar_cases") or []
        _render_similar_cases(sim_cases)

        st.divider()


# ── Main payload renderer ─────────────────────────────────────────────────────

def show_payload(payload: dict, project_path: str) -> None:
    results = payload.get("results") or []
    metrics = payload.get("metrics") or {}

    _render_metrics(metrics)
    st.divider()

    if not results:
        st.info("No errors found in the provided logs.")
        return

    st.markdown(f"### Found **{len(results)}** error(s)")
    for i, item in enumerate(results, 1):
        _render_error_card(i, item, project_path)

    # Download button
    st.download_button(
        "⬇️ Download Full Report (JSON)",
        data=json.dumps(payload, ensure_ascii=False, indent=2),
        file_name="analysis_report.json",
        mime="application/json",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tab: Upload log
# ─────────────────────────────────────────────────────────────────────────────
with tab_upload:
    st.markdown("##### Upload a log file to analyse")
    uploaded = st.file_uploader(
        "Log file", type=["log", "txt", "out", "err"], label_visibility="collapsed"
    )
    if uploaded:
        run_btn = st.button("🚀 Analyse Uploaded Log", type="primary", key="btn_upload")
        if run_btn:
            d = Path(tempfile.mkdtemp())
            log_file = d / "uploaded.log"
            log_file.write_bytes(uploaded.getvalue())
            with st.spinner("Running analysis pipeline…"):
                payload = run_analysis(str(d), use_rag=use_rag, use_llm_classifier=llm_cls)
            st.success(f"Done — {len(payload['results'])} item(s) found")
            show_payload(payload, str(d))
    else:
        st.info("Upload a `.log`, `.txt`, `.out`, or `.err` file to get started.")

# ─────────────────────────────────────────────────────────────────────────────
# Tab: Project directory
# ─────────────────────────────────────────────────────────────────────────────
with tab_project:
    st.markdown("##### Scan a project directory for log files")
    project_dir = st.text_input(
        "Project path",
        value=str(Path.cwd()),
        label_visibility="collapsed",
    )
    run_project = st.button("🚀 Analyse Project", type="primary", key="btn_project")
    if run_project:
        root = Path(project_dir).expanduser().resolve()
        if not root.is_dir():
            st.error(f"Not a valid directory: `{root}`")
        else:
            with st.spinner("Scanning and analysing…"):
                payload = run_analysis(str(root), use_rag=use_rag, use_llm_classifier=llm_cls)
            st.success(f"Done — {len(payload['results'])} item(s) found")
            show_payload(payload, str(root))

# ─────────────────────────────────────────────────────────────────────────────
# Tab: Live Monitor
# ─────────────────────────────────────────────────────────────────────────────
with tab_monitor:
    st.markdown("##### Real-time log file monitoring")
    monitor_file = st.text_input(
        "Log file path to monitor",
        value=log_watch_path or "",
        placeholder="/var/log/app.log",
        key="monitor_file_input",
    )
    mon_interval = st.slider("Poll interval (seconds)", 1.0, 30.0, watch_interval, 0.5, key="mon_interval")
    mon_rag = st.checkbox("Enable RAG in monitor", value=use_rag, key="mon_rag")

    mon_col1, mon_col2 = st.columns(2)
    start_mon = mon_col1.button("▶ Start Monitoring", type="primary", key="start_mon")
    stop_mon = mon_col2.button("⏹ Stop Monitoring", key="stop_mon")

    live_container = st.empty()

    if "monitoring_active" not in st.session_state:
        st.session_state["monitoring_active"] = False
    if "monitor_results" not in st.session_state:
        st.session_state["monitor_results"] = []

    if start_mon and monitor_file:
        p = Path(monitor_file).resolve()
        if not p.is_file():
            st.error(f"File not found: `{p}`")
        else:
            st.session_state["monitoring_active"] = True
            st.session_state["monitor_results"] = []
            st.info(f"👁 Watching `{p}` every {mon_interval}s — keep this tab open.")
            pos = p.stat().st_size
            seen: set[str] = set()

            # Polling loop — runs synchronously in Streamlit's execution context
            # (Ctrl+C or Stop button breaks it)
            while st.session_state.get("monitoring_active", False):
                time.sleep(mon_interval)
                try:
                    sz = p.stat().st_size
                except OSError:
                    continue
                if sz <= pos:
                    continue
                try:
                    with p.open("rb") as f:
                        f.seek(pos)
                        chunk = f.read().decode("utf-8", errors="replace")
                    pos = sz
                except OSError:
                    continue
                if not chunk.strip():
                    continue

                with tempfile.TemporaryDirectory() as d:
                    tmp_log = Path(d) / "watch.log"
                    tmp_log.write_text(chunk, encoding="utf-8")
                    payload = run_analysis(d, use_rag=mon_rag)

                for item in payload.get("results", []):
                    err_key = item.get("error", "")
                    if err_key and err_key not in seen:
                        seen.add(err_key)
                        st.session_state["monitor_results"].insert(0, item)

                with live_container.container():
                    st.markdown(f"**{len(st.session_state['monitor_results'])} new error(s) detected**")
                    for idx, itm in enumerate(st.session_state["monitor_results"][:20], 1):
                        _render_error_card(idx, itm, str(p.parent))

    if stop_mon:
        st.session_state["monitoring_active"] = False
        st.success("Monitoring stopped.")

    if not monitor_file:
        st.info("Enter a log file path above and press **Start Monitoring**.")

    # Show buffered results if any
    if st.session_state.get("monitor_results") and not st.session_state.get("monitoring_active"):
        with live_container.container():
            st.markdown(f"**Last session: {len(st.session_state['monitor_results'])} error(s)**")
            for idx, itm in enumerate(st.session_state["monitor_results"][:20], 1):
                _render_error_card(idx, itm, ".")
