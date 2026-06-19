"""graph.py — LangGraph StateGraph for the multi-agent code review pipeline.

Graph topology
--------------
START
  └─► ingest_node          (clone repo, chunk files, embed to Pinecone)
        └─► [fan-out via Send API]
              ├─► bug_node      (BugAgent)
              ├─► security_node (SecurityAgent)
              └─► coverage_node (CoverageAgent)
                    └─► synthesize_node   (Synthesizer)
                              └─► END

All three agent nodes run in parallel.  LangGraph's ``Send`` API is used for
the fan-out so each agent receives a full snapshot of the state at that point.
The Annotated[list, operator.add] fields in ReviewState accumulate results from
all three branches before synthesize_node executes.
"""
from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import structlog
from langgraph.constants import END, Send
from langgraph.graph import START, StateGraph

from ..agents.bug_agent import BugAgent
from ..agents.coverage_agent import CoverageAgent
from ..agents.security_agent import SecurityAgent
from ..ingestion.code_chunker import CodeChunker
from ..ingestion.git_loader import GitLoader
from .state import ReviewState
from .synthesizer import Synthesizer

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_CLONE_BASE_DIR: str = os.environ.get("CLONE_BASE_DIR", "/tmp/code-review-clones")

# Pinecone is optional — if the env var is absent we skip upsert silently.
_PINECONE_ENABLED: bool = bool(os.environ.get("PINECONE_API_KEY"))


# ===========================================================================
# Node implementations
# ===========================================================================

async def ingest_node(state: ReviewState) -> dict:
    """Clone the repository, chunk all source files, optionally embed to Pinecone.

    Returns updates for: repo_path, repo_metadata, chunks, files_analyzed,
    progress_messages.
    """
    run_id = state["run_id"]
    git_url = state["git_url"]
    openai_api_key = state["openai_api_key"]

    log.info("ingest_node.start", run_id=run_id, git_url=git_url)

    # --- Clone ---
    loader = GitLoader(clone_base_dir=_CLONE_BASE_DIR)
    try:
        repo_path_obj: Path = await loader.clone(git_url=git_url, run_id=run_id)
    except Exception as exc:
        log.error("ingest_node.clone_failed", run_id=run_id, error=str(exc))
        return {
            "error": f"Clone failed: {exc}",
            "progress_messages": [f"ERROR: failed to clone repository — {exc}"],
            "repo_path": "",
            "repo_metadata": {},
            "chunks": [],
            "files_analyzed": 0,
        }

    repo_path = str(repo_path_obj)

    # --- Metadata ---
    repo_metadata = await asyncio.to_thread(loader.get_repo_metadata, repo_path_obj)
    log.info("ingest_node.metadata", run_id=run_id, metadata=repo_metadata)

    # --- Chunk ---
    files = loader.get_files(repo_path_obj)
    chunker = CodeChunker()
    chunks: list[dict] = await asyncio.to_thread(chunker.chunk_repo, files, repo_path_obj)
    files_analyzed = len({c["file_path"] for c in chunks if "file_path" in c})

    log.info(
        "ingest_node.chunked",
        run_id=run_id,
        files=files_analyzed,
        chunks=len(chunks),
    )

    # --- Embed & upsert to Pinecone (optional) ---
    if _PINECONE_ENABLED and chunks:
        try:
            from openai import AsyncOpenAI

            from ..ingestion.embedder import ChunkEmbedder
            from ..storage.vector_store import PineconeStore

            openai_client = AsyncOpenAI(api_key=openai_api_key)
            embedder = ChunkEmbedder(openai_client=openai_client)
            embedded = await embedder.embed_chunks(chunks)

            store = PineconeStore(openai_api_key=openai_api_key)
            await store.init()
            await store.upsert_chunks(run_id=run_id, chunks=embedded)
            log.info("ingest_node.pinecone_upsert_complete", run_id=run_id, vectors=len(embedded))
        except Exception as exc:
            # Pinecone errors are non-fatal — agents can still read files directly.
            log.warning("ingest_node.pinecone_failed", run_id=run_id, error=str(exc))

    return {
        "repo_path": repo_path,
        "repo_metadata": repo_metadata,
        "chunks": chunks,
        "files_analyzed": files_analyzed,
        "progress_messages": [
            f"Repository cloned: {repo_metadata.get('name', git_url)} "
            f"({files_analyzed} files, {len(chunks)} chunks)"
        ],
        "error": None,
    }


