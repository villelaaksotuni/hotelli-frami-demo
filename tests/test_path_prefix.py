import unittest

from app.path_prefix import (
    build_app_path,
    normalize_path_prefix,
    path_has_prefix,
    public_path_prefix_from_base_url,
    strip_path_prefix,
)


class PathPrefixTests(unittest.TestCase):
    def test_normalize_path_prefix(self):
        self.assertEqual(normalize_path_prefix(None), "")
        self.assertEqual(normalize_path_prefix(""), "")
        self.assertEqual(normalize_path_prefix("/"), "")
        self.assertEqual(normalize_path_prefix("demo/app/"), "/demo/app")

    def test_public_path_prefix_from_base_url(self):
        self.assertEqual(
            public_path_prefix_from_base_url(
                "https://demo.example.com/demo/app/"
            ),
            "/demo/app",
        )
        self.assertEqual(
            public_path_prefix_from_base_url("https://voice.example.com"),
            "",
        )

    def test_build_app_path(self):
        self.assertEqual(build_app_path("", "/api/dashboard"), "/api/dashboard")
        self.assertEqual(
            build_app_path("/demo/app", "/api/dashboard"),
            "/demo/app/api/dashboard",
        )

    def test_strip_path_prefix_only_trims_matching_boundary(self):
        path_prefix = "/demo/app"

        self.assertTrue(path_has_prefix("/demo/app", path_prefix))
        self.assertTrue(path_has_prefix("/demo/app/dashboard", path_prefix))
        self.assertFalse(path_has_prefix("/demo/application", path_prefix))

        self.assertEqual(strip_path_prefix("/demo/app", path_prefix), "/")
        self.assertEqual(
            strip_path_prefix("/demo/app/dashboard", path_prefix),
            "/dashboard",
        )
        self.assertEqual(
            strip_path_prefix("/demo/application", path_prefix),
            "/demo/application",
        )


if __name__ == "__main__":
    unittest.main()
