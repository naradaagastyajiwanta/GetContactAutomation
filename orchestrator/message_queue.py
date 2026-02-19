import asyncio
from typing import Any, Coroutine, Optional

import httpx

from orchestrator.config import WA_SERVICE_URL, MAX_AI_CONCURRENT, SEND_INTERVAL_MS, log


class MessageQueue:
    """Controls AI concurrency (semaphore) and serial WA message sending (queue)."""

    def __init__(
        self,
        max_ai_concurrent: int = MAX_AI_CONCURRENT,
        send_interval_ms: int = SEND_INTERVAL_MS,
    ) -> None:
        self._ai_semaphore = asyncio.Semaphore(max_ai_concurrent)
        self._send_queue: asyncio.Queue[dict] = asyncio.Queue()
        self._send_interval_s = send_interval_ms / 1000.0
        self._worker_task: Optional[asyncio.Task] = None

    # -- AI concurrency gate --------------------------------------------------

    async def process_with_ai(self, coro: Coroutine) -> Any:
        """Run *coro* while holding the AI-concurrency semaphore."""
        async with self._ai_semaphore:
            return await coro

    # -- WA send queue ---------------------------------------------------------

    async def enqueue_send(
        self,
        phone: str,
        message: str,
        reply_to_msg_key: Optional[str] = None,
    ) -> None:
        """Put an outbound WA message onto the serial send queue."""
        payload: dict = {"to": phone, "message": message}
        if reply_to_msg_key is not None:
            payload["replyToMsgKey"] = reply_to_msg_key
        await self._send_queue.put(payload)
        log.info("Enqueued WA send to %s (queue size: %d)", phone, self._send_queue.qsize())

    async def send_worker(self) -> None:
        """Background loop that drains the send queue one message at a time."""
        log.info("Send-worker started (interval=%.1fs)", self._send_interval_s)
        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                payload = await self._send_queue.get()
                try:
                    resp = await client.post(
                        f"{WA_SERVICE_URL}/send",
                        json=payload,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    if data.get("success"):
                        log.info("Sent WA message to %s", payload["to"])
                    else:
                        log.error("WA send failed for %s: %s", payload["to"], data.get("error", "unknown"))
                except Exception as exc:
                    log.error("Failed to send WA message to %s: %s", payload["to"], exc)
                finally:
                    self._send_queue.task_done()
                await asyncio.sleep(self._send_interval_s)

    def start_worker(self) -> None:
        """Spawn the send-worker as a background task on the running loop."""
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.get_event_loop().create_task(self.send_worker())


message_queue = MessageQueue()
