"""Regression checks for auth role upgrade request workflow."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from types import SimpleNamespace
from typing import Any


project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from orchestrator import db as db_module, main


def make_request(user: dict[str, Any]) -> Any:
    return SimpleNamespace(
        state=SimpleNamespace(current_user=user),
        client=SimpleNamespace(host="127.0.0.1"),
        headers={"user-agent": "role-request-test"},
    )


def make_user(dms_user_id: int, email: str, name: str, roles: list[str]) -> dict[str, Any]:
    return {
        "dms_user_id": dms_user_id,
        "email": email,
        "name": name,
        "roles": roles,
        "permissions": ["*"] if "admin" in roles else [],
    }


def assert_equal(actual: Any, expected: Any, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


async def test_role_request_approval() -> None:
    viewer = make_user(1001, "viewer1@example.com", "Viewer One", ["viewer"])
    admin = make_user(2001, "admin@example.com", "Admin User", ["admin"])

    create_result = await main.auth_role_requests_create(
        main.AuthRoleUpgradeRequestPayload(role_key="operator", request_note="Need to run outreach actions"),
        make_request(viewer),
    )
    assert_equal(create_result["status"], "ok", "create role request status")
    request_id = int(create_result["request"]["id"])

    my_requests = await main.auth_role_requests_me(make_request(viewer), limit=10)
    assert_true(len(my_requests["requests"]) == 1, "viewer should see created request")
    assert_true("operator" in my_requests["available_roles"], "viewer should be able to request operator")

    approve_result = await main.auth_role_requests_approve(
        request_id,
        main.AuthRoleUpgradeDecisionPayload(review_note="Approved for broader execution"),
        make_request(admin),
    )
    assert_equal(approve_result["status"], "ok", "approve role request status")

    approved_request = await db_module.get_auth_role_upgrade_request(request_id)
    assert_equal(approved_request["status"], "approved", "request status after approval")
    assert_equal(approved_request["reviewed_by_email"], admin["email"], "approver email")

    granted_assignment = await db_module.get_active_auth_role_assignment(viewer["dms_user_id"], "operator")
    assert_true(granted_assignment is not None, "approved request should grant operator role")


async def test_role_request_rejection_and_duplicate_guard() -> None:
    viewer = make_user(1002, "viewer2@example.com", "Viewer Two", ["viewer"])
    admin = make_user(2001, "admin@example.com", "Admin User", ["admin"])

    create_result = await main.auth_role_requests_create(
        main.AuthRoleUpgradeRequestPayload(role_key="admin", request_note="Need approval for admin tasks"),
        make_request(viewer),
    )
    request_id = int(create_result["request"]["id"])

    duplicate_response = await main.auth_role_requests_create(
        main.AuthRoleUpgradeRequestPayload(role_key="operator", request_note="Second request should fail"),
        make_request(viewer),
    )
    assert_equal(getattr(duplicate_response, "status_code", None), 409, "duplicate pending request should be blocked")

    reject_result = await main.auth_role_requests_reject(
        request_id,
        main.AuthRoleUpgradeDecisionPayload(review_note="Rejected for now"),
        make_request(admin),
    )
    assert_equal(reject_result["status"], "ok", "reject role request status")

    rejected_request = await db_module.get_auth_role_upgrade_request(request_id)
    assert_equal(rejected_request["status"], "rejected", "request status after rejection")

    rejected_assignment = await db_module.get_active_auth_role_assignment(viewer["dms_user_id"], "admin")
    assert_true(rejected_assignment is None, "rejected request should not grant role")


async def main_async() -> None:
    with tempfile.TemporaryDirectory(prefix="auth-role-requests-") as tmp_dir:
        db_path = os.path.join(tmp_dir, "test.db")
        original_db_path = db_module.DATABASE_PATH
        db_module.DATABASE_PATH = db_path
        try:
            await db_module.init_db()
            await test_role_request_approval()
            await test_role_request_rejection_and_duplicate_guard()
        finally:
            db_module.DATABASE_PATH = original_db_path


def main_cli() -> None:
    asyncio.run(main_async())
    print("Auth role request regression checks passed.")


if __name__ == "__main__":
    main_cli()