async def bug_node(state: ReviewState) -> dict:
    """Run BugAgent and return bug_findings + progress."""
    run_id = state["run_id"]
    log.info("bug_node.start", run_id=run_id)

    agent = BugAgent(
        openai_api_key=state["openai_api_key"],
        model=state.get("openai_model", "gpt-4o"),
    )
    try:
        result = await agent.analyze(
            chunks=state.get("chunks", []),
            repo_path=state["repo_path"],
            repo_metadata=state.get("repo_metadata", {}),
            peer_findings=None,
        )
        findings = [
            {**f.model_dump(), "agent_type": "bug"}
            for f in result.findings
        ]
        summary = result.summary
        log.info("bug_node.complete", run_id=run_id, findings=len(findings))
    except Exception as exc:
        log.error("bug_node.error", run_id=run_id, error=str(exc))
        findings = []
        summary = f"Bug analysis failed: {exc}"

    return {
        "bug_findings": findings,
        "progress_messages": [f"Bug analysis complete: {summary}"],
    }


async def security_node(state: ReviewState) -> dict:
    """Run SecurityAgent (with bug findings as peer context) and return security_findings."""
    run_id = state["run_id"]
    log.info("security_node.start", run_id=run_id)

    # Pass already-completed bug findings as peer context so SecurityAgent can
    # elevate severity when a bug and security issue overlap.
    from ..agents.base_agent import AgentFinding

    peer: list[AgentFinding] = []
    for f in state.get("bug_findings", []):
        try:
            peer.append(AgentFinding(**{k: v for k, v in f.items() if k != "agent_type"}))
        except Exception:
            pass

    agent = SecurityAgent(
        openai_api_key=state["openai_api_key"],
        model=state.get("openai_model", "gpt-4o"),
    )
    try:
        result = await agent.analyze(
            chunks=state.get("chunks", []),
            repo_path=state["repo_path"],
            repo_metadata=state.get("repo_metadata", {}),
            peer_findings=peer or None,
        )
        findings = [
            {**f.model_dump(), "agent_type": "security"}
            for f in result.findings
        ]
        summary = result.summary
        log.info("security_node.complete", run_id=run_id, findings=len(findings))
    except Exception as exc:
        log.error("security_node.error", run_id=run_id, error=str(exc))
        findings = []
        summary = f"Security analysis failed: {exc}"

    return {
        "security_findings": findings,
        "progress_messages": [f"Security analysis complete: {summary}"],
    }


async def coverage_node(state: ReviewState) -> dict:
    """Run CoverageAgent (with bug + security peer findings) and return coverage_findings."""
    run_id = state["run_id"]
    log.info("coverage_node.start", run_id=run_id)

    from ..agents.base_agent import AgentFinding

    peer: list[AgentFinding] = []
    for f in [*state.get("bug_findings", []), *state.get("security_findings", [])]:
        try:
            peer.append(AgentFinding(**{k: v for k, v in f.items() if k != "agent_type"}))
        except Exception:
            pass

    agent = CoverageAgent(
        openai_api_key=state["openai_api_key"],
        model=state.get("openai_model", "gpt-4o"),
    )
    try:
        result = await agent.analyze(
            chunks=state.get("chunks", []),
            repo_path=state["repo_path"],
            repo_metadata=state.get("repo_metadata", {}),
            peer_findings=peer or None,
        )
        findings = [
            {**f.model_dump(), "agent_type": "coverage"}
            for f in result.findings
        ]
        summary = result.summary
        log.info("coverage_node.complete", run_id=run_id, findings=len(findings))
    except Exception as exc:
        log.error("coverage_node.error", run_id=run_id, error=str(exc))
        findings = []
        summary = f"Coverage analysis failed: {exc}"

    return {
        "coverage_findings": findings,
        "progress_messages": [f"Coverage analysis complete: {summary}"],
    }


async def synthesize_node(state: ReviewState) -> dict:
    """Run the Synthesizer to merge, score, and render the final report."""
    run_id = state["run_id"]
    log.info("synthesize_node.start", run_id=run_id)
    synth = Synthesizer()
    return await synth.synthesize(state)


# ===========================================================================
# Routing function for the parallel fan-out
# ===========================================================================

def route_to_agents(state: ReviewState) -> list[Send]:
    """Called after ingest_node to launch all three agent nodes in parallel.

    LangGraph's Send API schedules each node independently with a full copy
    of the current state, enabling true parallel execution.
    """
    if state.get("error"):
        # If ingestion failed, skip agents and go straight to END via synthesizer
        # (synthesizer will produce an empty/error report).
        log.warning("route_to_agents.skipping_due_to_error", run_id=state.get("run_id"))
        return [Send("synthesize_node", state)]

    return [
        Send("bug_node", state),
        Send("security_node", state),
        Send("coverage_node", state),
    ]


# ===========================================================================
# Graph construction
# ===========================================================================

