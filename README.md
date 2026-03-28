# AI-Powered Log Error Analyzer and Auto-Solver (v2)

Production-oriented tool: scans logs, classifies errors, **loads source around the failing line**, **RAG** over past fixes, **LLM solutions + patches**, **severity/priority**, **metrics**, **pretty CLI**, and **Streamlit UI**.

## Features

| Feature | Description |
|--------|-------------|
| **Codebase awareness** | `agents/code_context.py` reads configurable lines before/after the error (`CODE_CONTEXT_LINES_BEFORE` / `AFTER`). |
| **RAG** | `rag/vector_store.py` + `rag/retriever.py` store `error → cause → fix → code` in Chroma and retrieve similar cases. |
| **CLI** | `cli.py`: `ai-debugger run` (Rich panels), `--json` for machine output, `ai-debugger watch` polls a log file. |
| **Patches** | `agents/patch_generator.py` asks the LLM for a unified diff or safe replacement block. |
| **Severity** | `agents/severity.py`: `low` / `medium` / `high` + numeric `priority`. |
| **Metrics** | `utils/logger.py` reducers + `run_analysis()` returns `{"results", "metrics"}`. |
| **Languages** | Parsers for Python, Node, Java, Go-style paths (`utils/parser.py`). |

## Output JSON (per error)

```json
{
  "error": "...",
  "type": "...",
  "cause": "...",
  "fix": "...",
  "code": "...",
  "patch": "...",
  "severity": "high",
  "priority": 1,
  "confidence": 0.85,
  "validation": { "approved": true, "notes": "..." },
  "context": { "file": "...", "line": 42, "function": "...", "resolved_path": "..." }
}
```

Top-level API:

```json
{
  "results": [ ... ],
  "metrics": {
    "errors_processed": 3,
    "llm_success": 3,
    "llm_failures": 0,
    "total_processing_seconds": 0.01,
    "wall_clock_seconds": 1.2,
    "errors_by_severity": { "high": 1, "medium": 2 }
  }
}
```

## Setup

```bash
cd /path/to/Self_healing
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

Environment: create a `.env` in the project root (see `.env.example`) or export vars in the shell.

| Variable | Notes |
|----------|--------|
| `GROQ_API_KEY` | If set (e.g. in `.env`), **Groq is used for all LLM calls** unless `LLM_PROVIDER=openai` is set. |
| `LLM_PROVIDER` | Optional override: `groq` or `openai` when both keys exist. |
| `OPENAI_API_KEY` | Used when `LLM_PROVIDER=openai` or when no Groq key is set. |

`config.py` loads `.env` via `python-dotenv` before choosing the provider (shell env still overrides `.env`).

## CLI

```bash
# Pretty colored output + metrics table
ai-debugger run /path/to/project

# Raw JSON (results + metrics)
ai-debugger run /path/to/project --json

# RAG on for this run
ai-debugger run /path/to/project --rag

# Save full JSON
ai-debugger run /path/to/project -o report.json

# Poll a single log file (append-only); analyzes new error lines as they appear
ai-debugger watch /path/to/app.log --interval 1.0
```

Legacy: `python main.py run …` still resolves to the same CLI.

## Streamlit

```bash
streamlit run ui/app.py
```

## Tests

```bash
pytest tests/ -q
```

## Layout

```
main.py              # Entry shim → cli.main
cli.py               # Click + Rich
config.py
agents/
  log_reader.py, error_filter.py, classifier.py
  context_extractor.py   # parse only
  code_context.py        # read source window
  solution_generator.py, validator.py, patch_generator.py, severity.py
rag/
  vector_store.py, retriever.py
utils/
  file_scanner.py, parser.py, llm_client.py, logger.py, log_monitor.py
workflows/graph.py
prompts/prompts.py
ui/app.py
```

## Sample

`sample_logs/sample_mixed.log` — run:

```bash
ai-debugger run sample_logs --no-rag --json | head
```

Without API keys, solutions use the rule-based fallback; severity/patch/context still populate.
