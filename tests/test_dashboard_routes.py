import asyncio
import unittest

from fastapi import HTTPException
from fastapi.routing import APIRoute
from fastapi.security import HTTPBasicCredentials
from starlette.requests import Request

from app.config.settings import settings
from app.routes.admin_prompt import router as admin_prompt_router
from app.routes.admin_auth import require_admin_access
from app.routes.dashboard import dashboard_page
from app.routes.dashboard import router as dashboard_router


class DashboardRouteTests(unittest.TestCase):
    def setUp(self):
        self.original_username = settings.admin_prompt_username
        self.original_password = settings.admin_prompt_password
        object.__setattr__(settings, "admin_prompt_username", "admin")
        object.__setattr__(settings, "admin_prompt_password", "salainen")

    def tearDown(self):
        object.__setattr__(settings, "admin_prompt_username", self.original_username)
        object.__setattr__(settings, "admin_prompt_password", self.original_password)

    def test_shared_admin_credentials_are_valid_for_dashboard_and_prompt(self):
        credentials = HTTPBasicCredentials(
            username=settings.admin_prompt_username,
            password=settings.admin_prompt_password,
        )

        authenticated_user = require_admin_access(credentials)
        self.assertEqual(authenticated_user, settings.admin_prompt_username)

        protected_routes = {
            route.path: route
            for route in [*dashboard_router.routes, *admin_prompt_router.routes]
            if isinstance(route, APIRoute)
        }
        for path in ("/dashboard", "/api/dashboard", "/admin/prompt"):
            dependency_calls = [
                dependency.call
                for dependency in protected_routes[path].dependant.dependencies
            ]
            self.assertIn(require_admin_access, dependency_calls)

    def test_dashboard_rejects_missing_credentials(self):
        with self.assertRaises(HTTPException) as context:
            require_admin_access(None)

        self.assertEqual(context.exception.status_code, 401)
        self.assertEqual(context.exception.headers["WWW-Authenticate"], "Basic")

    def test_dashboard_page_uses_finnish_copy(self):
        response = asyncio.run(
            dashboard_page(
                request=self._build_request("/dashboard"),
                admin_user=settings.admin_prompt_username,
            )
        )
        body = response.body.decode("utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Puhelukoonti", body)
        self.assertIn("7 päivän kehitys", body)
        self.assertIn("suomenkieliseen koontinäkymään", body)
        self.assertNotIn("Puheludashboard", body)

    @staticmethod
    def _build_request(path: str) -> Request:
        return Request(
            {
                "type": "http",
                "http_version": "1.1",
                "method": "GET",
                "scheme": "https",
                "path": path,
                "raw_path": path.encode("utf-8"),
                "root_path": "",
                "query_string": b"",
                "headers": [],
                "client": ("127.0.0.1", 12345),
                "server": ("localhost", 443),
            }
        )


if __name__ == "__main__":
    unittest.main()