def build_graph() -> Any:
    """Construct and compile the review StateGraph."""
    builder: StateGraph = StateGraph(ReviewState)

    # Nodes
    builder.add_node("ingest_node", ingest_node)
    builder.add_node("bug_node", bug_node)
    builder.add_node("security_node", security_node)
    builder.add_node("coverage_node", coverage_node)
    builder.add_node("synthesize_node", synthesize_node)

    # Edges
    builder.add_edge(START, "ingest_node")

    # Conditional fan-out: after ingest, launch all three agents in parallel
    builder.add_conditional_edges(
        "ingest_node",
        route_to_agents,
        # Explicit destination map so LangGraph can validate target node names
        ["bug_node", "security_node", "coverage_node", "synthesize_node"],
    )

    # All three agent nodes converge at synthesize_node
    builder.add_edge("bug_node", "synthesize_node")
    builder.add_edge("security_node", "synthesize_node")
    builder.add_edge("coverage_node", "synthesize_node")

    # synthesize_node → END
    builder.add_edge("synthesize_node", END)

    return builder.compile()


# Singleton compiled graph (created once at import time)
_graph = build_graph()


# ===========================================================================
# Public API
# ===========================================================================

async def run_review(
    git_url: str,
    run_id: str,
    openai_api_key: str,
    progress_callback: Callable[[str], None] | None = None,
    openai_model: str = "gpt-4o",
) -> ReviewState:
    """Execute the full code-review pipeline and return the final ReviewState.

    Parameters
    ----------
    git_url:
        Public or authenticated Git URL to review.
    run_id:
        Unique identifier for this review run (used as clone directory name,
        Pinecone namespace, and DB primary key).
    openai_api_key:
        OpenAI API key forwarded to all agents and the embedder.
    progress_callback:
        Optional synchronous callable invoked with each progress message as the
        graph streams state updates.  Use this to push messages over WebSocket.
    openai_model:
        OpenAI chat model identifier (default ``"gpt-4o"``).

    Returns
    -------
    ReviewState
        The final, fully-populated state after all nodes have executed.
    """
    log.info("run_review.start", run_id=run_id, git_url=git_url)

    initial_state: ReviewState = {
        "run_id": run_id,
        "git_url": git_url,
        "repo_path": "",
        "repo_metadata": {},
        "openai_api_key": openai_api_key,
        "openai_model": openai_model,
        "chunks": [],
        "files_analyzed": 0,
        "bug_findings": [],
        "security_findings": [],
        "coverage_findings": [],
        "all_findings": [],
        "production_score": 0.0,
        "production_verdict": "",
        "report_markdown": "",
        "report_json": {},
        "progress_messages": [f"Starting review for {git_url}"],
        "error": None,
    }

    final_state: ReviewState | None = None

    # Stream execution so we can fire progress callbacks as nodes complete.
    async for chunk in _graph.astream(initial_state, stream_mode="updates"):
        # chunk is a dict[node_name, partial_state_update]
        for node_name, node_output in chunk.items():
            messages: list[str] = node_output.get("progress_messages") or []
            for msg in messages:
                log.debug("progress", run_id=run_id, node=node_name, message=msg)
                if progress_callback is not None:
                    try:
                        progress_callback(msg)
                    except Exception as cb_exc:
                        log.warning(
                            "progress_callback.error",
                            run_id=run_id,
                            error=str(cb_exc),
                        )

    # Retrieve the final accumulated state
    final_state = await _graph.aget_state(
        config={"configurable": {"thread_id": run_id}}
    )

    # aget_state returns a StateSnapshot; extract .values for the raw dict.
    # If we got a snapshot, unwrap it.
    if hasattr(final_state, "values"):
        result: ReviewState = final_state.values  # type: ignore[assignment]
    elif final_state is not None:
        result = final_state  # type: ignore[assignment]
    else:
        # Fallback: re-invoke without streaming to get the final state
        result = await _graph.ainvoke(initial_state)

    log.info(
        "run_review.complete",
        run_id=run_id,
        score=result.get("production_score"),
        verdict=result.get("production_verdict"),
        findings=len(result.get("all_findings") or []),
    )
    return result


async def run_review_streaming(
    git_url: str,
    run_id: str,
    openai_api_key: str,
    openai_model: str = "gpt-4o",
) -> AsyncIterator[tuple[str, dict]]:
    """Async generator that yields ``(node_name, partial_state)`` tuples as nodes complete.

    Useful for WebSocket handlers that want fine-grained streaming control.

    Usage::

        async for node_name, update in run_review_streaming(url, run_id, key):
            await ws.send_json({"node": node_name, "update": update})
    """
    initial_state: ReviewState = {
        "run_id": run_id,
        "git_url": git_url,
        "repo_path": "",
        "repo_metadata": {},
        "openai_api_key": openai_api_key,
        "openai_model": openai_model,
        "chunks": [],
        "files_analyzed": 0,
        "bug_findings": [],
        "security_findings": [],
        "coverage_findings": [],
        "all_findings": [],
        "production_score": 0.0,
        "production_verdict": "",
        "report_markdown": "",
        "report_json": {},
        "progress_messages": [f"Starting review for {git_url}"],
        "error": None,
    }

    async for chunk in _graph.astream(initial_state, stream_mode="updates"):
        for node_name, node_output in chunk.items():
            yield node_name, node_output
