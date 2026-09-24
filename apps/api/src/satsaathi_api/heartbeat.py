"""Reading what the workers say about themselves, from Redis.

The GPU worker publishes its runtime snapshot under `models:gpu:heartbeat`,
and every worker publishes `workers:<queue>:heartbeat` for each queue it
consumes, all with a 15-second TTL. A missing key therefore means "nobody
has said so in the last 15 seconds" — which is what readiness needs, and it
costs the API one GET instead of a torch import or a Celery broadcast.
"""

from __future__ import annotations

import json
from typing import Any

import redis.asyncio as redis_asyncio

GPU_HEARTBEAT_KEY = "models:gpu:heartbeat"
QUEUE_HEARTBEAT_KEY = "workers:{queue}:heartbeat"


def _client(redis_url: str):
    return redis_asyncio.from_url(redis_url, socket_connect_timeout=1, socket_timeout=1)


async def gpu_heartbeat(redis_url: str) -> dict[str, Any] | None:
    """The GPU worker's last snapshot, or None when none is alive or Redis is down."""
    client = _client(redis_url)
    try:
        raw = await client.get(GPU_HEARTBEAT_KEY)
    except Exception:  # noqa: BLE001 - an unreachable broker is "no worker"
        return None
    finally:
        await client.aclose()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


async def queue_consumers(redis_url: str, queues: list[str]) -> dict[str, bool]:
    """Whether each queue has had a live consumer within the heartbeat TTL."""
    client = _client(redis_url)
    try:
        values = await client.mget([QUEUE_HEARTBEAT_KEY.format(queue=q) for q in queues])
    except Exception:  # noqa: BLE001
        return {q: False for q in queues}
    finally:
        await client.aclose()
    return {q: bool(v) for q, v in zip(queues, values, strict=True)}


def gpu_worker_alive_sync(redis_url: str) -> bool:
    """Blocking variant for the dispatcher, which runs outside the event loop."""
    import redis

    try:
        client = redis.Redis.from_url(redis_url, socket_connect_timeout=1, socket_timeout=1)
        try:
            return bool(client.exists(GPU_HEARTBEAT_KEY))
        finally:
            client.close()
    except Exception:  # noqa: BLE001
        return False
