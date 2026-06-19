import asyncio
import shutil
from collections import Counter
from pathlib import Path

import git  # gitpython
import structlog

log = structlog.get_logger()

SUPPORTED_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
    ".cpp", ".c", ".h", ".cs", ".rb", ".php", ".swift", ".kt",
    ".yaml", ".yml", ".json", ".toml", ".sh", ".sql", ".md",
}

SKIP_DIRS: set[str] = {
    ".git", "node_modules", "__pycache__", "dist", "build", ".venv", "vendor",
}

MAX_FILE_SIZE_BYTES: int = 500_000  # skip files larger than 500 KB


class GitLoader:
    def __init__(self, clone_base_dir: str) -> None:
        self.clone_base = Path(clone_base_dir)
        self.clone_base.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def clone(self, git_url: str, run_id: str) -> Path:
        """Clone *git_url* into ``<clone_base>/<run_id>`` and return the path.

        The blocking :py:func:`git.Repo.clone_from` call is executed in a
        thread pool so the event loop is not blocked.
        """
        dest = self.clone_base / run_id
        if dest.exists():
            log.info("clone_dir_exists_reusing", run_id=run_id, dest=str(dest))
            return dest

        log.info("cloning_repo", git_url=git_url, run_id=run_id, dest=str(dest))
        try:
            await asyncio.to_thread(
                git.Repo.clone_from,
                git_url,
                str(dest),
                depth=1,  # shallow clone — faster for review purposes
            )
        except git.GitCommandError as exc:
            log.error("clone_failed", git_url=git_url, run_id=run_id, error=str(exc))
            raise

        log.info("clone_complete", run_id=run_id)
        return dest

    def get_files(self, repo_path: Path) -> list[Path]:
        """Return all source files in *repo_path* that pass the size/extension filter."""
        collected: list[Path] = []

        for candidate in repo_path.rglob("*"):
            # Skip directories — rglob yields both files and dirs
            if not candidate.is_file():
                continue

            # Skip files inside blacklisted directories
            if any(part in SKIP_DIRS for part in candidate.relative_to(repo_path).parts):
                continue

            # Extension filter
            if candidate.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue

            # Size filter
            try:
                size = candidate.stat().st_size
            except OSError:
                continue

            if size > MAX_FILE_SIZE_BYTES:
                log.debug(
                    "skipping_large_file",
                    path=str(candidate.relative_to(repo_path)),
                    size_bytes=size,
                )
                continue

            collected.append(candidate)

        log.info("files_collected", repo=str(repo_path), count=len(collected))
        return collected

    def get_repo_metadata(self, repo_path: Path) -> dict:
        """Return a metadata dict describing the repository."""
        try:
            repo = git.Repo(str(repo_path))
        except git.InvalidGitRepositoryError as exc:
            log.error("invalid_git_repo", path=str(repo_path), error=str(exc))
            return {}

        # Determine the active / default branch name safely
        try:
            default_branch = repo.active_branch.name
        except TypeError:
            # Detached HEAD (common for shallow clones)
            default_branch = "HEAD"

        # Latest commit
        try:
            head_commit = repo.head.commit
            last_commit = {
                "sha": head_commit.hexsha[:12],
                "message": head_commit.message.strip().splitlines()[0],
                "author": str(head_commit.author),
                "date": head_commit.committed_datetime.isoformat(),
            }
        except Exception:  # noqa: BLE001
            last_commit = {}

        # Count files and tally languages
        files = self.get_files(repo_path)
        ext_counter: Counter[str] = Counter(f.suffix.lower() for f in files)
        languages = dict(ext_counter.most_common())

        # Best-effort remote URL
        try:
            url = next(repo.remotes[0].urls) if repo.remotes else str(repo_path)
        except Exception:  # noqa: BLE001
            url = str(repo_path)

        return {
            "name": repo_path.name,
            "url": url,
            "default_branch": default_branch,
            "last_commit": last_commit,
            "total_files": len(files),
            "languages": languages,
        }

    async def cleanup(self, run_id: str) -> None:
        """Remove the cloned directory for *run_id*."""
        target = self.clone_base / run_id
        if not target.exists():
            log.warning("cleanup_dir_not_found", run_id=run_id)
            return

        log.info("cleaning_up_clone", run_id=run_id, path=str(target))
        await asyncio.to_thread(shutil.rmtree, target, ignore_errors=True)
        log.info("cleanup_complete", run_id=run_id)
