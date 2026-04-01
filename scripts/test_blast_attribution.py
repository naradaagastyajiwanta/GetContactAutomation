"""Regression checks for blast attribution metadata on create/start flows."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from types import SimpleNamespace
from typing import Any


project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from orchestrator import blast_service, db as db_module, email_blast, main


def make_request(user: dict[str, Any]) -> Any:
    return SimpleNamespace(state=SimpleNamespace(current_user=user))


def assert_equal(actual: Any, expected: Any, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


async def seed_university(name: str, email: str) -> int:
    async with db_module.get_db() as db:
        cursor = await db.execute(
            "INSERT INTO universities (name, province, email_kampus, enabled) VALUES (?, ?, ?, 1)",
            (name, "DKI Jakarta", email),
        )
        await db.commit()
        return int(cursor.lastrowid)


async def seed_contact(university_id: int, phone_number: str, contact_name: str) -> int:
    async with db_module.get_db() as db:
        cursor = await db.execute(
            "INSERT INTO ig_contacts (university_id, phone_number, contact_name) VALUES (?, ?, ?)",
            (university_id, phone_number, contact_name),
        )
        await db.commit()
        return int(cursor.lastrowid)


async def set_email_recipient_status(campaign_id: int, status: str) -> None:
    async with db_module.get_db() as db:
        await db.execute(
            "UPDATE email_blast_recipients SET status = ?, error_message = ? WHERE campaign_id = ?",
            (status, None if status != "failed" else "smtp timeout", campaign_id),
        )
        await db.commit()


async def test_whatsapp_blast_attribution() -> None:
    creator = {"dms_user_id": 101, "email": "creator@example.com", "name": "Creator User"}
    starter = {"dms_user_id": 202, "email": "starter@example.com", "name": "Starter User"}

    university_id = await seed_university("Universitas Attribution WA", "wa@example.com")
    contact_id = await seed_contact(university_id, "+6281234567890", "Nadia")

    create_result = await main.blast_create_campaign(
        {
            "name": "WA Attribution Campaign",
            "template_message": "Halo {nama_kontak} dari {nama_universitas}",
            "device_id": "device_test",
        },
        make_request(creator),
    )
    campaign_id = int(create_result["campaign"]["id"])

    created_campaign = await blast_service.get_campaign(campaign_id)
    assert_equal(created_campaign["created_by_dms_user_id"], creator["dms_user_id"], "WA campaign creator id")
    assert_equal(created_campaign["created_by_email"], creator["email"], "WA campaign creator email")
    assert_equal(created_campaign["created_by_name"], creator["name"], "WA campaign creator name")

    add_result = await blast_service.add_recipients_from_contacts(campaign_id, [contact_id])
    assert_equal(add_result["added"], 1, "WA recipient add count")

    original_worker = blast_service._blast_worker

    async def fake_blast_worker(_: int) -> None:
        return None

    blast_service._blast_worker = fake_blast_worker
    try:
        start_result = await main.blast_start_campaign(campaign_id, make_request(starter))
        assert_equal(start_result["success"], True, "WA start result")
        await asyncio.sleep(0)
    finally:
        blast_service._blast_worker = original_worker
        task = blast_service._blast_tasks.pop(campaign_id, None)
        if task and not task.done():
            task.cancel()

    started_campaign = await blast_service.get_campaign(campaign_id)
    assert_equal(started_campaign["started_by_dms_user_id"], starter["dms_user_id"], "WA campaign starter id")
    assert_equal(started_campaign["started_by_email"], starter["email"], "WA campaign starter email")
    assert_equal(started_campaign["started_by_name"], starter["name"], "WA campaign starter name")


async def test_email_blast_attribution() -> None:
    creator = {"dms_user_id": 303, "email": "email-creator@example.com", "name": "Email Creator"}
    starter = {"dms_user_id": 404, "email": "email-starter@example.com", "name": "Email Starter"}
    retrier = {"dms_user_id": 505, "email": "email-retry@example.com", "name": "Email Retry"}

    university_id = await seed_university("Universitas Attribution Email", "kampus@example.com")

    create_result = await main.create_email_campaign(
        main.EmailBlastCampaignCreate(
            name="Email Attribution Campaign",
            subject="Halo {{university_name}}",
            template_message="Isi email ke {{university_name}}",
            from_email="sekretariat@example.com",
            from_name="Sekretariat",
            delay_between_ms=1,
        ),
        make_request(creator),
    )
    campaign_id = int(create_result["campaign_id"])

    created_campaign = await email_blast.get_campaign_status(campaign_id)
    assert_equal(created_campaign["created_by_dms_user_id"], creator["dms_user_id"], "Email campaign creator id")
    assert_equal(created_campaign["created_by_email"], creator["email"], "Email campaign creator email")
    assert_equal(created_campaign["created_by_name"], creator["name"], "Email campaign creator name")

    added = await email_blast.add_recipients_to_campaign(campaign_id, [university_id])
    assert_equal(added, 1, "Email recipient add count")

    original_run = email_blast.run_email_blast_campaign
    original_retry = email_blast.retry_failed_email_blast

    async def fake_email_run(_: int, smtp_client: Any = None, max_recipients: int | None = None) -> None:
        return None

    async def fake_email_retry(_: int, max_recipients: int | None = None) -> None:
        return None

    email_blast.run_email_blast_campaign = fake_email_run
    email_blast.retry_failed_email_blast = fake_email_retry
    try:
        start_result = await main.start_email_campaign(
            campaign_id,
            main.EmailBlastStartRequest(max_recipients=1),
            make_request(starter),
        )
        assert_equal(start_result["success"], True, "Email start result")
        await asyncio.sleep(0)

        started_campaign = await email_blast.get_campaign_status(campaign_id)
        assert_equal(started_campaign["started_by_dms_user_id"], starter["dms_user_id"], "Email campaign starter id")
        assert_equal(started_campaign["started_by_email"], starter["email"], "Email campaign starter email")
        assert_equal(started_campaign["started_by_name"], starter["name"], "Email campaign starter name")

        await set_email_recipient_status(campaign_id, "failed")

        retry_result = await main.retry_failed_email_campaign(
            campaign_id,
            main.EmailBlastStartRequest(max_recipients=1),
            make_request(retrier),
        )
        assert_equal(retry_result["success"], True, "Email retry result")
        assert_equal(retry_result["recipients_retried"], 1, "Email retry count")
        await asyncio.sleep(0)
    finally:
        email_blast.run_email_blast_campaign = original_run
        email_blast.retry_failed_email_blast = original_retry

    retried_campaign = await email_blast.get_campaign_status(campaign_id)
    assert_equal(retried_campaign["started_by_dms_user_id"], retrier["dms_user_id"], "Email retry starter id")
    assert_equal(retried_campaign["started_by_email"], retrier["email"], "Email retry starter email")
    assert_equal(retried_campaign["started_by_name"], retrier["name"], "Email retry starter name")


async def main_async() -> None:
    with tempfile.TemporaryDirectory(prefix="blast-attribution-") as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")
        original_db_path = db_module.DATABASE_PATH
        db_module.DATABASE_PATH = db_path
        try:
            await db_module.init_db()
            await test_whatsapp_blast_attribution()
            await test_email_blast_attribution()
        finally:
            db_module.DATABASE_PATH = original_db_path


def main_cli() -> None:
    asyncio.run(main_async())
    print("Blast attribution regression checks passed.")


if __name__ == "__main__":
    main_cli()