import hashlib
import uuid
from pathlib import Path

import structlog
from llama_index.core import Document
from llama_index.core.node_parser import CodeSplitter

log = structlog.get_logger()

# Map file extensions to tree-sitter language names understood by CodeSplitter
EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".cs": "c_sharp",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
}

# Extensions that fall back to plain line-based splitting
_TEXT_EXTENSIONS: set[str] = {
    ".yaml", ".yml", ".json", ".toml", ".sh", ".sql", ".md",
}


def _detect_language(file_path: Path) -> str | None:
    """Return the tree-sitter language name for *file_path*, or ``None`` for plain text."""
    return EXTENSION_TO_LANGUAGE.get(file_path.suffix.lower())


def _chunk_id(file_path_rel: str, chunk_index: int) -> str:
    """Deterministic, URL-safe chunk identifier."""
    raw = f"{file_path_rel}::{chunk_index}"
    return hashlib.sha1(raw.encode()).hexdigest()  # noqa: S324 (not crypto)


class CodeChunker:
    """Split source files into overlapping chunks suitable for embedding."""

    def __init__(
        self,
        chunk_lines: int = 50,
        chunk_lines_overlap: int = 5,
        max_chars: int = 2000,
    ) -> None:
        self.chunk_lines = chunk_lines
        self.chunk_lines_overlap = chunk_lines_overlap
        self.max_chars = max_chars

        # We create per-language splitters lazily and cache them.
        self._splitter_cache: dict[str, CodeSplitter] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_splitter(self, language: str) -> CodeSplitter:
        if language not in self._splitter_cache:
            self._splitter_cache[language] = CodeSplitter(
                language=language,
                chunk_lines=self.chunk_lines,
                chunk_lines_overlap=self.chunk_lines_overlap,
                max_chars=self.max_chars,
            )
        return self._splitter_cache[language]

    def _split_plain_text(self, text: str) -> list[str]:
        """Simple line-window split for non-code files."""
        lines = text.splitlines(keepends=True)
        step = max(1, self.chunk_lines - self.chunk_lines_overlap)
        chunks: list[str] = []
        i = 0
        while i < len(lines):
            chunk_lines = lines[i : i + self.chunk_lines]
            chunks.append("".join(chunk_lines))
            if i + self.chunk_lines >= len(lines):
                break
            i += step
        return chunks

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chunk_file(self, file_path: Path, repo_path: Path) -> list[dict]:
        """Chunk a single file and return a list of chunk dicts.

        Each chunk dict contains:
        ``{id, text, file_path, start_line, end_line, language, chunk_index, char_count}``
        """
        rel_path = str(file_path.relative_to(repo_path))

        try:
            raw_text = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            log.warning("file_read_error", path=rel_path, error=str(exc))
            return []

        if not raw_text.strip():
            return []

        language = _detect_language(file_path)
        chunks: list[dict] = []

        if language is not None:
            # Use LlamaIndex CodeSplitter
            try:
                splitter = self._get_splitter(language)
                doc = Document(text=raw_text, metadata={"file_path": rel_path})
                nodes = splitter.get_nodes_from_documents([doc])
                for idx, node in enumerate(nodes):
                    chunk_text = node.get_content()
                    # LlamaIndex stores line numbers in node metadata when available
                    node_meta = node.metadata or {}
                    start_line: int = node_meta.get("start_line_idx", 0)
                    end_line: int = node_meta.get("end_line_idx", start_line + chunk_text.count("\n"))
                    chunks.append(
                        {
                            "id": _chunk_id(rel_path, idx),
                            "text": chunk_text,
                            "file_path": rel_path,
                            "start_line": start_line,
                            "end_line": end_line,
                            "language": language,
                            "chunk_index": idx,
                            "char_count": len(chunk_text),
                        }
                    )
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "code_splitter_failed_falling_back",
                    path=rel_path,
                    language=language,
                    error=str(exc),
                )
                # Fall through to plain-text splitting
                language = None

        if language is None:
            # Plain-text / unknown-language fallback
            lang_label = file_path.suffix.lstrip(".") or "text"
            raw_chunks = self._split_plain_text(raw_text)
            all_lines = raw_text.splitlines()
            cursor = 0
            for idx, chunk_text in enumerate(raw_chunks):
                chunk_line_count = chunk_text.count("\n") + 1
                start = cursor
                end = min(cursor + chunk_line_count - 1, len(all_lines) - 1)
                chunks.append(
                    {
                        "id": _chunk_id(rel_path, idx),
                        "text": chunk_text,
                        "file_path": rel_path,
                        "start_line": start,
                        "end_line": end,
                        "language": lang_label,
                        "chunk_index": idx,
                        "char_count": len(chunk_text),
                    }
                )
                step = max(1, self.chunk_lines - self.chunk_lines_overlap)
                cursor += step

        log.debug("file_chunked", path=rel_path, chunks=len(chunks))
        return chunks

    def chunk_repo(self, files: list[Path], repo_path: Path) -> list[dict]:
        """Chunk all *files* and return a flat list of chunk dicts.

        Skips files that produce zero chunks (empty or unreadable).
        """
        all_chunks: list[dict] = []
        for file_path in files:
            file_chunks = self.chunk_file(file_path, repo_path)
            all_chunks.extend(file_chunks)

        log.info(
            "repo_chunked",
            repo=str(repo_path),
            files_processed=len(files),
            total_chunks=len(all_chunks),
        )
        return all_chunks
