import re
import subprocess
from pathlib import Path
from collections import defaultdict

import structlog

log = structlog.get_logger()

# Map file extensions to language names
EXTENSION_LANGUAGE_MAP: dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript (React)",
    ".jsx": "JavaScript (React)",
    ".java": "Java",
    ".go": "Go",
    ".rs": "Rust",
    ".rb": "Ruby",
    ".php": "PHP",
    ".c": "C",
    ".cpp": "C++",
    ".h": "C/C++ Header",
    ".cs": "C#",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".sh": "Shell",
    ".bash": "Bash",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".md": "Markdown",
    ".sql": "SQL",
    ".r": "R",
    ".scala": "Scala",
    ".lua": "Lua",
    ".dart": "Dart",
}

# Directories to skip when walking the repo
SKIP_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    ".env",
    "dist",
    "build",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "coverage",
    ".next",
    ".nuxt",
    "target",
}


def read_file_contents(path: str) -> str:
    """Read and return the text contents of a file.

    Returns the file contents as a string, or an error message prefixed with
    'ERROR:' if the file cannot be read.
    """
    file_path = Path(path)
    if not file_path.exists():
        msg = f"ERROR: File not found: {path}"
        log.warning("file not found", path=path)
        return msg
    if not file_path.is_file():
        msg = f"ERROR: Path is not a file: {path}"
        log.warning("path is not a file", path=path)
        return msg
    try:
        contents = file_path.read_text(encoding="utf-8", errors="replace")
        log.info("file read", path=path, size=len(contents))
        return contents
    except Exception as exc:
        msg = f"ERROR: Could not read file {path}: {exc}"
        log.exception("file read error", path=path, error=str(exc))
        return msg


def grep_in_repo(
    repo_path: str,
    pattern: str,
    file_pattern: str = "*",
) -> list[dict]:
    """Search for a regex pattern across files in the repo.

    Args:
        repo_path: Absolute path to the repository root.
        pattern: Regular expression pattern to search for.
        file_pattern: Glob pattern to restrict which files are searched (e.g. "*.py").

    Returns:
        List of match dicts with keys:
            file, line_number, line_content, context
    """
    path = Path(repo_path)
    if not path.exists():
        log.error("repo_path does not exist", repo_path=repo_path)
        return []

    # Use ripgrep when available, fall back to grep
    try:
        rg_result = subprocess.run(["rg", "--version"], capture_output=True)
        use_rg = rg_result.returncode == 0
    except FileNotFoundError:
        use_rg = False

    matches: list[dict] = []

    if use_rg:
        cmd = [
            "rg",
            "--json",
            "--context", "2",
            "--glob", file_pattern,
            pattern,
            str(path),
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            for line in result.stdout.splitlines():
                try:
                    obj = __import__("json").loads(line)
                except Exception:
                    continue
                if obj.get("type") == "match":
                    data = obj["data"]
                    file_rel = str(Path(data["path"]["text"]).relative_to(path))
                    line_num = data["line_number"]
                    line_content = data["lines"]["text"].rstrip("\n")
                    context_before = [
                        s["text"].rstrip("\n")
                        for s in data.get("submatches", [])
                    ]
                    matches.append(
                        {
                            "file": file_rel,
                            "line_number": line_num,
                            "line_content": line_content,
                            "context": context_before,
                        }
                    )
        except subprocess.TimeoutExpired:
            log.error("rg timed out", repo_path=repo_path, pattern=pattern)
        except Exception as exc:
            log.exception("rg error", error=str(exc))
    else:
        # Pure Python fallback
        try:
            compiled = re.compile(pattern)
        except re.error as exc:
            log.error("invalid regex pattern", pattern=pattern, error=str(exc))
            return []

        for file_path in _iter_files(path, extensions=None):
            # Apply file_pattern filter (simple suffix check when not "*")
            if file_pattern != "*":
                # convert glob like "*.py" to a suffix check
                suffix = file_pattern.lstrip("*")
                if not file_path.name.endswith(suffix):
                    continue
            try:
                lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                continue
            for i, line in enumerate(lines, start=1):
                if compiled.search(line):
                    context_lines = lines[max(0, i - 3): i - 1]
                    matches.append(
                        {
                            "file": str(file_path.relative_to(path)),
                            "line_number": i,
                            "line_content": line,
                            "context": context_lines,
                        }
                    )

    log.info(
        "grep complete",
        repo_path=repo_path,
        pattern=pattern,
        file_pattern=file_pattern,
        matches=len(matches),
    )
    return matches


def list_files(repo_path: str, extensions: list[str] | None = None) -> list[str]:
    """Return a sorted list of relative file paths within the repo.

    Args:
        repo_path: Absolute path to the repository root.
        extensions: Optional list of extensions to filter by (e.g. [".py", ".js"]).
                    Include the leading dot. When None, all files are returned.

    Returns:
        Sorted list of POSIX-style relative paths.
    """
    path = Path(repo_path)
    if not path.exists():
        log.error("repo_path does not exist", repo_path=repo_path)
        return []

    files = [
        str(f.relative_to(path))
        for f in _iter_files(path, extensions=extensions)
    ]
    files.sort()
    log.info("list_files complete", repo_path=repo_path, count=len(files))
    return files


def get_file_stats(repo_path: str) -> dict:
    """Compute aggregate statistics for all files in the repo.

    Returns:
        {
            "total_files": int,
            "total_lines": int,
            "by_extension": {".py": int, ...},
            "languages": ["Python", ...],
        }
    """
    path = Path(repo_path)
    if not path.exists():
        log.error("repo_path does not exist", repo_path=repo_path)
        return {
            "total_files": 0,
            "total_lines": 0,
            "by_extension": {},
            "languages": [],
        }

    total_files = 0
    total_lines = 0
    by_extension: dict[str, int] = defaultdict(int)

    for file_path in _iter_files(path, extensions=None):
        ext = file_path.suffix.lower()
        total_files += 1
        by_extension[ext] += 1
        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
            total_lines += content.count("\n") + (1 if content and not content.endswith("\n") else 0)
        except Exception:
            pass

    languages_seen: set[str] = set()
    for ext in by_extension:
        lang = EXTENSION_LANGUAGE_MAP.get(ext)
        if lang:
            languages_seen.add(lang)

    stats = {
        "total_files": total_files,
        "total_lines": total_lines,
        "by_extension": dict(by_extension),
        "languages": sorted(languages_seen),
    }
    log.info("file stats computed", repo_path=repo_path, **stats)
    return stats


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _iter_files(root: Path, extensions: list[str] | None):
    """Yield all files under root, skipping SKIP_DIRS."""
    for item in root.rglob("*"):
        # Skip any path that has a SKIP_DIRS component
        if any(part in SKIP_DIRS for part in item.parts):
            continue
        if not item.is_file():
            continue
        if extensions is not None:
            if item.suffix.lower() not in extensions:
                continue
        yield item
