# AI-Powered Log Error Analyzer and Auto-Solver

A reusable Python tool that scans project logs, classifies errors, extracts structured context (file, line, function), and uses an LLM to propose root causes, fixes, and code snippets. Optional **ChromaDB** RAG stores past errors for similarity search. The workflow is implemented with **LangGraph**.

## Features

- **Multi-step pipeline**: log read → error filter → per-error classify → context extraction → optional RAG → solution generation → validation
- **Error categories**: syntax, runtime, memory, file_system, network, database, api, dependency, config, unknown
- **Log formats**: Python tracebacks, Node-style stacks, Java stack lines, generic `file:line` patterns
- **CLI**: `ai-debugger run <project_dir>`
- **Optional UI**: Streamlit app for uploads and project paths
- **Output**: JSON array of objects with `error`, `type`, `cause`, `fix`, `code`, `confidence`, plus optional `validation` and slim `context`

## Setup

```bash
cd /path/to/Self_healing
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install -e .
```

### Environment variables

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | OpenAI API (default provider) |
| `LLM_PROVIDER` | `openai` (default) or `groq` |
| `GROQ_API_KEY` | Groq API when `LLM_PROVIDER=groq` |
| `OPENAI_MODEL` | Default: `gpt-4o-mini` |
| `GROQ_MODEL` | Default: `llama-3.3-70b-versatile` |
| `ENABLE_RAG` | `true` to persist/query Chroma by default |
| `CHROMA_PERSIST_DIR` | Chroma persistence directory |
| `LLM_MAX_RETRIES` | Retry count for LLM JSON parsing (default `3`) |

Without API keys, the tool still runs: classification and context extraction work; solutions use a **fallback** message explaining that LLM keys are missing.

## CLI usage

```bash
# Analyze all logs under a directory (skips venv, .git, node_modules, etc.)
ai-debugger run /path/to/project

# Write JSON to a file
ai-debugger run /path/to/project -o results.json

# Enable RAG for this run (requires Chroma + embeddings)
ai-debugger run /path/to/project --rag

# Optional: LLM-based classifier refinement (extra API calls)
ai-debugger run /path/to/project --llm-classifier
```

Or without installing the console script:

```bash
PYTHONPATH=. python main.py run sample_logs
```

## Streamlit UI

```bash
streamlit run ui/app.py
```

Upload a log file or enter a project directory, then analyze and download JSON.

## Sample log and expected shape

See `sample_logs/sample_mixed.log`. With LLM keys configured, each item resembles:

```json
[
  {
    "error": "[sample_mixed.log] ERROR ModuleNotFoundError: No module named 'requests'",
    "type": "dependency",
    "cause": "...",
    "fix": "...",
    "code": "...",
    "confidence": 0.85,
    "validation": { "approved": true, "notes": "..." },
    "context": { "file": "...", "line": 42, "function": "..." }
  }
]
```

## Tests

```bash
pytest tests/ -q
```

## Project layout

- `agents/` — Log reader, error filter, classifier, context extractor, solution generator, validator
- `workflows/graph.py` — LangGraph state machine
- `prompts/prompts.py` — System/user prompts (strict JSON)
- `rag/retriever.py` — Chroma optional RAG
- `utils/` — Log discovery, parsing, LLM helpers
- `main.py` — CLI entry
- `ui/app.py` — Streamlit UI

## License

Use and modify freely in your own projects.
