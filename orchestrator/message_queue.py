import asyncio
import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Coroutine, Optional

import httpx

from orchestrator.config import WA_SERVICE_URL, log, cfg
from orchestrator.websocket import manager as ws_manager

MAX_SEND_RETRIES = 3
RETRY_DELAYS = [2, 5, 10]  # seconds – exponential backoff


@dataclass
class SendAttemptResult:
    success: bool
    blocked: bool = False
    error: str | None = None
    retry_after_ms: int | None = None
    anti_ban: dict[str, Any] | None = None


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
        reply_to_msg_key: Optional[Any] = None,
        all_msg_keys: Optional[list] = None,
        device_id: str = "device_1",
    ) -> None:
        """Put an outbound WA message onto the serial send queue."""
        payload: dict = {
            "to": phone,
            "message": message,
            "_type": "text",
            "device_id": device_id,
        }
        if reply_to_msg_key is not None:
            payload["replyToMsgKey"] = reply_to_msg_key
        if all_msg_keys is not None:
            payload["allMsgKeys"] = all_msg_keys
        await self._send_queue.put(payload)
        log.info("Enqueued WA send to %s via %s (queue size: %d)", phone, device_id, self._send_queue.qsize())

    async def enqueue_send_document(
        self,
        phone: str,
        file_path: str,
        file_name: str,
        caption: str | None = None,
        device_id: str = "device_1",
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
            "device_id": device_id,
        }
        if caption:
            payload["caption"] = caption
        await self._send_queue.put(payload)
        log.info("Enqueued WA document to %s via %s (%s, queue size: %d)", phone, device_id, file_name, self._send_queue.qsize())

    async def _send_single(self, client: httpx.AsyncClient, payload: dict) -> SendAttemptResult:
        """Try to send a single message with retry and return structured status."""
        msg_type = payload.get("_type", "text")
        endpoint = "/send-document" if msg_type == "document" else "/send"
        send_payload = {k: v for k, v in payload.items() if k != "_type"}

        for attempt in range(MAX_SEND_RETRIES + 1):
            try:
                resp = await client.post(
                    f"{WA_SERVICE_URL}/{endpoint.lstrip('/')}",
                    json=send_payload,
                )
                data = resp.json()

                if resp.status_code == 429 and data.get("blocked"):
                    error = data.get("error", "Blocked by anti-ban policy")
                    log.warning(
                        "WA send blocked by anti-ban for %s: %s",
                        payload["to"],
                        error,
                    )
                    return SendAttemptResult(
                        success=False,
                        blocked=True,
                        error=error,
                        retry_after_ms=data.get("retryAfterMs"),
                        anti_ban=data.get("antiBan"),
                    )

                resp.raise_for_status()
                if data.get("success"):
                    log.info("Sent WA %s to %s", msg_type, payload["to"])
                    # Broadcast message sent event
                    from datetime import datetime, timezone
                    await ws_manager.broadcast_type(
                        "message_sent",
                        phone=payload["to"],
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    )
                    return SendAttemptResult(success=True, anti_ban=data.get("antiBan"))
                else:
                    error = data.get("error", "unknown")
                    # "not connected" is transient — worth retrying
                    if "not connected" in error.lower():
                        if attempt < MAX_SEND_RETRIES:
                            delay = RETRY_DELAYS[attempt]
                            log.warning(
                                "WA not connected, retry %d/%d in %ds",
                                attempt + 1, MAX_SEND_RETRIES, delay,
                            )
                            await asyncio.sleep(delay)
                            continue
                    # Permanent failure or retries exhausted
                    log.error("WA send failed for %s: %s", payload["to"], error)
                    return SendAttemptResult(success=False, error=error, anti_ban=data.get("antiBan"))
            except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as exc:
                if attempt < MAX_SEND_RETRIES:
                    delay = RETRY_DELAYS[attempt]
                    log.warning(
                        "WA send error (retry %d/%d in %ds): %s",
                        attempt + 1, MAX_SEND_RETRIES, delay, exc,
                    )
                    await asyncio.sleep(delay)
                else:
                    log.critical(
                        "WA send FAILED after %d retries for %s: %s",
                        MAX_SEND_RETRIES, payload["to"], exc,
                    )
                    return SendAttemptResult(success=False, error=str(exc))
            except Exception as exc:
                # Unexpected / non-retryable error — don't retry
                log.error("WA send unexpected error for %s: %s", payload["to"], exc)
                return SendAttemptResult(success=False, error=str(exc))
        return SendAttemptResult(success=False, error="Unknown send failure")

    async def send_worker(self) -> None:
        """Background loop that drains the send queue one message at a time."""
        log.info("Send-worker started (interval read from cfg.SEND_INTERVAL_MS)")
        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                payload = await self._send_queue.get()
                try:
                    await self._send_single(client, payload)
                finally:
                    self._send_queue.task_done()
                await asyncio.sleep(cfg.SEND_INTERVAL_MS / 1000.0)

    async def send_now(
        self,
        phone: str,
        message: str,
        device_id: str = "device_1",
    ) -> bool:
        """Send a WA message immediately (bypasses queue) and return True on success.

        Use this when the caller needs to know whether the send succeeded
        (e.g. blast worker) rather than fire-and-forget via enqueue_send.
        """
        payload = {
            "to": phone,
            "message": message,
            "device_id": device_id,
            "_type": "text",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            result = await self._send_single(client, payload)
            return result.success

    async def send_now_detailed(
        self,
        phone: str,
        message: str,
        device_id: str = "device_1",
    ) -> SendAttemptResult:
        """Send a WA message immediately and return detailed anti-ban aware status."""
        payload = {
            "to": phone,
            "message": message,
            "device_id": device_id,
            "_type": "text",
        }
        async with httpx.AsyncClient(timeout=30) as client:
            return await self._send_single(client, payload)

    def start_worker(self) -> None:
        """Spawn the send-worker as a background task on the running loop."""
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.get_event_loop().create_task(self.send_worker())


message_queue = MessageQueue()
