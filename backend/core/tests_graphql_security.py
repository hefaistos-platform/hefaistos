from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from graphql import GraphQLError

from core.graphql_security import GraphQLSecurityMiddleware
from identity.decorators import Roles


class _DummyPath:
    def __init__(self, parts=None):
        self._parts = parts or ["field"]

    def as_list(self):
        return self._parts


def _make_info(user, operation_kind: str, field_name: str, path_parts=None):
    request = SimpleNamespace(user=user, META={"REMOTE_ADDR": "127.0.0.1"})
    return SimpleNamespace(
        context=request,
        operation=SimpleNamespace(operation=operation_kind),
        field_name=field_name,
        path=_DummyPath(path_parts),
    )


def _make_user(role: str):
    return SimpleNamespace(
        id="u-1",
        username="bot-user",
        role=role,
        is_anonymous=False,
        is_superuser=False,
        is_staff=False,
    )


class GraphQLSecurityMiddlewareTests(SimpleTestCase):
    def setUp(self):
        self.middleware = GraphQLSecurityMiddleware()

    @patch("core.graphql_security.emit_security_event")
    def test_bot_mutation_is_blocked(self, _mock_emit):
        user = _make_user(Roles.BOT_AUDITOR_ORG)
        info = _make_info(user, "mutation", "deleteUser")

        with self.assertRaises(GraphQLError):
            self.middleware.resolve(lambda *_args, **_kwargs: {"ok": True}, None, info)

    def test_sensitive_field_is_redacted_for_bot(self):
        user = _make_user(Roles.BOT_AUDITOR_ORG)
        info = _make_info(user, "query", "smtpPassword")

        result = self.middleware.resolve(lambda *_args, **_kwargs: "super-secret", None, info)
        self.assertEqual(result, "[REDACTED]")

    def test_camel_case_sensitive_field_is_redacted_for_bot(self):
        user = _make_user(Roles.BOT_AUDITOR_ORG)
        info = _make_info(user, "query", "authKey")

        result = self.middleware.resolve(lambda *_args, **_kwargs: "abcd-1234", None, info)
        self.assertEqual(result, "[REDACTED]")

    def test_non_bot_query_is_untouched(self):
        user = _make_user(Roles.ANALYST)
        info = _make_info(user, "query", "smtpPassword")

        result = self.middleware.resolve(lambda *_args, **_kwargs: "super-secret", None, info)
        self.assertEqual(result, "super-secret")

    def test_org_bot_is_elevated_to_admin_role_for_query_only(self):
        user = _make_user(Roles.BOT_AUDITOR_ORG)
        info = _make_info(user, "query", "smtpSettings")
        observed = {}

        def _next(_root, _info, **_kwargs):
            observed["role"] = user.role
            observed["is_superuser"] = user.is_superuser
            observed["is_staff"] = user.is_staff
            return {"ok": True}

        result = self.middleware.resolve(_next, None, info)
        self.assertEqual(result, {"ok": True})
        self.assertEqual(observed["role"], Roles.ADMIN)
        self.assertFalse(observed["is_superuser"])
        self.assertFalse(observed["is_staff"])
        self.assertEqual(user.role, Roles.BOT_AUDITOR_ORG)

    def test_global_bot_is_elevated_for_query_only(self):
        user = _make_user(Roles.BOT_AUDITOR_GLOBAL)
        info = _make_info(user, "query", "me")
        observed = {}

        def _next(_root, _info, **_kwargs):
            observed["role"] = user.role
            observed["is_superuser"] = user.is_superuser
            observed["is_staff"] = user.is_staff
            return {"ok": True}

        result = self.middleware.resolve(_next, None, info)
        self.assertEqual(result, {"ok": True})
        self.assertEqual(observed["role"], Roles.ADMIN)
        self.assertTrue(observed["is_superuser"])
        self.assertTrue(observed["is_staff"])
        self.assertEqual(user.role, Roles.BOT_AUDITOR_GLOBAL)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_staff)

    def test_nested_query_field_does_not_keep_elevated_identity(self):
        user = _make_user(Roles.BOT_AUDITOR_GLOBAL)
        info = _make_info(user, "query", "role", path_parts=["me", "role"])
        observed = {}

        def _next(_root, _info, **_kwargs):
            observed["role"] = user.role
            observed["is_superuser"] = user.is_superuser
            observed["is_staff"] = user.is_staff
            return user.role

        result = self.middleware.resolve(_next, None, info)
        self.assertEqual(result, Roles.BOT_AUDITOR_GLOBAL)
        self.assertEqual(observed["role"], Roles.BOT_AUDITOR_GLOBAL)
        self.assertFalse(observed["is_superuser"])
        self.assertFalse(observed["is_staff"])
