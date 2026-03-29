"""
Flet Desktop App — AI Log Error Analyzer

A native desktop application replacing the Streamlit UI.
Features:  Material Design / Dark Mode, Tabs, Interactive Error Cards, Settings Drawer, Apply Fix, Download JSON.
"""
from __future__ import annotations

import json
import os
import sys
import shutil
import tempfile
import threading
import time
from pathlib import Path

# Add project root to sys.path so we can import modules
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    # Running in a bundled PyInstaller folder
    PROJECT_ROOT = Path(sys._MEIPASS)
else:
    # Running in normal Python environment
    PROJECT_ROOT = Path(__file__).resolve().parent.parent

sys.path.append(str(PROJECT_ROOT))

import flet as ft

import config
from utils.patch_applier import apply_patch
from workflows.graph import run_analysis

# ── Modern Design Tokens ───────────────────────────────────────────────────────

class AppColors:
    BG_DARK = "#0B0E14"          # Deep Space Zinc
    SURFACE_DARK = "#151921"     # Lighter Zinc
    ACCENT_INDIGO = "#6366F1"    # Indigo-500
    ACCENT_VIOLET = "#8B5CF6"    # Violet-500
    TEXT_PRIMARY = "#F8FAFC"     # Slate-50
    TEXT_SECONDARY = "#94A3B8"   # Slate-400
    TEXT_MUTED = "#64748B"       # Slate-500
    
    # Severity & Risk
    HIGH = "#EF4444"             # Red-500
    MEDIUM = "#F59E0B"           # Amber-500
    LOW = "#10B981"              # Emerald-500
    SUCCESS = "#10B981"
    ERROR = "#EF4444"

# ── Global UI Helpers ──────────────────────────────────────────────────────────

def _sev_badge(sev: str) -> ft.Container:
    s = (sev or "unknown").lower()
    color = AppColors.HIGH if s == "high" else AppColors.MEDIUM if s == "medium" else AppColors.LOW if s == "low" else AppColors.TEXT_MUTED
    return ft.Container(
        content=ft.Text(f"{s.upper()}", size=10, weight="bold", color=color),
        padding=ft.padding.symmetric(horizontal=12, vertical=4),
        border_radius=30,
        bgcolor=f"{color}15",
        border=ft.border.all(1, f"{color}40"),
    )

def _risk_badge(level: str) -> ft.Container:
    l = (level or "medium").lower()
    color = AppColors.HIGH if l == "high" else AppColors.MEDIUM if l == "medium" else AppColors.LOW if l == "low" else AppColors.TEXT_MUTED
    return ft.Container(
        content=ft.Row([
            ft.Icon(ft.Icons.SHIELD_OUTLINED, size=12, color=color),
            ft.Text(f"{l.upper()} RISK", size=10, weight="bold", color=color),
        ], spacing=5, tight=True),
        padding=ft.padding.symmetric(horizontal=12, vertical=4),
        border_radius=30,
        bgcolor=f"{color}15",
        border=ft.border.all(1, f"{color}40"),
    )

def _section_title(text: str) -> ft.Text:
    return ft.Text(
        text.upper(),
        size=11,
        weight="bold",
        color=AppColors.TEXT_MUTED,
    )


# ── Main Flet App ──────────────────────────────────────────────────────────────

