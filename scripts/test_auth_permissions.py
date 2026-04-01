"""Regression checks for auth permission routing and role coverage."""

from __future__ import annotations

import os
import sys


project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from orchestrator.auth.service import ROLE_DEFINITIONS, build_app_user, has_permission
from orchestrator.main import _required_permission_for_request


def make_user(*roles: str) -> dict:
    return build_app_user(
        {
            "dms_user_id": 1,
            "user_name": "Permission Test",
            "user_email": "permission-test@example.com",
            "user_level": "tester",
        },
        list(roles),
    )


def assert_equal(actual, expected, message: str) -> None:
    if actual != expected:
        raise AssertionError(f"{message}: expected {expected!r}, got {actual!r}")


def assert_true(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def assert_false(value: bool, message: str) -> None:
    if value:
        raise AssertionError(message)


def test_role_definitions() -> None:
    operator_permissions = set(ROLE_DEFINITIONS["operator"]["permissions"])
    viewer_permissions = set(ROLE_DEFINITIONS["viewer"]["permissions"])

    required_operator_permissions = {
        "pipeline.view",
        "pipeline.manage",
        "pipeline.run",
        "whatsapp.view",
        "whatsapp.manage",
        "blast.view",
        "blast.manage",
    }
    required_viewer_permissions = {
        "pipeline.view",
        "whatsapp.view",
        "blast.view",
    }
    forbidden_viewer_permissions = {
        "pipeline.manage",
        "pipeline.run",
        "whatsapp.manage",
        "blast.manage",
        "settings.manage",
    }

    for permission in required_operator_permissions:
        assert_true(permission in operator_permissions, f"operator missing permission {permission}")

    for permission in required_viewer_permissions:
        assert_true(permission in viewer_permissions, f"viewer missing permission {permission}")

    for permission in forbidden_viewer_permissions:
        assert_false(permission in viewer_permissions, f"viewer should not have permission {permission}")


def test_route_permissions() -> None:
    viewer = make_user("viewer")
    operator = make_user("operator")
    admin = make_user("admin")

    cases = [
        ("GET", "/control/status", "pipeline.view", True, True),
        ("POST", "/control/pause", "pipeline.manage", False, True),
        ("POST", "/control/chatbot/email", "settings.manage", False, False),
        ("GET", "/wa/status", "whatsapp.view", True, True),
        ("POST", "/wa/restart", "whatsapp.manage", False, True),
        ("POST", "/conversations/test", "whatsapp.manage", False, True),
        ("GET", "/pipeline/status", "pipeline.view", True, True),
        ("GET", "/pipeline/logs", "pipeline.view", True, True),
        ("POST", "/pipeline/find-ig-handles", "pipeline.manage", False, True),
        ("POST", "/pipeline/run-agent-targeted", "pipeline.run", False, True),
        ("POST", "/outreach/run", "pipeline.run", False, True),
        ("GET", "/blast/campaigns", "blast.view", True, True),
        ("POST", "/blast/campaigns", "blast.manage", False, True),
        ("GET", "/email-blast/campaigns", "blast.view", True, True),
        ("POST", "/email-blast/campaigns", "blast.manage", False, True),
        ("GET", "/universities/with-emails", "blast.manage", False, True),
        ("GET", "/api-logs", "settings.manage", False, False),
    ]

    for method, path, expected_permission, viewer_allowed, operator_allowed in cases:
        actual_permission = _required_permission_for_request(method, path)
        assert_equal(actual_permission, expected_permission, f"permission mismatch for {method} {path}")
        assert_equal(
            has_permission(viewer, expected_permission),
            viewer_allowed,
            f"viewer access mismatch for {method} {path}",
        )
        assert_equal(
            has_permission(operator, expected_permission),
            operator_allowed,
            f"operator access mismatch for {method} {path}",
        )
        assert_true(has_permission(admin, expected_permission), f"admin should be allowed for {method} {path}")


def main() -> None:
    test_role_definitions()
    test_route_permissions()
    print("All auth permission regression checks passed.")


if __name__ == "__main__":
    main()