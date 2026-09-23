"""Job step events, from the worker to every connected browser.

Redis pub/sub is the transport so any API process can serve any job's stream,
regardless of which worker is running it. An in-process fallback exists for
tests and single-process development, and it is explicit rather than silent:
a stream backed by the fallback cannot see events from another process, so the
caller is told which one it got.

Subscribers always receive a full snapshot, never a delta. A browser that
reconnects mid-job therefore recovers by receiving the next snapshot, and does
not have to replay anything it missed.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncGenerator
from typing import Any, Protocol

CHANNEL_PREFIX = "satsaathi:job:"


def channel_for(job_id: str) -> str:
    return f"{CHANNEL_PREFIX}{job_id}"


class EventBus(Protocol):
    async def publish(self, job_id: str, payload: dict[str, Any]) -> None: ...

    def subscribe(self, job_id: str) -> AsyncGenerator[dict[str, Any], None]: ...


class InProcessEventBus:
    """Single-process bus. Fine for tests; useless across processes."""

    is_cross_process = False

    def __init__(self) -> None:
        self._queues: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._last: dict[str, dict[str, Any]] = {}

    async def publish(self, job_id: str, payload: dict[str, Any]) -> None:
        self._last[job_id] = payload
        for queue in list(self._queues.get(job_id, ())):
            queue.put_nowait(payload)

    async def subscribe(self, job_id: str) -> AsyncGenerator[dict[str, Any], None]:
        queue: asyncio.Queue = asyncio.Queue()
        self._queues[job_id].add(queue)
        try:
            # Reconnecting clients need current state, not just future changes.
            if job_id in self._last:
                yield self._last[job_id]
            while True:
                yield await queue.get()
        finally:
            self._queues[job_id].discard(queue)
            if not self._queues[job_id]:
                self._queues.pop(job_id, None)


class RedisEventBus:
    """Cross-process bus. Publishing never blocks the pipeline."""

    is_cross_process = True

    def __init__(self, url: str):
        self.url = url
        self._client = None

    def _connect(self):
        if self._client is None:
            import redis.asyncio as redis_asyncio

            self._client = redis_asyncio.from_url(
                self.url, decode_responses=True, socket_connect_timeout=2
            )
        return self._client

    async def publish(self, job_id: str, payload: dict[str, Any]) -> None:
        client = self._connect()
        await client.publish(channel_for(job_id), json.dumps(payload))

    async def subscribe(self, job_id: str) -> AsyncGenerator[dict[str, Any], None]:
        client = self._connect()
        pubsub = client.pubsub()
        await pubsub.subscribe(channel_for(job_id))
        try:
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                try:
                    yield json.loads(message["data"])
                except (TypeError, ValueError):
                    # A malformed payload must not kill a live stream.
                    continue
        finally:
            await pubsub.unsubscribe(channel_for(job_id))
            await pubsub.aclose()

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


def publish_sync(url: str, job_id: str, payload: dict[str, Any]) -> None:
    """Publish from synchronous code — the Celery worker runs sync."""
    import redis

    client = redis.from_url(url, socket_connect_timeout=2)
    try:
        client.publish(channel_for(job_id), json.dumps(payload))
    finally:
        client.close()
