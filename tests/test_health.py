import asyncio
import json
import unittest

from starlette.requests import Request

from app.routes.health import healthcheck


def _build_request(
    *,
    path: str,
    raw_path: str,
    root_path: str = "",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": path,
            "raw_path": raw_path.encode("utf-8"),
            "root_path": root_path,
            "query_string": b"",
            "headers": headers or [],
            "client": ("127.0.0.1", 12345),
            "server": ("demo.example.com", 443),
        }
    )


class HealthcheckTests(unittest.TestCase):
    def test_healthcheck_reports_request_context_without_prefix(self):
        request = _build_request(
            path="/healthz",
            raw_path="/healthz",
            headers=[(b"x-forwarded-proto", b"https")],
        )

        response = asyncio.run(healthcheck(request))
        payload = json.loads(response.body)

        self.assertEqual(payload["request_root_path"], "")
        self.assertEqual(payload["request_path"], "/healthz")
        self.assertEqual(payload["request_raw_path"], "/healthz")
        self.assertEqual(payload["request_url_path"], "/healthz")
        self.assertEqual(payload["x_forwarded_proto"], "https")

    def test_healthcheck_reports_request_context_with_prefix(self):
        request = _build_request(
            path="/healthz",
            raw_path="/hotelli-frami/healthz",
            root_path="/hotelli-frami",
            headers=[(b"x-forwarded-host", b"demo.example.com")],
        )

        response = asyncio.run(healthcheck(request))
        payload = json.loads(response.body)

        self.assertEqual(
            payload["request_root_path"],
            "/hotelli-frami",
        )
        self.assertEqual(payload["request_path"], "/healthz")
        self.assertEqual(
            payload["request_raw_path"],
            "/hotelli-frami/healthz",
        )
        self.assertEqual(payload["request_url_path"], "/healthz")
        self.assertEqual(payload["x_forwarded_host"], "demo.example.com")


if __name__ == "__main__":
    unittest.main()
