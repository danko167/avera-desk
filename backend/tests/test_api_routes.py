import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import httpx
from fastapi import HTTPException

from app.api.main import app
from app.api.routers import local_auth as local_auth_router
from app.api.routers import oauth as oauth_router
from app.api.routers.root import health
from app.api.routers.settings import _check_llm_connection, _normalize_base_url


class ApiRoutesTests(unittest.TestCase):
    def test_health_payload_shape(self) -> None:
        payload = health()
        self.assertEqual(payload.get("status"), "ok")
        self.assertEqual(payload.get("service"), "avera-backend")
        self.assertIsInstance(payload.get("timestamp"), str)

    def test_critical_routes_registered(self) -> None:
        paths = {route.path for route in app.routes}
        expected = {
            "/health",
            "/ws",
            "/api/settings",
            "/api/settings/test-ai-connection",
            "/api/settings/llm-usage-summary",
            "/api/oauth/status",
            "/api/emails/sync",
            "/api/followups/{follow_up_id}",
            "/api/email-drafts/{draft_id}",
            "/api/calendar/events/upcoming",
            "/api/calendar/availability",
            "/api/calendar-proposals/plan",
            "/api/calendar-proposals/{proposal_id}",
        }
        self.assertTrue(expected.issubset(paths))


class SettingsRouteTests(unittest.IsolatedAsyncioTestCase):
    def test_normalize_base_url_allows_public_https_for_external_provider(self) -> None:
        normalized = _normalize_base_url("https://api.openai.com/v1", provider="openai")
        self.assertEqual(normalized, "https://api.openai.com/v1")

    def test_normalize_base_url_rejects_public_http_for_external_provider(self) -> None:
        with self.assertRaisesRegex(ValueError, "https://"):
            _normalize_base_url("http://api.openai.com/v1", provider="openai")

    def test_normalize_base_url_rejects_public_host_for_local_provider_without_override(self) -> None:
        with patch("app.api.routers.settings.os.getenv", return_value=""):
            with self.assertRaisesRegex(ValueError, "loopback/private"):
                _normalize_base_url("https://example.com/v1", provider="local")

    async def test_check_llm_connection_succeeds_for_responses_payload(self) -> None:
        payload = SimpleNamespace(
            provider="openai",
            model="gpt-5.4-mini",
            base_url="https://example.com",
            api_key="test-key",
        )
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "output": [
                {
                    "content": [
                        {"type": "output_text", "text": "ok"},
                    ]
                }
            ]
        }

        client = AsyncMock()
        client.post.return_value = response
        client.__aenter__.return_value = client
        client.__aexit__.return_value = False

        with patch("app.api.routers.settings.httpx.AsyncClient", return_value=client):
            result = await _check_llm_connection(payload)

        self.assertTrue(result.ok)
        self.assertEqual(result.endpoint, "/responses")

    async def test_check_llm_connection_falls_back_to_chat_completions(self) -> None:
        payload = SimpleNamespace(
            provider="openai",
            model="gpt-5.4-mini",
            base_url="https://example.com",
            api_key="test-key",
        )
        responses_fail = Mock()
        responses_fail.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Bad request",
            request=httpx.Request("POST", "https://example.com/responses"),
            response=httpx.Response(status_code=400, request=httpx.Request("POST", "https://example.com/responses")),
        )
        chat_ok = Mock()
        chat_ok.raise_for_status.return_value = None
        chat_ok.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "ok",
                    }
                }
            ]
        }

        client = AsyncMock()
        client.post.side_effect = [responses_fail, chat_ok]
        client.__aenter__.return_value = client
        client.__aexit__.return_value = False

        with patch("app.api.routers.settings.httpx.AsyncClient", return_value=client):
            result = await _check_llm_connection(payload)

        self.assertTrue(result.ok)
        self.assertEqual(result.endpoint, "/chat/completions")

    async def test_check_llm_connection_invalid_responses_payload_returns_http_error(self) -> None:
        payload = SimpleNamespace(
            provider="openai",
            model="gpt-5.4-mini",
            base_url="https://example.com",
            api_key="test-key",
        )
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"output": []}

        client = AsyncMock()
        client.post.return_value = response
        client.__aenter__.return_value = client
        client.__aexit__.return_value = False

        with patch("app.api.routers.settings.httpx.AsyncClient", return_value=client):
            with self.assertRaises(HTTPException) as raised:
                await _check_llm_connection(payload)

        self.assertEqual(raised.exception.status_code, 502)
        self.assertIn("invalid response", str(raised.exception.detail).lower())


class OAuthRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_handle_oauth_callback_uses_route_provider_not_settings_provider(self) -> None:
        oauth = AsyncMock()
        oauth.exchange_auth_response.return_value = {"access_token": "token"}
        db = AsyncMock()
        db_context = AsyncMock()
        db_context.__aenter__.return_value = db
        db_context.__aexit__.return_value = False

        with (
            patch("app.api.routers.oauth.db_session", return_value=db_context),
            patch("app.api.routers.oauth.get_oauth_module", return_value=oauth) as get_oauth_module_mock,
        ):
            response = await oauth_router._handle_oauth_callback(
                {"code": "abc", "state": "state-1"},
                email_provider="gmail",
                provider_label="Gmail",
            )

        get_oauth_module_mock.assert_called_once_with("gmail")
        oauth.exchange_auth_response.assert_awaited_once_with({"code": "abc", "state": "state-1"}, db)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Gmail connected", response.body.decode("utf-8"))


class LocalAuthRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_auth_token_rejects_non_loopback(self) -> None:
        request = SimpleNamespace(
            client=SimpleNamespace(host="192.168.1.22"),
            headers={},
        )

        with self.assertRaises(HTTPException) as ctx:
            await local_auth_router.get_local_auth_session_token(request)

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("loopback", str(ctx.exception.detail).lower())

    async def test_local_auth_token_rejects_disallowed_origin(self) -> None:
        request = SimpleNamespace(
            client=SimpleNamespace(host="127.0.0.1"),
            headers={"origin": "https://example.com"},
        )

        with self.assertRaises(HTTPException) as ctx:
            await local_auth_router.get_local_auth_session_token(request)

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("origin", str(ctx.exception.detail).lower())

    async def test_local_auth_token_accepts_loopback_with_allowed_origin(self) -> None:
        request = SimpleNamespace(
            client=SimpleNamespace(host="127.0.0.1"),
            headers={"origin": "http://localhost:1420"},
        )

        payload = await local_auth_router.get_local_auth_session_token(request)

        self.assertIsInstance(payload.get("token"), str)
        self.assertTrue(len(payload.get("token", "")) > 0)

    async def test_local_auth_token_rejects_loopback_via_forwarded_for_by_default(self) -> None:
        request = SimpleNamespace(
            client=SimpleNamespace(host="10.0.0.8"),
            headers={"x-forwarded-for": "127.0.0.1, 10.0.0.8"},
        )

        with self.assertRaises(HTTPException) as ctx:
            await local_auth_router.get_local_auth_session_token(request)

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("loopback", str(ctx.exception.detail).lower())

    async def test_local_auth_token_accepts_loopback_via_forwarded_for_when_trusted_proxy_enabled(self) -> None:
        request = SimpleNamespace(
            client=SimpleNamespace(host="10.0.0.8"),
            headers={"x-forwarded-for": "127.0.0.1, 10.0.0.8"},
        )

        with patch("app.api.routers.local_auth.should_trust_forwarded_headers", return_value=True):
            payload = await local_auth_router.get_local_auth_session_token(request)

        self.assertIsInstance(payload.get("token"), str)
        self.assertTrue(len(payload.get("token", "")) > 0)

    async def test_local_auth_ws_ticket_rejects_non_loopback(self) -> None:
        request = SimpleNamespace(
            client=SimpleNamespace(host="192.168.1.22"),
            headers={},
        )

        with self.assertRaises(HTTPException) as ctx:
            await local_auth_router.issue_local_auth_ws_ticket(request)

        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("loopback", str(ctx.exception.detail).lower())

    async def test_local_auth_ws_ticket_accepts_loopback_with_allowed_origin(self) -> None:
        request = SimpleNamespace(
            client=SimpleNamespace(host="127.0.0.1"),
            headers={"origin": "http://localhost:1420"},
        )

        payload = await local_auth_router.issue_local_auth_ws_ticket(request)

        self.assertIsInstance(payload.get("ticket"), str)
        self.assertTrue(len(payload.get("ticket", "")) > 0)
        self.assertEqual(payload.get("expires_in_seconds"), 45)


if __name__ == "__main__":
    unittest.main()
