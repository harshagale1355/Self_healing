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


# ── Global UI Helpers ──────────────────────────────────────────────────────────

def _sev_badge(sev: str) -> ft.Container:
    s = (sev or "unknown").lower()
    if s == "high":
        text, color, bgcolor = "🔴 HIGH", "#ff6b6b", "#331111"
    elif s == "medium":
        text, color, bgcolor = "🟡 MEDIUM", "#ffcc44", "#332200"
    elif s == "low":
        text, color, bgcolor = "🟢 LOW", "#44ff88", "#113311"
    else:
        text, color, bgcolor = f"⚪ {s.upper()}", "#aaaaaa", "#222222"
    return ft.Container(
        content=ft.Text(text, size=11, weight="bold", color=color),
        padding=ft.padding.symmetric(horizontal=10, vertical=3),
        border_radius=20,
        bgcolor=bgcolor,
        border=ft.border.all(1, color),
    )


def _risk_badge(level: str) -> ft.Container:
    l = (level or "medium").lower()
    if l == "high":
        text, color, bgcolor = "🔴 HIGH RISK", "#ff5555", "#441111"
    elif l == "medium":
        text, color, bgcolor = "🟡 MEDIUM RISK", "#ffaa33", "#332200"
    elif l == "low":
        text, color, bgcolor = "🟢 LOW RISK", "#55ff99", "#003311"
    else:
        text, color, bgcolor = f"⚪ {l.upper()} RISK", "#aaaaaa", "#222222"
    return ft.Container(
        content=ft.Text(text, size=11, weight="bold", color=color),
        padding=ft.padding.symmetric(horizontal=10, vertical=3),
        border_radius=20,
        bgcolor=bgcolor,
        border=ft.border.all(1, color),
    )

def _section_title(text: str) -> ft.Text:
    return ft.Text(
        text.upper(),
        size=12,
        weight="bold",
        color=ft.Colors.BLUE_GREY_400,
    )


# ── Main Flet App ──────────────────────────────────────────────────────────────

