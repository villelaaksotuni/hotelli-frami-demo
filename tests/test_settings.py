import os
import unittest
from unittest.mock import patch

from app.config.settings import Settings, SettingsError


class SettingsTests(unittest.TestCase):
    def test_public_base_url_and_data_dir_defaults(self):
        with patch.dict(
            os.environ,
            {
                "PUBLIC_BASE_URL": "https://voice.example.com/",
                "APP_DATA_DIR": "/data",
            },
            clear=True,
        ):
            settings = Settings.from_env()

        expected_data_dir = Settings._normalize_path("/data")
        self.assertEqual(settings.normalized_public_base_url, "https://voice.example.com")
        self.assertEqual(settings.public_websocket_base_url, "wss://voice.example.com")
        self.assertEqual(settings.public_url_path_prefix, "")
        self.assertEqual(settings.conversation_log_dir, expected_data_dir)
        self.assertEqual(
            settings.prompt_store_path,
            Settings._normalize_path(f"{expected_data_dir}/prompt_store.json"),
        )
        self.assertEqual(
            settings.daily_summary_history_path,
            Settings._normalize_path(f"{expected_data_dir}/daily_summary_history.json"),
        )
        self.assertTrue(settings.daily_summary_auto_send_enabled)
        self.assertEqual(settings.daily_summary_send_time, "08:00")
        self.assertEqual(
            settings.feedback_survey_history_path,
            Settings._normalize_path(f"{expected_data_dir}/feedback_survey_history.json"),
        )

    def test_public_base_url_is_required_without_fallback_alias(self):
        with patch.dict(
            os.environ,
            {
                "PUBLIC_BASE_URL": "",
            },
            clear=True,
        ):
            settings = Settings.from_env()

        self.assertIsNone(settings.normalized_public_base_url)
        with self.assertRaises(SettingsError) as context:
            settings.validate_public_base_url()
        self.assertIn("PUBLIC_BASE_URL", str(context.exception))

    def test_public_base_url_path_prefix_is_extracted(self):
        with patch.dict(
            os.environ,
            {
                "PUBLIC_BASE_URL": "https://demo.example.com/hotelli-frami/",
            },
            clear=True,
        ):
            settings = Settings.from_env()

        self.assertEqual(
            settings.normalized_public_base_url,
            "https://demo.example.com/hotelli-frami",
        )
        self.assertEqual(
            settings.public_websocket_base_url,
            "wss://demo.example.com/hotelli-frami",
        )
        self.assertEqual(
            settings.public_url_path_prefix,
            "/hotelli-frami",
        )

    def test_twilio_ai_disclosure_settings_can_be_overridden(self):
        with patch.dict(
            os.environ,
            {
                "TWILIO_AI_DISCLOSURE_ENABLED": "false",
                "TWILIO_AI_DISCLOSURE_MESSAGE_FI": "Tama puhelu kay AI-avustajalle.",
                "TWILIO_AI_DISCLOSURE_MESSAGE_EN": "This call uses an AI assistant.",
            },
            clear=True,
        ):
            settings = Settings.from_env()

        self.assertFalse(settings.twilio_ai_disclosure_enabled)
        self.assertEqual(
            settings.twilio_ai_disclosure_message_fi,
            "Tama puhelu kay AI-avustajalle.",
        )
        self.assertEqual(
            settings.twilio_ai_disclosure_message_en,
            "This call uses an AI assistant.",
        )

    def test_twilio_preamble_can_be_disabled(self):
        with patch.dict(
            os.environ,
            {
                "TWILIO_PREAMBLE_ENABLED": "false",
            },
            clear=True,
        ):
            settings = Settings.from_env()

        self.assertFalse(settings.twilio_preamble_enabled)

    def test_realtime_defaults_target_realtime_2(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings.from_env()

        self.assertEqual(settings.openai_realtime_model, "gpt-realtime-2")
        self.assertEqual(settings.default_reasoning_effort, "medium")

    def test_azure_realtime_defaults_to_v1_route_for_non_preview_deployments(self):
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_PROVIDER": "azure-openai",
                "AZURE_OPENAI_API_KEY": "test-key",
                "AZURE_OPENAI_ENDPOINT": "https://example-resource.openai.azure.com/",
                "AZURE_OPENAI_REALTIME_DEPLOYMENT": "gpt-realtime",
            },
            clear=True,
        ):
            settings = Settings.from_env()

        self.assertEqual(
            settings.realtime_websocket_url,
            "wss://example-resource.openai.azure.com/openai/v1/realtime?model=gpt-realtime",
        )
        self.assertTrue(settings.has_openai_credentials)

    def test_azure_realtime_uses_preview_route_when_api_version_is_configured(self):
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_PROVIDER": "azure-openai",
                "AZURE_OPENAI_API_KEY": "test-key",
                "AZURE_OPENAI_ENDPOINT": "https://example-resource.openai.azure.com",
                "AZURE_OPENAI_REALTIME_DEPLOYMENT": "my-realtime-preview",
                "AZURE_OPENAI_REALTIME_API_VERSION": "2025-04-01-preview",
            },
            clear=True,
        ):
            settings = Settings.from_env()

        self.assertEqual(
            settings.realtime_websocket_url,
            "wss://example-resource.openai.azure.com/openai/realtime?api-version=2025-04-01-preview&deployment=my-realtime-preview",
        )

    def test_azure_realtime_url_override_is_used_and_normalized(self):
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_PROVIDER": "azure-openai",
                "AZURE_OPENAI_API_KEY": "test-key",
                "AZURE_OPENAI_ENDPOINT": "https://unused.openai.azure.com",
                "AZURE_OPENAI_REALTIME_DEPLOYMENT": "unused-deployment",
                "AZURE_OPENAI_REALTIME_URL": "https://custom.example.com/openai/v1/realtime?model=custom-deployment",
            },
            clear=True,
        ):
            settings = Settings.from_env()

        self.assertEqual(
            settings.realtime_websocket_url,
            "wss://custom.example.com/openai/v1/realtime?model=custom-deployment",
        )

    def test_azure_realtime_url_override_satisfies_provider_validation(self):
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_PROVIDER": "azure-openai",
                "AZURE_OPENAI_API_KEY": "test-key",
                "AZURE_OPENAI_REALTIME_URL": "wss://custom.example.com/openai/v1/realtime?model=custom-deployment",
            },
            clear=True,
        ):
            settings = Settings.from_env()

        settings.validate_openai_provider()

    def test_azure_chat_api_version_defaults_to_reasoning_compatible_preview(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings.from_env()

        self.assertEqual(settings.azure_openai_chat_api_version, "2024-12-01-preview")

    def test_validate_runtime_dependencies_raises_when_python_multipart_missing(self):
        settings = Settings.from_env()

        with patch("app.config.settings.find_spec", return_value=None):
            with self.assertRaises(SettingsError) as context:
                settings.validate_runtime_dependencies()

        self.assertIn("python-multipart", str(context.exception))

    def test_validate_runtime_dependencies_accepts_installed_python_multipart(self):
        settings = Settings.from_env()

        with patch("app.config.settings.find_spec", return_value=object()):
            settings.validate_runtime_dependencies()


if __name__ == "__main__":
    unittest.main()
