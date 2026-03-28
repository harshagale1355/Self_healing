"""
Patch Applier: safely apply unified-diff patches to source files.

Workflow:
1. Parse the patch to identify the target file.
2. Resolve the file using project-relative or absolute path.
3. Create a dated .bak backup alongside the original.
4. Apply the diff hunk-by-hunk (add / remove lines).
5. Write the patched content back to the file.
6. Return {success, backup_path, message}.

Never deletes data — the backup is always created first.
"""
from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any


# ── Regex patterns for unified diff parsing ─────────────────────────────────

_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_FILE_MINUS = re.compile(r"^--- (.+)$")
_FILE_PLUS = re.compile(r"^\+\+\+ (.+)$")


def _parse_target_filename(patch_text: str) -> str | None:
    """Extract the +++ b/... filename from the patch header."""
    for line in patch_text.splitlines():
        m = _FILE_PLUS.match(line)
        if m:
            name = m.group(1).strip()
            # strip leading a/ b/ git prefixes
            for prefix in ("b/", "a/"):
                if name.startswith(prefix):
                    name = name[len(prefix):]
            return name
    return None


def _resolve_file(project_root: str | Path, file_ref: str) -> Path | None:
    """Reuse the same search logic as code_context."""
    from agents.code_context import resolve_source_path  # local import to avoid circularity

    return resolve_source_path(project_root, file_ref)


def _apply_hunk(lines: list[str], hunk_lines: list[str], start: int) -> list[str] | None:
    """
    Apply a single diff hunk to *lines* (0-based list, no trailing newlines).
    *start* is the 1-based old-file start line from the @@ header.
    Returns new lines list or None on failure.
    """
    result = list(lines[: start - 1])
    pos = start - 1  # 0-based index into original

    for dl in hunk_lines:
        if dl.startswith("-"):
            # expect to consume one line from original
            if pos >= len(lines):
                return None
            result_candidate = lines[pos]
            expected = dl[1:]
            if result_candidate.rstrip("\r\n") != expected.rstrip("\r\n"):
                return None  # context mismatch
            pos += 1
        elif dl.startswith("+"):
            result.append(dl[1:])
        else:
            # context line — must match
            ctx = dl[1:] if dl.startswith(" ") else dl
            if pos >= len(lines):
                return None
            if lines[pos].rstrip("\r\n") != ctx.rstrip("\r\n"):
                return None
            result.append(lines[pos])
            pos += 1

    # Append remainder of original file after this hunk
    result.extend(lines[pos:])
    return result


def apply_patch(
    patch_text: str,
    target_file: str | Path | None = None,
    project_root: str | Path = ".",
) -> dict[str, Any]:
    """
    Apply *patch_text* (unified diff) to a source file.

    Parameters
    ----------
    patch_text   : The unified diff string.
    target_file  : Explicit file path override (optional).
    project_root : Project root used for resolving relative paths.

    Returns
    -------
    dict with keys: success (bool), backup_path (str|None), message (str).
    """
    root = Path(project_root).resolve()

    # 1. Find target file
    if target_file:
        ref = str(target_file)
    else:
        ref = _parse_target_filename(patch_text)
        if not ref:
            return {"success": False, "backup_path": None, "message": "Could not determine target file from patch header."}

    path = _resolve_file(root, ref)
    if path is None or not path.is_file():
        return {
            "success": False,
            "backup_path": None,
            "message": f"Target file not found: {ref!r} (looked under {root})",
        }

    # 2. Create backup
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = path.with_suffix(path.suffix + f".{ts}.bak")
    try:
        shutil.copy2(path, backup_path)
    except OSError as e:
        return {"success": False, "backup_path": None, "message": f"Backup failed: {e}"}

    # 3. Parse patch and apply hunks
    try:
        original_text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return {"success": False, "backup_path": str(backup_path), "message": f"Read failed: {e}"}

    lines: list[str] = original_text.splitlines()

    patch_lines = patch_text.splitlines()
    i = 0
    n = len(patch_lines)
    while i < n and not _HUNK_HEADER.match(patch_lines[i]):
        i += 1

    if i >= n:
        # No hunk headers — could be a pure replacement block comment; treat as no-op
        return {
            "success": False,
            "backup_path": str(backup_path),
            "message": "Patch contains no valid @@ hunk headers — cannot apply automatically.",
        }

    errors: list[str] = []
    while i < n:
        m = _HUNK_HEADER.match(patch_lines[i])
        if not m:
            i += 1
            continue
        old_start = int(m.group(1))
        i += 1
        hunk_lines: list[str] = []
        while i < n and not _HUNK_HEADER.match(patch_lines[i]):
            pl = patch_lines[i]
            if pl.startswith(("-", "+", " ")):
                hunk_lines.append(pl)
            elif pl.startswith("\\ "):
                pass  # "No newline at end of file"
            i += 1
        new_lines = _apply_hunk(lines, hunk_lines, old_start)
        if new_lines is None:
            errors.append(f"Hunk at line {old_start} failed to apply (context mismatch).")
            break
        lines = new_lines

    if errors:
        # Restore from backup
        shutil.copy2(backup_path, path)
        return {
            "success": False,
            "backup_path": str(backup_path),
            "message": "; ".join(errors) + " Original file restored from backup.",
        }

    # 4. Write patched content
    new_text = "\n".join(lines)
    if original_text.endswith("\n"):
        new_text += "\n"
    try:
        path.write_text(new_text, encoding="utf-8")
    except OSError as e:
        shutil.copy2(backup_path, path)
        return {
            "success": False,
            "backup_path": str(backup_path),
            "message": f"Write failed: {e}. Original restored.",
        }

    return {
        "success": True,
        "backup_path": str(backup_path),
        "message": f"Patch applied to {path.relative_to(root)}. Backup: {backup_path.name}",
    }
