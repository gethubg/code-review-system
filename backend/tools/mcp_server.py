"""MCP server exposing all code-review tools via FastMCP."""

from mcp.server.fastmcp import FastMCP

from .file_tools import (
    read_file_contents,
    grep_in_repo,
    list_files,
    get_file_stats,
)
from .git_tools import get_git_log, get_git_blame
from .dep_audit import run_pip_audit, run_npm_audit

mcp = FastMCP("code-review-tools")


# ---------------------------------------------------------------------------
# File tools
# ---------------------------------------------------------------------------


@mcp.tool()
def tool_read_file_contents(path: str) -> str:
    """Read and return the text contents of a file at the given absolute path."""
    return read_file_contents(path)


@mcp.tool()
def tool_grep_in_repo(
    repo_path: str,
    pattern: str,
    file_pattern: str = "*",
) -> list[dict]:
    """Search for a regex pattern across files in the repo.

    Args:
        repo_path: Absolute path to the repository root.
        pattern: Regular expression to search for.
        file_pattern: Glob pattern restricting which files to search (e.g. "*.py").

    Returns:
        List of matches, each with keys: file, line_number, line_content, context.
    """
    return grep_in_repo(repo_path, pattern, file_pattern)


@mcp.tool()
def tool_list_files(
    repo_path: str,
    extensions: list[str] | None = None,
) -> list[str]:
    """Return a sorted list of relative file paths within the repo.

    Args:
        repo_path: Absolute path to the repository root.
        extensions: Optional list of extensions to filter by, e.g. [".py", ".js"].
    """
    return list_files(repo_path, extensions)


@mcp.tool()
def tool_get_file_stats(repo_path: str) -> dict:
    """Compute aggregate statistics for all files in the repo.

    Returns a dict with total_files, total_lines, by_extension, and languages.
    """
    return get_file_stats(repo_path)


# ---------------------------------------------------------------------------
# Git tools
# ---------------------------------------------------------------------------


@mcp.tool()
def tool_get_git_log(repo_path: str, max_entries: int = 50) -> list[dict]:
    """Return the git commit log for the repository.

    Args:
        repo_path: Absolute path to the repository root.
        max_entries: Maximum number of commits to return (default 50).

    Returns:
        List of commit dicts with keys: hash, author_name, author_email, date, subject.
    """
    return get_git_log(repo_path, max_entries)


@mcp.tool()
def tool_get_git_blame(repo_path: str, file_path: str) -> str:
    """Return git blame output for a file.

    Args:
        repo_path: Absolute path to the repository root.
        file_path: Path to the file relative to repo_path.

    Returns:
        Raw git blame --line-porcelain output as a string.
    """
    return get_git_blame(repo_path, file_path)


# ---------------------------------------------------------------------------
# Dependency audit tools
# ---------------------------------------------------------------------------


@mcp.tool()
def tool_run_pip_audit(repo_path: str) -> dict:
    """Run pip-audit against the repository and return vulnerability data.

    Args:
        repo_path: Absolute path to the repository root.

    Returns:
        Dict with keys: vulnerabilities (list), total (int), error (str|None).
    """
    return run_pip_audit(repo_path)


@mcp.tool()
def tool_run_npm_audit(repo_path: str) -> dict:
    """Run npm audit against the repository and return vulnerability data.

    Skips gracefully when no package.json is present.

    Args:
        repo_path: Absolute path to the repository root.

    Returns:
        Dict with keys: vulnerabilities (list), total (int), error (str|None).
    """
    return run_npm_audit(repo_path)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
