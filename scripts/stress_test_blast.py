#!/usr/bin/env python3
"""Run an end-to-end stress test for WhatsApp blast campaigns.

This script exercises the actual blast flow used by the orchestrator:
1. Validates the target WhatsApp device is connected.
2. Optionally resets the device anti-ban state.
3. Creates a temporary blast campaign.
4. Adds recipients from CLI flags or a file.
5. Starts the campaign and polls campaign + anti-ban status.
6. Prints a concise summary and optionally cleans the campaign up.

Recommended usage:
  python scripts/stress_test_blast.py \
      --recipient 62812xxxx001 \
      --recipient 62812xxxx002 \
      --reset-antiban \
      --cleanup

Recipient file formats:
  - .json: [{"phone_number": "628...", "contact_name": "T1"}]
  - text: one recipient per line in the form
      62812xxxx001|Tester 1|Internal QA
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_TEMPLATE = "Stress test message for {nama_kontak}."


@dataclass
class Recipient:
    phone_number: str
    contact_name: str | None = None
    university_name: str | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"phone_number": self.phone_number}
        if self.contact_name:
            payload["contact_name"] = self.contact_name
        if self.university_name:
            payload["university_name"] = self.university_name
        return payload


class StressTestError(RuntimeError):
    """Raised when the stress test cannot continue safely."""


@dataclass
class StageResult:
    campaign_id: int
    campaign_name: str
    final_campaign: dict[str, Any]
    final_antiban: dict[str, Any]
    failed_rows: list[dict[str, Any]]
    exit_code: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stress-test the real blast pipeline against anti-ban controls.",
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Orchestrator base URL")
    parser.add_argument("--device-id", default="device_1", help="WhatsApp device id")
    parser.add_argument(
        "--recipient",
        action="append",
        default=[],
        help="Recipient spec: PHONE or PHONE|NAME|UNIVERSITY. Repeatable.",
    )
    parser.add_argument(
        "--recipients-file",
        help="Path to .json or text file containing recipients",
    )
    parser.add_argument("--campaign-name", help="Override generated campaign name")
    parser.add_argument("--template-message", default=DEFAULT_TEMPLATE, help="Blast template message")
    parser.add_argument("--delay-between-ms", type=int, default=500, help="Base blast delay")
    parser.add_argument("--human-delay-min-ms", type=int, default=0, help="Campaign human min delay")
    parser.add_argument("--human-delay-max-ms", type=int, default=0, help="Campaign human max delay")
    parser.add_argument("--poll-seconds", type=float, default=5.0, help="Polling interval in seconds")
    parser.add_argument("--timeout-minutes", type=float, default=45.0, help="Max runtime before timeout")
    parser.add_argument(
        "--ramp-sizes",
        help="Comma-separated stage sizes, for example 20,50,100. Each stage uses the first N recipients.",
    )
    parser.add_argument(
        "--reset-between-stages",
        action="store_true",
        help="Reset anti-ban state before every ramp stage instead of only before the first stage.",
    )
    parser.add_argument(
        "--reset-antiban",
        action="store_true",
        help="Reset device anti-ban state before starting",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Cancel/delete the campaign after the test completes",
    )
    parser.add_argument(
        "--allow-paused-complete",
        action="store_true",
        help="Treat a paused campaign as a valid end-state for manual inspection",
    )
    return parser.parse_args()


def parse_recipient_spec(spec: str) -> Recipient:
    raw = spec.strip()
    if not raw:
        raise StressTestError("Empty recipient spec")

    if "|" in raw:
        parts = [part.strip() for part in raw.split("|", 2)]
    elif "," in raw:
        parts = [part.strip() for part in raw.split(",", 2)]
    else:
        parts = [raw]

    phone_number = parts[0]
    if not phone_number:
        raise StressTestError(f"Invalid recipient spec: {spec}")

    contact_name = parts[1] if len(parts) > 1 and parts[1] else None
    university_name = parts[2] if len(parts) > 2 and parts[2] else None
    return Recipient(
        phone_number=phone_number,
        contact_name=contact_name,
        university_name=university_name,
    )


def load_recipients_from_file(file_path: str) -> list[Recipient]:
    path = Path(file_path)
    if not path.exists():
        raise StressTestError(f"Recipients file not found: {path}")

    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise StressTestError("JSON recipients file must contain a list")

        recipients: list[Recipient] = []
        for item in data:
            if not isinstance(item, dict):
                raise StressTestError("Each JSON recipient must be an object")
            phone_number = str(item.get("phone_number", "")).strip()
            if not phone_number:
                raise StressTestError("Each JSON recipient must include phone_number")
            recipients.append(
                Recipient(
                    phone_number=phone_number,
                    contact_name=str(item.get("contact_name", "")).strip() or None,
                    university_name=str(item.get("university_name", "")).strip() or None,
                )
            )
        return recipients

    recipients = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        recipients.append(parse_recipient_spec(stripped))
    return recipients


def load_recipients(args: argparse.Namespace) -> list[Recipient]:
    recipients = [parse_recipient_spec(spec) for spec in args.recipient]
    if args.recipients_file:
        recipients.extend(load_recipients_from_file(args.recipients_file))

    deduped: dict[str, Recipient] = {}
    for recipient in recipients:
        deduped[recipient.phone_number] = recipient

    result = list(deduped.values())
    if not result:
        raise StressTestError("Provide at least one recipient with --recipient or --recipients-file")
    return result


def parse_ramp_sizes(raw: str | None) -> list[int]:
    if not raw:
        return []

    sizes: list[int] = []
    for part in raw.split(","):
        stripped = part.strip()
        if not stripped:
            continue
        try:
            size = int(stripped)
        except ValueError as exc:
            raise StressTestError(f"Invalid ramp size: {stripped}") from exc
        if size <= 0:
            raise StressTestError(f"Ramp size must be > 0: {size}")
        sizes.append(size)

    if not sizes:
        raise StressTestError("Ramp sizes were provided but no valid values were found")

    ordered = sorted(sizes)
    if ordered != sizes:
        raise StressTestError("Ramp sizes must be ascending, for example 20,50,100")
    return sizes


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def format_timestamp(value: str | None) -> str:
    parsed = parse_iso_datetime(value)
    if not parsed:
        return "-"
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def format_epoch_ms(value: int | float | None) -> str:
    if value is None:
        return "-"
    parsed = datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc)
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def format_eta(target: str | None) -> str:
    parsed = parse_iso_datetime(target)
    if not parsed:
        return "-"
    delta = parsed - utc_now()
    seconds = int(delta.total_seconds())
    if seconds <= 0:
        return "now"
    minutes, remainder = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}h {minutes}m {remainder}s"
    if minutes > 0:
        return f"{minutes}m {remainder}s"
    return f"{remainder}s"


def summarize_health(anti_ban: dict[str, Any] | None) -> str:
    if not anti_ban:
        return "risk=-"

    health = anti_ban.get("health", {})
    rate_limit = anti_ban.get("rateLimit", {})
    warm_up = anti_ban.get("warmUp", {})
    return (
        f"risk={health.get('risk', '-')}/{health.get('score', '-')} "
        f"minute={rate_limit.get('lastMinute', '-')} "
        f"hour={rate_limit.get('lastHour', '-')} "
        f"day={rate_limit.get('lastDay', '-')} "
        f"warmup={warm_up.get('todaySent', '-')}/{warm_up.get('todayLimit', '-')}"
    )


class StressTestClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=30)

    async def close(self) -> None:
        await self.client.aclose()

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self.client.request(method, path, **kwargs)
        try:
            payload = response.json()
        except ValueError as exc:
            raise StressTestError(f"{method} {path} returned non-JSON response") from exc

        if response.status_code >= 400:
            raise StressTestError(f"{method} {path} failed: {payload}")
        return payload

    async def get_wa_status(self) -> dict[str, Any]:
        return await self.request("GET", "/wa/status")

    async def get_antiban(self, device_id: str) -> dict[str, Any]:
        payload = await self.request("GET", f"/wa/devices/{device_id}/antiban")
        anti_ban = payload.get("antiBan")
        if not isinstance(anti_ban, dict):
            raise StressTestError(f"Unexpected anti-ban payload: {payload}")
        return anti_ban

    async def reset_antiban(self, device_id: str) -> dict[str, Any]:
        return await self.request("POST", f"/wa/devices/{device_id}/antiban/reset")

    async def create_campaign(
        self,
        args: argparse.Namespace,
        campaign_name: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "name": campaign_name
            or args.campaign_name
            or f"stress-test-{args.device_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            "template_message": args.template_message,
            "device_id": args.device_id,
            "delay_between_ms": args.delay_between_ms,
            "human_delay_min_ms": args.human_delay_min_ms,
            "human_delay_max_ms": args.human_delay_max_ms,
            "content_variation_enabled": True,
            "schedule_enabled": False,
            "auto_resume_enabled": True,
        }
        return await self.request("POST", "/blast/campaigns", json=payload)

    async def add_recipients(self, campaign_id: int, recipients: list[Recipient]) -> dict[str, Any]:
        payload = {"recipients": [recipient.to_payload() for recipient in recipients]}
        return await self.request("POST", f"/blast/campaigns/{campaign_id}/recipients", json=payload)

    async def start_campaign(self, campaign_id: int) -> dict[str, Any]:
        return await self.request("POST", f"/blast/campaigns/{campaign_id}/start")

    async def get_campaign(self, campaign_id: int) -> dict[str, Any]:
        return await self.request("GET", f"/blast/campaigns/{campaign_id}")

    async def get_recipients(
        self,
        campaign_id: int,
        status: str | None = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> dict[str, Any]:
        params = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        return await self.request("GET", f"/blast/campaigns/{campaign_id}/recipients", params=params)

    async def cancel_campaign(self, campaign_id: int) -> dict[str, Any]:
        return await self.request("POST", f"/blast/campaigns/{campaign_id}/cancel")

    async def delete_campaign(self, campaign_id: int) -> dict[str, Any]:
        return await self.request("DELETE", f"/blast/campaigns/{campaign_id}")


async def preflight(client: StressTestClient, device_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    wa_status = await client.get_wa_status()
    devices = wa_status.get("devices", [])
    device = next((item for item in devices if item.get("id") == device_id), None)
    if not device:
        raise StressTestError(f"Device not found in /wa/status: {device_id}")
    is_connected = bool(device.get("connected")) or str(device.get("connectionState", "")).lower() == "connected"
    if not is_connected:
        raise StressTestError(f"Device {device_id} is not connected")
    anti_ban = await client.get_antiban(device_id)
    return device, anti_ban


def print_preflight(device: dict[str, Any], anti_ban: dict[str, Any]) -> None:
    print("Preflight")
    print(f"  Device:        {device.get('id')}")
    print(f"  Phone:         {device.get('phoneNumber') or '-'}")
    is_connected = bool(device.get("connected")) or str(device.get("connectionState", "")).lower() == "connected"
    print(f"  Connected:     {is_connected}")
    print(f"  Anti-ban:      {summarize_health(anti_ban)}")
    print(f"  Next allowed:  {format_epoch_ms(anti_ban.get('nextAllowedAt'))}")
    print()


async def monitor_campaign(
    client: StressTestClient,
    campaign_id: int,
    device_id: str,
    poll_seconds: float,
    timeout_minutes: float,
    allow_paused_complete: bool,
) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + (timeout_minutes * 60.0)
    last_line = ""

    while True:
        campaign = await client.get_campaign(campaign_id)
        anti_ban = await client.get_antiban(device_id)

        total = int(campaign.get("total_recipients", 0))
        sent = int(campaign.get("sent_count", 0))
        failed = int(campaign.get("failed_count", 0))
        pending = max(total - sent - failed, 0)
        status = campaign.get("status", "unknown")

        line = (
            f"[{datetime.now().strftime('%H:%M:%S')}] "
            f"status={status} sent={sent}/{total} failed={failed} pending={pending} "
            f"{summarize_health(anti_ban)}"
        )

        paused_reason = campaign.get("paused_reason")
        auto_resume_at = campaign.get("auto_resume_at")
        if paused_reason:
            line += f" paused_reason={paused_reason!r}"
        if auto_resume_at:
            line += f" auto_resume_in={format_eta(auto_resume_at)}"

        if line != last_line:
            print(line)
            last_line = line

        if status in {"completed", "cancelled"}:
            return {"campaign": campaign, "anti_ban": anti_ban}

        if status == "paused" and allow_paused_complete:
            return {"campaign": campaign, "anti_ban": anti_ban}

        if asyncio.get_running_loop().time() >= deadline:
            raise StressTestError(f"Timed out waiting for campaign {campaign_id}")

        await asyncio.sleep(poll_seconds)


async def cleanup_campaign(client: StressTestClient, campaign_id: int) -> None:
    campaign = await client.get_campaign(campaign_id)
    status = campaign.get("status")
    if status in {"sending", "paused"}:
        await client.cancel_campaign(campaign_id)
        campaign = await client.get_campaign(campaign_id)
        status = campaign.get("status")
    if status in {"draft", "completed", "cancelled"}:
        await client.delete_campaign(campaign_id)


def print_summary(result: StageResult) -> None:
    final_campaign = result.final_campaign
    final_antiban = result.final_antiban

    print()
    print("Summary")
    print(f"  Campaign id:   {result.campaign_id}")
    print(f"  Campaign name: {result.campaign_name}")
    print(f"  Status:        {final_campaign.get('status')}")
    print(f"  Started at:    {format_timestamp(final_campaign.get('started_at'))}")
    print(f"  Paused at:     {format_timestamp(final_campaign.get('paused_at'))}")
    print(f"  Completed at:  {format_timestamp(final_campaign.get('completed_at'))}")
    print(f"  Sent:          {final_campaign.get('sent_count')}/{final_campaign.get('total_recipients')}")
    print(f"  Failed:        {final_campaign.get('failed_count')}")
    print(f"  Pause reason:  {final_campaign.get('paused_reason') or '-'}")
    print(f"  Auto resume:   {format_timestamp(final_campaign.get('auto_resume_at'))}")
    print(f"  Final anti-ban:{' '}{summarize_health(final_antiban)}")

    if result.failed_rows:
        print("  Failed rows:")
        for row in result.failed_rows[:10]:
            print(
                f"    - {row.get('phone_number')}: {row.get('error_message') or 'unknown error'}"
            )
        if len(result.failed_rows) > 10:
            print(f"    ... and {len(result.failed_rows) - 10} more")


async def run_stage(
    client: StressTestClient,
    args: argparse.Namespace,
    recipients: list[Recipient],
    stage_label: str | None = None,
) -> StageResult:
    campaign_id: int | None = None
    campaign_name = args.campaign_name or f"stress-test-{args.device_id}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    if stage_label:
        campaign_name = f"{campaign_name}-{stage_label}"

    try:
        campaign_result = await client.create_campaign(args, campaign_name=campaign_name)
        campaign = campaign_result["campaign"]
        campaign_id = int(campaign["id"])
        print(f"Created campaign {campaign_id}: {campaign['name']}")

        add_result = await client.add_recipients(campaign_id, recipients)
        print(
            f"Added recipients: added={add_result.get('added')} skipped={add_result.get('skipped')} total={add_result.get('total')}"
        )

        start_result = await client.start_campaign(campaign_id)
        print(f"Start result: {start_result}")
        print()

        monitor_result = await monitor_campaign(
            client,
            campaign_id,
            args.device_id,
            args.poll_seconds,
            args.timeout_minutes,
            args.allow_paused_complete,
        )

        final_campaign = monitor_result["campaign"]
        final_antiban = monitor_result["anti_ban"]
        failed_recipients = await client.get_recipients(campaign_id, status="failed")
        failed_rows = failed_recipients.get("data", [])

        status = final_campaign.get("status")
        failed_count = int(final_campaign.get("failed_count", 0))
        health_risk = ((final_antiban or {}).get("health") or {}).get("risk")

        if status == "completed" and failed_count == 0 and health_risk not in {"high", "critical"}:
            exit_code = 0
        elif status == "paused" and args.allow_paused_complete:
            exit_code = 2
        else:
            exit_code = 1

        return StageResult(
            campaign_id=campaign_id,
            campaign_name=campaign["name"],
            final_campaign=final_campaign,
            final_antiban=final_antiban,
            failed_rows=failed_rows,
            exit_code=exit_code,
        )
    except KeyboardInterrupt:
        print("Interrupted by user")
        if args.cleanup and campaign_id is not None:
            try:
                await cleanup_campaign(client, campaign_id)
                print(f"Cleanup: deleted campaign {campaign_id}")
            except Exception as exc:  # pragma: no cover - best effort cleanup
                print(f"Cleanup failed: {exc}")
        raise


async def run() -> int:
    args = parse_args()
    recipients = load_recipients(args)
    ramp_sizes = parse_ramp_sizes(args.ramp_sizes)
    client = StressTestClient(args.base_url)

    try:
        device, anti_ban = await preflight(client, args.device_id)
        print_preflight(device, anti_ban)

        if args.reset_antiban:
            reset_result = await client.reset_antiban(args.device_id)
            print(f"Anti-ban reset: {reset_result}")
            print()

        if ramp_sizes:
            if len(recipients) < ramp_sizes[-1]:
                raise StressTestError(
                    f"Ramp requires at least {ramp_sizes[-1]} unique recipients, but only {len(recipients)} were provided"
                )

            stage_results: list[StageResult] = []
            for index, stage_size in enumerate(ramp_sizes, start=1):
                if index > 1 and args.reset_between_stages:
                    reset_result = await client.reset_antiban(args.device_id)
                    print(f"Anti-ban reset before stage {index}: {reset_result}")
                    print()

                print(f"=== Ramp stage {index}/{len(ramp_sizes)}: first {stage_size} recipients ===")
                stage_result = await run_stage(
                    client,
                    args,
                    recipients[:stage_size],
                    stage_label=f"stage-{index}-{stage_size}",
                )
                print_summary(stage_result)

                if args.cleanup:
                    await cleanup_campaign(client, stage_result.campaign_id)
                    print(f"  Cleanup:       deleted campaign {stage_result.campaign_id}")

                stage_results.append(stage_result)
                print()

                if stage_result.exit_code == 1:
                    print(f"Ramp stopped at stage {index}")
                    print("Result: FAIL")
                    return 1

            if any(result.exit_code == 2 for result in stage_results):
                print("Result: PAUSED")
                return 2

            print("Result: PASS")
            return 0

        result = await run_stage(client, args, recipients)
        print_summary(result)

        if args.cleanup:
            await cleanup_campaign(client, result.campaign_id)
            print(f"  Cleanup:       deleted campaign {result.campaign_id}")

        print()
        if result.exit_code == 0:
            print("Result: PASS")
        elif result.exit_code == 2:
            print("Result: PAUSED")
        else:
            print("Result: FAIL")
        return result.exit_code
    except KeyboardInterrupt:
        return 130
    finally:
        await client.close()


def main() -> None:
    try:
        exit_code = asyncio.run(run())
    except StressTestError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()