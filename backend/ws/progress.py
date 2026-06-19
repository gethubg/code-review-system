from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Literal

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

log = structlog.get_logger(__name__)

router = APIRouter(tags=["websocket"])

# Module-level registry: run_id -> list of active queues.
# Using a list allows multiple clients to subscribe to the same run.
_queues: dict[str, list[asyncio.Queue]] = {}

MessageType = Literal["progress", "complete", "error"]


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


async def push_progress(
    run_id: str,
    message: str,
    msg_type: MessageType = "progress",
) -> None:
    """Push a progress message to all WebSocket clients watching *run_id*.

    This is a no-op when no clients are connected, so the orchestrator can
    call it unconditionally without risk of blocking.
    """
    payload = {
        "type": msg_type,
        "message": message,
        "timestamp": _now_iso(),
    }

    queues = _queues.get(run_id, [])
    for q in queues:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            log.warning("ws_queue_full", run_id=run_id)

    log.debug("progress_pushed", run_id=run_id, msg_type=msg_type, message=message)


@router.websocket("/ws/progress/{run_id}")
async def ws_progress(websocket: WebSocket, run_id: str) -> None:
    """WebSocket endpoint that streams review progress events for *run_id*."""
    await websocket.accept()

    queue: asyncio.Queue = asyncio.Queue(maxsize=200)

    # Register this client's queue
    if run_id not in _queues:
        _queues[run_id] = []
    _queues[run_id].append(queue)

    log.info("ws_client_connected", run_id=run_id)

    try:
        while True:
            try:
                # Wait up to 30 s for a message; send a heartbeat if nothing arrives.
                payload = await asyncio.wait_for(queue.get(), timeout=30.0)
            except asyncio.TimeoutError:
                # Heartbeat keeps the connection alive
                await websocket.send_json(
                    {"type": "heartbeat", "timestamp": _now_iso()}
                )
                continue

            await websocket.send_json(payload)

            # Stop streaming once the run reaches a terminal state.
            if payload.get("type") in ("complete", "error"):
                break

    except WebSocketDisconnect:
        log.info("ws_client_disconnected", run_id=run_id)
    except Exception as exc:
        log.exception("ws_error", run_id=run_id, error=str(exc))
    finally:
        # Deregister this queue
        queues = _queues.get(run_id, [])
        if queue in queues:
            queues.remove(queue)
        if not queues:
            _queues.pop(run_id, None)
        log.debug("ws_queue_cleaned", run_id=run_id)