def main(page: ft.Page):
    # Base page settings
    page.title = "AI Log Error Analyzer"
    page.theme_mode = ft.ThemeMode.DARK
    page.theme = ft.Theme(color_scheme_seed=ft.Colors.INDIGO)
    page.padding = 20
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
        controls=[
            ft.Container(
                content=ft.Text("⚙️ Settings", size=20, weight="bold"),
                padding=20,
            ),
            ft.Divider(),
            ft.Container(
                content=ft.Column([
                    ft.Text("LLM Provider Configuration"),
                    settings_api_key,
                    ft.ElevatedButton("Save Key", on_click=save_api_key),
                    ft.Text("Set this if you don't have a .env file.", color=ft.Colors.GREY_400, size=12),
                ]),
                padding=20,
            ),
            ft.Divider(),
            ft.Container(
                content=ft.Column([
                    ft.Switch(label="Enable RAG memory (ChromaDB)", value=state["use_rag"], 
                              on_change=lambda e: state.update({"use_rag": e.control.value})),
                    ft.Switch(label="Use LLM for Classification", value=state["use_llm_cls"],
                              on_change=lambda e: state.update({"use_llm_cls": e.control.value})),
                ]),
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
            ft.Icon(ft.Icons.SEARCH, size=30, color=ft.Colors.INDIGO_300),
            ft.Text("AI Log Error Analyzer", size=24, weight="bold"),
        ]),
        center_title=False,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        actions=[
            ft.Container(content=provider_label_text, padding=10),
            ft.IconButton(ft.Icons.SETTINGS, on_click=open_settings, tooltip="Settings"),
        ],
    )

    # ── Reusable Component Rendering ──────────────────────────────────────────

    def render_metrics(metrics: dict) -> ft.Row:
        def _metric_card(label: str, value: str):
            return ft.Card(
                content=ft.Container(
                    content=ft.Column([
                        ft.Text(label, size=12, color=ft.Colors.BLUE_GREY_200, weight="bold"),
                        ft.Text(str(value), size=24, weight="w600"),
                    ]),
                    padding=15,
                    width=150,
                ),
            )

        errs = metrics.get("errors_processed", 0)
        succ = metrics.get("llm_success", 0)
        fail = metrics.get("llm_failures", 0)
        rate = f"{succ / (succ + fail):.0%}" if (succ + fail) > 0 else "—"
        wall = f"{metrics.get('wall_clock_seconds', 0):.2f}s"

        return ft.Row([
            _metric_card("🪲 Errors", errs),
            _metric_card("✅ LLM OK", succ),
            _metric_card("❌ LLM Fail", fail),
            _metric_card("📈 Success Rate", rate),
            _metric_card("⏱ Time", wall),
        ], wrap=True)

    def render_confidence(conf: dict | float) -> ft.Column:
        if not isinstance(conf, dict):
            v = float(conf or 0)
            conf = {"overall": v, "pattern_match": v, "llm_reasoning": v, "context_match": v}

        rows = []
        labels = {
            "overall": "Overall",
            "pattern_match": "Pattern Match",
            "llm_reasoning": "LLM Reasoning",
            "context_match": "Context Match",
        }
        for key, label in labels.items():
            val = float(conf.get(key, 0))
            color = ft.Colors.GREEN if val >= 0.8 else ft.Colors.AMBER if val >= 0.5 else ft.Colors.RED
            rows.append(
                ft.Row([
                    ft.Text(label, width=120, size=12, color=ft.Colors.BLUE_GREY_200),
                    ft.ProgressBar(value=val, width=200, color=color, bgcolor=ft.Colors.BLUE_GREY_900),
                    ft.Text(f"{val:.0%}", width=50, size=12, weight="bold", color=color),
                ])
            )
        return ft.Column(rows)

    def create_error_card(index: int, item: dict, project_path: str) -> ft.Card:
        sev = item.get("severity", "unknown")
        err_type = item.get("type", "unknown")
        priority = item.get("priority", "—")
        fix_risk = item.get("fix_risk") or {}
        risk_level = fix_risk.get("level", "medium")

        card_title = f"#{index} · {err_type.upper()} · {sev.upper()} · P{priority}"
        
        # Header area
        header_row = ft.Row([
            _sev_badge(sev),
            _risk_badge(risk_level),
        ], spacing=10)

        err_txt = (item.get("error") or "")[:500]
        err_display = ft.Container(
            content=ft.Text(f"Error: {err_txt}", font_family="monospace", size=13),
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            padding=10,
            border_radius=5,
        )

        ctx = item.get("context") or {}
        ctx_text = ""
        if ctx.get("file"):
            ctx_text = f"📍 {ctx.get('file')}:{ctx.get('line', '?')} {ctx.get('function') or ''}"

        cause_col = ft.Column([ft.Text("🔎 Cause", weight="bold"), ft.Text(item.get("cause", "") or "—")], expand=1)
        fix_col = ft.Column([ft.Text("🛠 Fix", weight="bold"), ft.Text(item.get("fix", "") or "—")], expand=1)

        reason = item.get("reason") or {}
        explain_col = None
        if any(reason.values()):
            explain_col = ft.Column([
                _section_title("💡 Explainability"),
                ft.Row([
                    ft.Column([ft.Text("Immediate Trigger", weight="bold", size=12), ft.Text(reason.get("immediate") or "—", size=12)], expand=1),
                    ft.Column([ft.Text("Root Cause", weight="bold", size=12), ft.Text(reason.get("root") or "—", size=12)], expand=1),
                    ft.Column([ft.Text("Why Fix Works", weight="bold", size=12), ft.Text(reason.get("why_fix_works") or "—", size=12)], expand=1),
                ], alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.START)
            ])

        patch_txt = (item.get("patch") or "").strip()
        patch_controls = []
        if patch_txt:
            patch_controls.append(_section_title("📋 Patch (diff)"))
            patch_controls.append(ft.TextField(
                value=patch_txt, read_only=True, multiline=True,
                text_style=ft.TextStyle(font_family="monospace", size=12),
                min_lines=3, max_lines=10,
                border_color=ft.Colors.BLUE_GREY_700,
            ))
            
            def apply_fix_click(e, patch=patch_txt, proj=project_path):
                e.control.disabled = True
                e.control.text = "Applying..."
                page.update()
                
                res = apply_patch(patch, project_root=proj)
                e.control.text = "⚡ Apply Fix"
                e.control.disabled = False
                
                if res["success"]:
                    page.snack_bar = ft.SnackBar(ft.Text(f"✅ {res['message']}"), bgcolor=ft.Colors.GREEN_800)
                else:
                    page.snack_bar = ft.SnackBar(ft.Text(f"❌ {res['message']}"), bgcolor=ft.Colors.RED_800)
                page.snack_bar.open = True
                page.update()

            patch_controls.append(ft.ElevatedButton(
                "⚡ Apply Fix",
                color=ft.Colors.WHITE,
                bgcolor=ft.Colors.BLUE_700,
                on_click=apply_fix_click,
            ))

        code_txt = (item.get("code") or "").strip()
        code_controls = []
        if code_txt:
            code_controls.append(_section_title("💻 Suggested Code"))
            code_controls.append(ft.TextField(
                value=code_txt, read_only=True, multiline=True,
                text_style=ft.TextStyle(font_family="monospace", size=12),
                min_lines=3, max_lines=10,
                border_color=ft.Colors.BLUE_GREY_700,
            ))

        sim_cases = item.get("similar_cases") or []
        sim_controls = []
        if sim_cases:
            sim_controls.append(_section_title(f"🔍 Similar Issues Found (RAG Memory)"))
            for i, c in enumerate(sim_cases, 1):
                sim = float(c.get("similarity", 0))
                sim_controls.append(
                    ft.ExpansionTile(
                        title=ft.Text(f"Match #{i} — similarity {sim:.0%}", size=13),
                        controls=[
                            ft.Container(
                                content=ft.Column([
                                    ft.Text(f"**Error:** {c.get('error', '')[:300]}", size=12),
                                    ft.Text(f"**Past fix:** {c.get('fix', '')[:300]}", size=12),
                                ]),
                                padding=10,
                            )
                        ]
                    )
                )

        body_controls = [
            header_row,
            err_display,
        ]
        if ctx_text:
            body_controls.append(ft.Text(ctx_text, size=12, color=ft.Colors.BLUE_GREY_300))
        
        body_controls.extend([
            ft.Divider(color=ft.Colors.BLUE_GREY_800),
            ft.Row([cause_col, fix_col], alignment=ft.MainAxisAlignment.START, vertical_alignment=ft.CrossAxisAlignment.START),
        ])
        
        if explain_col:
            body_controls.extend([ft.Divider(color=ft.Colors.BLUE_GREY_800), explain_col])
            
        body_controls.extend([
            ft.Divider(color=ft.Colors.BLUE_GREY_800),
            _section_title("📊 Confidence Breakdown"),
            render_confidence(item.get("confidence")),
        ])

        if code_controls:
            body_controls.extend([ft.Divider(color=ft.Colors.BLUE_GREY_800)] + code_controls)
            
        if patch_controls:
            body_controls.extend([ft.Divider(color=ft.Colors.BLUE_GREY_800)] + patch_controls)
            
        if sim_controls:
            body_controls.extend([ft.Divider(color=ft.Colors.BLUE_GREY_800)] + sim_controls)

        return ft.Card(
            content=ft.ExpansionTile(
                title=ft.Text(card_title, weight="bold"),
                initially_expanded=(index <= 2),
                controls=[
                    ft.Container(
                        content=ft.Column(body_controls, spacing=10),
                        padding=20,
                    )
                ]
            ),
            margin=ft.margin.only(bottom=10),
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
            ft.Text("Upload a log file to analyse", size=16),
            ft.ElevatedButton(
                "🚀 Browse file and Analyse", 
                icon=ft.Icons.FOLDER_OPEN,
                on_click=lambda _: file_picker.pick_files(allow_multiple=False),
                height=45,
            ),
            upload_results,
        ]),
        padding=20,
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
            ft.Text("Scan a project directory for log files", size=16),
            ft.Row([
                project_dir_input,
                ft.IconButton(ft.Icons.FOLDER, on_click=lambda _: dir_picker.get_directory_path()),
            ]),
            ft.ElevatedButton(
                "🚀 Analyse Project", 
                icon=ft.Icons.PLAY_ARROW,
                on_click=analyze_project_click,
                height=45,
            ),
            project_results,
        ]),
        padding=20,
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
            ft.Text("Real-time log file monitoring", size=16),
            ft.Row([monitor_file_input, monitor_interval]),
            ft.Row([btn_start, btn_stop, monitor_status]),
            ft.Divider(),
            monitor_results_col,
        ]),
        padding=20,
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
        animation_duration=300,
        expand=True,
        tabs=[
            ft.Tab(text="📁 Upload Log", content=tab_upload),
            ft.Tab(text="📂 Project Directory", content=tab_project),
            ft.Tab(text="📡 Live Monitor", content=tab_monitor),
        ],
    )

    page.add(tabs)

if __name__ == "__main__":
    ft.app(target=main, view=ft.FLET_APP)