def main(page: ft.Page):
    # Base page settings
    page.title = "AI Log Error Analyzer"
    page.bgcolor = AppColors.BG_DARK
    page.theme_mode = ft.ThemeMode.DARK
    page.theme = ft.Theme(
        color_scheme_seed=AppColors.ACCENT_INDIGO,
        font_family="Inter, system-ui, sans-serif",
    )
    page.padding = 30
    page.scroll = ft.ScrollMode.ADAPTIVE

    # State variables
    state = {
        "use_rag": config.ENABLE_RAG,
        "use_llm_cls": False,
        "monitor_active": False,
        "monitor_results": [],
    }

    # ── App Bar / Header ──────────────────────────────────────────────────────

    def open_settings(e):
        page.end_drawer.open = True
        page.update()
        
    def save_api_key(e):
        val = settings_api_key.value.strip()
        if val:
            if val.startswith("gsk_"):
                os.environ["GROQ_API_KEY"] = val
                config.GROQ_API_KEY = val
                config.LLM_PROVIDER = "groq"
            elif val.startswith("sk-"):
                os.environ["OPENAI_API_KEY"] = val
                config.OPENAI_API_KEY = val
                config.LLM_PROVIDER = "openai"
        page.end_drawer.open = False
        update_provider_label()
        
    settings_api_key = ft.TextField(
        label="API Key (Groq or OpenAI)", 
        password=True, 
        can_reveal_password=True,
    )

    settings_drawer = ft.NavigationDrawer(
        bgcolor=AppColors.SURFACE_DARK,
        indicator_color=f"{AppColors.ACCENT_INDIGO}30",
        controls=[
            ft.Container(
                content=ft.Text("Settings", size=20, weight="w800", color=AppColors.TEXT_PRIMARY),
                padding=20,
            ),
            ft.Divider(color=f"{AppColors.TEXT_MUTED}20"),
            ft.Container(
                content=ft.Column([
                    ft.Text("API CONFIGURATION", size=10, weight="bold", color=AppColors.TEXT_MUTED),
                    settings_api_key,
                    ft.FilledButton(
                        "Save Key", 
                        on_click=save_api_key,
                        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8), bgcolor=AppColors.ACCENT_INDIGO)
                    ),
                    ft.Text("Saved keys are stored in memory for this session.", color=AppColors.TEXT_MUTED, size=11),
                ], spacing=15),
                padding=20,
            ),
            ft.Divider(color=f"{AppColors.TEXT_MUTED}20"),
            ft.Container(
                content=ft.Column([
                    ft.Text("ADVANCED OPTIONS", size=10, weight="bold", color=AppColors.TEXT_MUTED),
                    ft.Switch(
                        label="Enable RAG memory", 
                        value=state["use_rag"], 
                        active_color=AppColors.ACCENT_INDIGO,
                        on_change=lambda e: state.update({"use_rag": e.control.value})
                    ),
                    ft.Switch(
                        label="LLM Classification", 
                        value=state["use_llm_cls"],
                        active_color=AppColors.ACCENT_INDIGO,
                        on_change=lambda e: state.update({"use_llm_cls": e.control.value})
                    ),
                ], spacing=10),
                padding=20,
            ),
        ]
    )
    page.end_drawer = settings_drawer

    provider_label_text = ft.Text("Provider Label", size=12, color=ft.Colors.BLUE_GREY_300)

    def update_provider_label():
        if config.has_llm_credentials():
            provider_label_text.value = f"✅ {config.LLM_PROVIDER.upper()} Active"
        else:
            provider_label_text.value = "⚠️ Rule-based Fallback (No Key)"
        page.update()

    update_provider_label()

    page.appbar = ft.AppBar(
        title=ft.Row([
            ft.Container(
                content=ft.Icon(ft.Icons.SEARCH, size=28, color=AppColors.ACCENT_INDIGO),
                padding=10,
                border_radius=12,
                bgcolor=f"{AppColors.ACCENT_INDIGO}15",
            ),
            ft.Text("AI Log Error Analyzer", size=22, weight="w800"),
        ], spacing=15),
        center_title=False,
        bgcolor=f"{AppColors.BG_DARK}E6", # 90% opacity for glass effect
        # toolbar_height=80,
        actions=[
            ft.Container(
                content=ft.Row([
                    ft.Container(
                        width=8, height=8, border_radius=4,
                        bgcolor=AppColors.SUCCESS if config.has_llm_credentials() else AppColors.MEDIUM
                    ),
                    provider_label_text,
                ], spacing=8),
                padding=ft.padding.symmetric(horizontal=15, vertical=8),
                bgcolor=f"{AppColors.SURFACE_DARK}",
                border_radius=20,
                margin=ft.margin.only(right=10),
            ),
            ft.IconButton(
                ft.Icons.SETTINGS, 
                on_click=open_settings, 
                tooltip="Settings",
            ),
            ft.Container(width=20),
        ],
    )

    # ── Reusable Component Rendering ──────────────────────────────────────────

    def render_metrics(metrics: dict) -> ft.Row:
        def _metric_card(label: str, value: str, icon: str, color: str):
            return ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Icon(icon, size=18, color=color),
                        ft.Text(label, size=11, color=AppColors.TEXT_MUTED, weight="bold"),
                    ], spacing=10),
                    ft.Text(str(value), size=28, weight="w800", color=AppColors.TEXT_PRIMARY),
                ], spacing=8),
                padding=20,
                width=180,
                bgcolor=AppColors.SURFACE_DARK,
                border_radius=16,
                border=ft.border.all(1, f"{AppColors.TEXT_MUTED}20"),
                shadow=ft.BoxShadow(
                    spread_radius=1, blur_radius=10, 
                    color=ft.Colors.with_opacity(0.1, ft.Colors.BLACK),
                    offset=ft.Offset(0, 4)
                ),
            )

        errs = metrics.get("errors_processed", 0)
        succ = metrics.get("llm_success", 0)
        fail = metrics.get("llm_failures", 0)
        rate = f"{succ / (succ + fail):.0%}" if (succ + fail) > 0 else "—"
        wall = f"{metrics.get('wall_clock_seconds', 0):.2f}s"

        return ft.Row([
            _metric_card("ERRORS", errs, ft.Icons.BUG_REPORT, AppColors.ERROR),
            _metric_card("LLM OK", succ, ft.Icons.CHECK_CIRCLE, AppColors.SUCCESS),
            _metric_card("LLM FAIL", fail, ft.Icons.CANCEL, AppColors.ERROR),
            _metric_card("SUCCESS RATE", rate, ft.Icons.INSIGHTS, AppColors.ACCENT_INDIGO),
            _metric_card("WALL TIME", wall, ft.Icons.TIMER, AppColors.ACCENT_VIOLET),
        ], wrap=True, spacing=15)

    def render_confidence(conf: dict | float) -> ft.Column:
        if not isinstance(conf, dict):
            v = float(conf or 0)
            conf = {"overall": v, "pattern_match": v, "llm_reasoning": v, "context_match": v}

        rows = []
        labels = {
            "overall": "OVERALL",
            "pattern_match": "PATTERN MATCH",
            "llm_reasoning": "LLM REASONING",
            "context_match": "CONTEXT MATCH",
        }
        for key, label in labels.items():
            val = float(conf.get(key, 0))
            color = AppColors.SUCCESS if val >= 0.8 else AppColors.MEDIUM if val >= 0.5 else AppColors.ERROR
            rows.append(
                ft.Row([
                    ft.Text(label, width=120, size=10, weight="bold", color=AppColors.TEXT_MUTED),
                    ft.ProgressBar(value=val, width=200, color=color, bgcolor=f"{AppColors.TEXT_MUTED}20", height=8, border_radius=4),
                    ft.Text(f"{val:.0%}", width=50, size=11, weight="bold", color=color),
                ], spacing=15)
            )
        return ft.Column(rows, spacing=10)

    def create_error_card(index: int, item: dict, project_path: str) -> ft.Container:
        sev = item.get("severity", "unknown")
        err_type = item.get("type", "unknown")
        priority = item.get("priority", "—")
        fix_risk = item.get("fix_risk") or {}
        risk_level = fix_risk.get("level", "medium")
        
        sev_color = AppColors.HIGH if sev == "high" else AppColors.MEDIUM if sev == "medium" else AppColors.LOW if sev == "low" else AppColors.TEXT_MUTED

        card_title = f"#{index} · {err_type.upper()}"
        
        # Header area
        header_row = ft.Row([
            _sev_badge(sev),
            _risk_badge(risk_level),
            ft.VerticalDivider(width=1, color=f"{AppColors.TEXT_MUTED}20"),
            ft.Text(f"PRIORITY {priority}", size=10, weight="bold", color=AppColors.TEXT_MUTED),
        ], spacing=15)

        err_txt = (item.get("error") or "")[:500]
        err_display = ft.Container(
            content=ft.Text(err_txt, font_family="monospace", size=13, color=AppColors.TEXT_PRIMARY),
            bgcolor=f"{AppColors.BG_DARK}",
            padding=15,
            border_radius=8,
            border=ft.border.all(1, f"{AppColors.TEXT_MUTED}20"),
        )

        ctx = item.get("context") or {}
        ctx_text = ""
        if ctx.get("file"):
            ctx_text = f"{ctx.get('file')}:{ctx.get('line', '?')} → {ctx.get('function') or ''}"

        cause_col = ft.Column([
            _section_title("🔎 CAUSE"), 
            ft.Text(item.get("cause", "") or "—", color=AppColors.TEXT_SECONDARY, size=13)
        ], expand=1, spacing=10)
        
        fix_col = ft.Column([
            _section_title("🛠 SUGGESTED FIX"), 
            ft.Text(item.get("fix", "") or "—", color=AppColors.TEXT_SECONDARY, size=13)
        ], expand=1, spacing=10)

        reason = item.get("reason") or {}
        explain_area = None
        if any(reason.values()):
            explain_area = ft.Container(
                content=ft.Column([
                    _section_title("💡 EXPLAINABILITY"),
                    ft.Row([
                        ft.Column([ft.Text("IMMEDIATE TRIGGER", weight="bold", size=10, color=AppColors.TEXT_MUTED), ft.Text(reason.get("immediate") or "—", size=12, color=AppColors.TEXT_SECONDARY)], expand=1, spacing=5),
                        ft.Column([ft.Text("ROOT CAUSE", weight="bold", size=10, color=AppColors.TEXT_MUTED), ft.Text(reason.get("root") or "—", size=12, color=AppColors.TEXT_SECONDARY)], expand=1, spacing=5),
                        ft.Column([ft.Text("WHY IT WORKS", weight="bold", size=10, color=AppColors.TEXT_MUTED), ft.Text(reason.get("why_fix_works") or "—", size=12, color=AppColors.TEXT_SECONDARY)], expand=1, spacing=5),
                    ], alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.START, spacing=20)
                ], spacing=15),
                padding=20,
                bgcolor=f"{AppColors.ACCENT_INDIGO}08",
                border_radius=12,
            )

        patch_txt = (item.get("patch") or "").strip()
        patch_controls = []
        if patch_txt:
            patch_controls.append(_section_title("📋 PATCH DIFF"))
            patch_controls.append(ft.Container(
                content=ft.Text(patch_txt, font_family="monospace", size=11, color=AppColors.TEXT_PRIMARY),
                bgcolor=ft.Colors.with_opacity(0.3, ft.Colors.BLACK),
                padding=15,
                border_radius=8,
                border=ft.border.all(1, f"{AppColors.ACCENT_INDIGO}30"),
            ))
            
            def apply_fix_click(e, patch=patch_txt, proj=project_path):
                e.control.disabled = True
                e.control.content = ft.ProgressRing(width=16, height=16, color=AppColors.TEXT_PRIMARY)
                page.update()
                
                res = apply_patch(patch, project_root=proj)
                e.control.content = ft.Row([ft.Icon(ft.Icons.BOLT), ft.Text("Apply Fix")], spacing=10, tight=True)
                e.control.disabled = False
                
                if res["success"]:
                    page.snack_bar = ft.SnackBar(ft.Text(f"✅ {res['message']}"), bgcolor=AppColors.SUCCESS)
                else:
                    page.snack_bar = ft.SnackBar(ft.Text(f"❌ {res['message']}"), bgcolor=AppColors.ERROR)
                page.snack_bar.open = True
                page.update()

            patch_controls.append(ft.Container(
                content=ft.Row([ft.Icon(ft.Icons.BOLT), ft.Text("Apply Fix")], spacing=10, tight=True),
                padding=ft.padding.symmetric(horizontal=20, vertical=12),
                bgcolor=AppColors.ACCENT_INDIGO,
                border_radius=8,
                on_click=apply_fix_click,
            ))

        code_txt = (item.get("code") or "").strip()
        code_controls = []
        if code_txt:
            code_controls.append(_section_title("💻 SUGGESTED CODE"))
            code_controls.append(ft.Container(
                content=ft.Text(code_txt, font_family="monospace", size=11, color=AppColors.TEXT_PRIMARY),
                bgcolor=ft.Colors.with_opacity(0.3, ft.Colors.BLACK),
                padding=15,
                border_radius=8,
                border=ft.border.all(1, f"{AppColors.TEXT_MUTED}30"),
            ))

        sim_cases = item.get("similar_cases") or []
        sim_controls = []
        if sim_cases:
            sim_controls.append(_section_title(f"🔍 RAG MEMORY (SIMILAR ISSUES)"))
            for i, c in enumerate(sim_cases, 1):
                sim = float(c.get("similarity", 0))
                sim_controls.append(
                    ft.ExpansionTile(
                        title=ft.Text(f"Match #{i} — {sim:.0%} Similarity", size=12, weight="bold"),
                        controls_padding=15,
                        collapsed_text_color=AppColors.TEXT_SECONDARY,
                        text_color=AppColors.ACCENT_INDIGO,
                        controls=[
                            ft.Column([
                                ft.Text("PAST ERROR", size=10, weight="bold", color=AppColors.TEXT_MUTED),
                                ft.Text(c.get('error', '')[:300], size=11, color=AppColors.TEXT_SECONDARY),
                                ft.Text("PAST FIX", size=10, weight="bold", color=AppColors.TEXT_MUTED),
                                ft.Text(c.get('fix', '')[:300], size=11, color=AppColors.TEXT_SECONDARY),
                            ], spacing=8)
                        ]
                    )
                )

        body_controls = [
            header_row,
            err_display,
        ]
        if ctx_text:
            body_controls.append(ft.Row([
                ft.Icon(ft.Icons.LOCATION_ON, size=14, color=AppColors.TEXT_MUTED),
                ft.Text(ctx_text, size=11, color=AppColors.TEXT_MUTED, font_family="monospace"),
            ], spacing=5))
        
        body_controls.extend([
            ft.Divider(height=20, color=f"{AppColors.TEXT_MUTED}10"),
            ft.Row([cause_col, fix_col], alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.START, spacing=30),
        ])
        
        if explain_area:
            body_controls.extend([ft.Divider(height=20, color="transparent"), explain_area])
            
        body_controls.extend([
            ft.Divider(height=20, color=f"{AppColors.TEXT_MUTED}10"),
            _section_title("📊 CONFIDENCE SCORE"),
            render_confidence(item.get("confidence")),
        ])

        if code_controls:
            body_controls.extend([ft.Divider(height=30, color="transparent")] + code_controls)
            
        if patch_controls:
            body_controls.extend([ft.Divider(height=30, color="transparent")] + patch_controls)
            
        if sim_controls:
            body_controls.extend([ft.Divider(height=30, color="transparent")] + sim_controls)

        return ft.Container(
            content=ft.ExpansionTile(
                title=ft.Text(card_title, weight="w700", size=15, color=AppColors.TEXT_PRIMARY),
                subtitle=ft.Text(f"Severity: {sev.upper()}", size=11, color=AppColors.TEXT_MUTED),
                initially_expanded=(index <= 1),
                controls_padding=25,
                collapsed_text_color=AppColors.TEXT_PRIMARY,
                text_color=AppColors.ACCENT_INDIGO,
                icon_color=AppColors.TEXT_MUTED,
                controls=[ft.Column(body_controls, spacing=15)]
            ),
            bgcolor=AppColors.SURFACE_DARK,
            border_radius=16,
            border=ft.border.only(left=ft.BorderSide(4, sev_color)),
            margin=ft.margin.only(bottom=15),
        )

    # ── Upload Log Tab ────────────────────────────────────────────────────────
    
    upload_results = ft.Column()
    
    def on_file_picked(e: ft.FilePickerResultEvent):
        if not e.files: return
        fpath = e.files[0].path
        run_analysis_action(fpath, is_dir=False, results_container=upload_results)

    file_picker = ft.FilePicker(on_result=on_file_picked)
    page.overlay.append(file_picker)

    tab_upload = ft.Container(
        content=ft.Column([
            ft.Container(
                content=ft.Column([
                    _section_title("SELECT LOG FILE"),
                    ft.Text("Upload a local log file (.log, .txt) to start deep analysis.", color=AppColors.TEXT_SECONDARY, size=13),
                    ft.Container(height=10),
                    ft.FilledButton(
                        "Browse and Analyse", 
                        icon=ft.Icons.UPLOAD_FILE,
                        on_click=lambda _: file_picker.pick_files(allow_multiple=False),
                        height=50,
                        style=ft.ButtonStyle(
                            bgcolor=AppColors.ACCENT_INDIGO,
                            shape=ft.RoundedRectangleBorder(radius=12)
                        )
                    ),
                ], spacing=5),
                padding=30,
                bgcolor=AppColors.SURFACE_DARK,
                border_radius=20,
                border=ft.border.all(1, f"{AppColors.TEXT_MUTED}20"),
            ),
            ft.Container(height=20),
            upload_results,
        ]),
        padding=ft.padding.only(top=20),
    )

    # ── Project Directory Tab ──────────────────────────────────────────────────
    
    project_results = ft.Column()
    project_dir_input = ft.TextField(
        label="Project Path", 
        value=str(Path.cwd()), 
        expand=True,
    )
    
    def on_project_dir_picked(e: ft.FilePickerResultEvent):
        if e.path:
            project_dir_input.value = e.path
            project_dir_input.update()

    dir_picker = ft.FilePicker(on_result=on_project_dir_picked)
    page.overlay.append(dir_picker)

    def analyze_project_click(e):
        run_analysis_action(project_dir_input.value, is_dir=True, results_container=project_results)

    tab_project = ft.Container(
        content=ft.Column([
            ft.Container(
                content=ft.Column([
                    _section_title("SCAN DIRECTORY"),
                    ft.Text("Select a folder to scan for all relevant log files.", color=AppColors.TEXT_SECONDARY, size=13),
                    ft.Container(height=10),
                    ft.Row([
                        project_dir_input,
                        ft.IconButton(
                            ft.Icons.FOLDER_OPEN, 
                            on_click=lambda _: dir_picker.get_directory_path(),
                            icon_color=AppColors.ACCENT_INDIGO,
                        ),
                    ], spacing=10),
                    ft.Container(height=10),
                    ft.FilledButton(
                        "Start Batch Analysis", 
                        icon=ft.Icons.PLAY_CIRCLE_FILLED,
                        on_click=analyze_project_click,
                        height=50,
                        style=ft.ButtonStyle(
                            bgcolor=AppColors.ACCENT_INDIGO,
                            shape=ft.RoundedRectangleBorder(radius=12)
                        )
                    ),
                ], spacing=5),
                padding=30,
                bgcolor=AppColors.SURFACE_DARK,
                border_radius=20,
                border=ft.border.all(1, f"{AppColors.TEXT_MUTED}20"),
            ),
            ft.Container(height=20),
            project_results,
        ]),
        padding=ft.padding.only(top=20),
    )

    # ── Live Monitor Tab ───────────────────────────────────────────────────────
    
    monitor_results_col = ft.Column()
    monitor_status = ft.Text("Not monitoring", color=ft.Colors.BLUE_GREY_400)
    monitor_file_input = ft.TextField(label="Log file to monitor", hint_text="/var/log/syslog", expand=True)
    monitor_interval = ft.Slider(min=1.0, max=10.0, value=2.0, divisions=18, label="Poll interval: {value}s")

    def monitor_loop():
        p = Path(monitor_file_input.value).resolve()
        pos = p.stat().st_size
        seen = set()
        
        while state["monitor_active"]:
            time.sleep(monitor_interval.value)
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
                # Blocking call, but running in thread
                payload = run_analysis(d, use_rag=state["use_rag"])

            new_results = []
            for item in payload.get("results", []):
                err_key = item.get("error", "")
                if err_key and err_key not in seen:
                    seen.add(err_key)
                    new_results.append(item)
                    state["monitor_results"].insert(0, item)

            if new_results:
                def update_mon_ui():
                    monitor_status.value = f"Watching {p.name}... Found {len(state['monitor_results'])} total errors."
                    monitor_results_col.controls.clear()
                    for idx, itm in enumerate(state["monitor_results"][:20], 1):
                        monitor_results_col.controls.append(create_error_card(idx, itm, str(p.parent)))
                    page.update()
                
                update_mon_ui()

    def btn_start_monitor(e):
        if not monitor_file_input.value:
            return
        p = Path(monitor_file_input.value).resolve()
        if not p.is_file():
            page.snack_bar = ft.SnackBar(ft.Text(f"File not found: {p}"), bgcolor=ft.Colors.RED_800)
            page.snack_bar.open = True
            page.update()
            return
            
        state["monitor_active"] = True
        state["monitor_results"] = []
        monitor_results_col.controls.clear()
        monitor_status.value = f"👁 Watching `{p.name}` every {monitor_interval.value}s..."
        monitor_status.color = ft.Colors.GREEN_400
        btn_start.disabled = True
        btn_stop.disabled = False
        page.update()
        
        threading.Thread(target=monitor_loop, daemon=True).start()

    def btn_stop_monitor(e):
        state["monitor_active"] = False
        monitor_status.value = "Monitoring stopped."
        monitor_status.color = ft.Colors.BLUE_GREY_400
        btn_start.disabled = False
        btn_stop.disabled = True
        page.update()

    btn_start = ft.ElevatedButton("▶ Start Monitoring", on_click=btn_start_monitor, color=ft.Colors.WHITE, bgcolor=ft.Colors.BLUE_700)
    btn_stop = ft.ElevatedButton("⏹ Stop", on_click=btn_stop_monitor, disabled=True)

    tab_monitor = ft.Container(
        content=ft.Column([
            ft.Container(
                content=ft.Column([
                    _section_title("LIVE LOG STREAMING"),
                    ft.Text("Watch a log file in real-time. New errors will appear instantly.", color=AppColors.TEXT_SECONDARY, size=13),
                    ft.Container(height=10),
                    ft.Row([monitor_file_input, monitor_interval], spacing=20),
                    ft.Row([
                        btn_start, 
                        btn_stop, 
                        ft.VerticalDivider(width=1, color=f"{AppColors.TEXT_MUTED}20"),
                        monitor_status
                    ], spacing=20),
                ], spacing=10),
                padding=30,
                bgcolor=AppColors.SURFACE_DARK,
                border_radius=20,
                border=ft.border.all(1, f"{AppColors.TEXT_MUTED}20"),
            ),
            ft.Divider(height=40, color="transparent"),
            monitor_results_col,
        ]),
        padding=ft.padding.only(top=20),
    )

    # ── Shared Action Logic ────────────────────────────────────────────────────
    
    current_payload_json = ""
    
    def save_json_result(e: ft.FilePickerResultEvent):
        if e.path and current_payload_json:
            try:
                Path(e.path).write_text(current_payload_json, encoding="utf-8")
                page.snack_bar = ft.SnackBar(ft.Text("Report saved successfully."), bgcolor=ft.Colors.GREEN_800)
            except Exception as ex:
                page.snack_bar = ft.SnackBar(ft.Text(f"Error saving: {ex}"), bgcolor=ft.Colors.RED_800)
            page.snack_bar.open = True
            page.update()

    save_picker = ft.FilePicker(on_result=save_json_result)
    page.overlay.append(save_picker)

    def btn_download_click(e):
        save_picker.save_file(dialog_title="Save Analysis Report", file_name="analysis_report.json", allowed_extensions=["json"])

    def run_analysis_action(target_path: str, is_dir: bool, results_container: ft.Column):
        results_container.controls.clear()
        results_container.controls.append(
            ft.Row([ft.ProgressRing(width=20, height=20), ft.Text("Running analysis pipeline...")])
        )
        page.update()

        def do_work():
            nonlocal current_payload_json
            try:
                if not is_dir:
                    with tempfile.TemporaryDirectory() as d:
                        tmp_log = Path(d) / "uploaded.log"
                        shutil_copy = True
                        try:
                            shutil.copy2(target_path, tmp_log)
                        except:
                            tmp_log.write_bytes(Path(target_path).read_bytes())
                            
                        payload = run_analysis(
                            d, 
                            use_rag=state["use_rag"], 
                            use_llm_classifier=state["use_llm_cls"]
                        )
                else:
                    payload = run_analysis(
                        target_path, 
                        use_rag=state["use_rag"], 
                        use_llm_classifier=state["use_llm_cls"]
                    )
                
                current_payload_json = json.dumps(payload, ensure_ascii=False, indent=2)
                
                results_container.controls.clear()
                results_container.controls.append(render_metrics(payload.get("metrics") or {}))
                results_container.controls.append(ft.Divider())
                
                results = payload.get("results") or []
                if not results:
                    results_container.controls.append(ft.Text("No errors found in the provided logs.", color=ft.Colors.BLUE_200))
                else:
                    results_container.controls.append(ft.Text(f"Found {len(results)} error(s)", size=18, weight="bold"))
                    for i, item in enumerate(results, 1):
                        results_container.controls.append(create_error_card(i, item, target_path if is_dir else str(Path(target_path).parent)))

                results_container.controls.append(
                    ft.ElevatedButton("⬇️ Download Full Report (JSON)", on_click=btn_download_click)
                )

            except Exception as ex:
                results_container.controls.clear()
                results_container.controls.append(ft.Text(f"Analysis failed: {ex}", color=ft.Colors.RED_400))
            
            page.update()

        threading.Thread(target=do_work, daemon=True).start()

    # ── Main Tabs Setup ────────────────────────────────────────────────────────
    
    tabs = ft.Tabs(
        selected_index=0,
        animation_duration=400,
        expand=True,
        label_color=AppColors.ACCENT_INDIGO,
        unselected_label_color=AppColors.TEXT_MUTED,
        indicator_color=AppColors.ACCENT_INDIGO,
        divider_color="transparent",
        tabs=[
            ft.Tab(
                text="LOCAL FILE", 
                icon=ft.Icons.FILE_COPY,
                content=tab_upload
            ),
            ft.Tab(
                text="PROJECT SCAN", 
                icon=ft.Icons.FOLDER,
                content=tab_project
            ),
            ft.Tab(
                text="LIVE MONITOR", 
                icon=ft.Icons.SENSORS,
                content=tab_monitor
            ),
        ],
    )

    page.add(tabs)

if __name__ == "__main__":
    ft.app(target=main, view=ft.FLET_APP)
