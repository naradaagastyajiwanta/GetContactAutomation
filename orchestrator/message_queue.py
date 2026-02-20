import asyncio
import base64
from pathlib import Path
from typing import Any, Coroutine, Optional

import httpx

from orchestrator.config import WA_SERVICE_URL, log, cfg


class MessageQueue:
    """Controls AI concurrency (semaphore) and serial WA message sending (queue)."""

    def __init__(self) -> None:
        self._ai_semaphore = asyncio.Semaphore(cfg.MAX_AI_CONCURRENT)
        self._send_queue: asyncio.Queue[dict] = asyncio.Queue()
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
        payload: dict = {"to": phone, "message": message, "_type": "text"}
        if reply_to_msg_key is not None:
            payload["replyToMsgKey"] = reply_to_msg_key
        await self._send_queue.put(payload)
        log.info("Enqueued WA send to %s (queue size: %d)", phone, self._send_queue.qsize())

    async def enqueue_send_document(
        self,
        phone: str,
        file_path: str,
        file_name: str,
        caption: str | None = None,
    ) -> None:
        """Put an outbound WA document message onto the serial send queue."""
        path = Path(file_path)
        if not path.exists():
            log.error("enqueue_send_document: file not found: %s", file_path)
            return
        file_bytes = path.read_bytes()
        file_b64 = base64.b64encode(file_bytes).decode("ascii")

        # Determine mimetype from extension
        ext = path.suffix.lower()
        mimetypes = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".doc": "application/msword",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
        }
        mimetype = mimetypes.get(ext, "application/octet-stream")

        payload: dict = {
            "_type": "document",
            "to": phone,
            "fileBase64": file_b64,
            "fileName": file_name,
            "mimetype": mimetype,
        }
        if caption:
            payload["caption"] = caption
        await self._send_queue.put(payload)
        log.info("Enqueued WA document to %s (%s, queue size: %d)", phone, file_name, self._send_queue.qsize())

    async def send_worker(self) -> None:
        """Background loop that drains the send queue one message at a time."""
        log.info("Send-worker started (interval read from cfg.SEND_INTERVAL_MS)")
        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                payload = await self._send_queue.get()
                try:
                    msg_type = payload.pop("_type", "text")
                    if msg_type == "document":
                        resp = await client.post(
                            f"{WA_SERVICE_URL}/send-document",
                            json=payload,
                        )
                    else:
                        resp = await client.post(
                            f"{WA_SERVICE_URL}/send",
                            json=payload,
                        )
                    resp.raise_for_status()
                    data = resp.json()
                    if data.get("success"):
                        log.info("Sent WA %s to %s", msg_type, payload["to"])
                    else:
                        log.error("WA send failed for %s: %s", payload["to"], data.get("error", "unknown"))
                except Exception as exc:
                    log.error("Failed to send WA message to %s: %s", payload["to"], exc)
                finally:
                    self._send_queue.task_done()
                await asyncio.sleep(cfg.SEND_INTERVAL_MS / 1000.0)

    def start_worker(self) -> None:
        """Spawn the send-worker as a background task on the running loop."""
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.get_event_loop().create_task(self.send_worker())


message_queue = MessageQueue()
