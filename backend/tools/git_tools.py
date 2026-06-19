import subprocess
import json
from pathlib import Path

import structlog

log = structlog.get_logger()


def get_git_log(repo_path: str, max_entries: int = 50) -> list[dict]:
    """Return a list of git commits with metadata."""
    path = Path(repo_path)
    if not path.exists():
        log.error("repo_path does not exist", repo_path=repo_path)
        return []

    fmt = "%H|%an|%ae|%ai|%s"
    try:
        result = subprocess.run(
            ["git", "log", f"--max-count={max_entries}", f"--format={fmt}"],
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            log.error("git log failed", stderr=result.stderr, repo_path=repo_path)
            return []

        commits = []
        for line in result.stdout.strip().splitlines():
            if not line.strip():
                continue
            parts = line.split("|", 4)
            if len(parts) < 5:
                continue
            commits.append(
                {
                    "hash": parts[0],
                    "author_name": parts[1],
                    "author_email": parts[2],
                    "date": parts[3],
                    "subject": parts[4],
                }
            )
        log.info("git log retrieved", repo_path=repo_path, count=len(commits))
        return commits
    except subprocess.TimeoutExpired:
        log.error("git log timed out", repo_path=repo_path)
        return []
    except Exception as exc:
        log.exception("git log error", repo_path=repo_path, error=str(exc))
        return []


def get_git_blame(repo_path: str, file_path: str) -> str:
    """Return git blame output for the given file."""
    path = Path(repo_path)
    if not path.exists():
        log.error("repo_path does not exist", repo_path=repo_path)
        return ""

    try:
        result = subprocess.run(
            ["git", "blame", "--line-porcelain", file_path],
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            log.error(
                "git blame failed",
                stderr=result.stderr,
                repo_path=repo_path,
                file_path=file_path,
            )
            return result.stderr

        log.info("git blame retrieved", repo_path=repo_path, file_path=file_path)
        return result.stdout
    except subprocess.TimeoutExpired:
        log.error("git blame timed out", repo_path=repo_path, file_path=file_path)
        return ""
    except Exception as exc:
        log.exception(
            "git blame error",
            repo_path=repo_path,
            file_path=file_path,
            error=str(exc),
        )
        return ""


def get_changed_files(repo_path: str, base_ref: str = "HEAD~1") -> list[str]:
    """Return a list of files changed between base_ref and HEAD."""
    path = Path(repo_path)
    if not path.exists():
        log.error("repo_path does not exist", repo_path=repo_path)
        return []

    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", base_ref, "HEAD"],
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            log.error(
                "git diff failed",
                stderr=result.stderr,
                repo_path=repo_path,
                base_ref=base_ref,
            )
            return []

        files = [f for f in result.stdout.strip().splitlines() if f.strip()]
        log.info(
            "changed files retrieved",
            repo_path=repo_path,
            base_ref=base_ref,
            count=len(files),
        )
        return files
    except subprocess.TimeoutExpired:
        log.error("git diff timed out", repo_path=repo_path)
        return []
    except Exception as exc:
        log.exception("git diff error", repo_path=repo_path, error=str(exc))
        return []
