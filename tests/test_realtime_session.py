import json
import unittest
from dataclasses import replace
from unittest.mock import AsyncMock, patch

from app.models.call import CallConfig
from app.services import realtime_session
from app.services.realtime_session import (
    initialize_session,
    request_initial_assistant_response,
)


class RealtimeSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_initialize_session_sends_realtime_2_session_update_payload(self):
        openai_ws = AsyncMock()
        config = CallConfig(
            system_message="system prompt",
            voice="shimmer",
            language="fi",
            temperature=0.8,
            reasoning_effort="medium",
        )
        test_settings = replace(
            realtime_session.settings,
            openai_realtime_model="gpt-realtime-2",
        )

        with patch.object(realtime_session, "settings", test_settings):
            await initialize_session(openai_ws, config)

        self.assertEqual(openai_ws.send.await_count, 1)
        payload = json.loads(openai_ws.send.await_args.args[0])
        self.assertEqual(payload["type"], "session.update")
        self.assertEqual(payload["session"]["type"], "realtime")
        self.assertEqual(payload["session"]["model"], "gpt-realtime-2")
        self.assertEqual(payload["session"]["instructions"], "system prompt")
        self.assertEqual(payload["session"]["audio"]["input"]["format"]["type"], "audio/pcmu")
        self.assertEqual(payload["session"]["audio"]["output"]["format"]["type"], "audio/pcmu")
        self.assertEqual(payload["session"]["audio"]["output"]["voice"], "shimmer")
        self.assertEqual(payload["session"]["output_modalities"], ["audio"])
        self.assertEqual(
            payload["session"]["audio"]["input"]["transcription"]["language"],
            "fi",
        )
        self.assertNotIn("temperature", payload["session"])
        self.assertEqual(
            payload["session"]["reasoning"],
            {"effort": "medium"},
        )
        self.assertTrue(payload["session"]["audio"]["input"]["turn_detection"]["create_response"])

    async def test_initialize_session_sends_current_shape_for_gpt_realtime(self):
        openai_ws = AsyncMock()
        config = CallConfig(
            system_message="system prompt",
            voice="shimmer",
            language="fi",
            temperature=0.8,
            reasoning_effort="high",
        )
        test_settings = replace(
            realtime_session.settings,
            openai_realtime_model="gpt-realtime",
        )

        with patch.object(realtime_session, "settings", test_settings):
            await initialize_session(openai_ws, config)

        payload = json.loads(openai_ws.send.await_args.args[0])
        self.assertEqual(payload["session"]["model"], "gpt-realtime")
        self.assertEqual(payload["session"]["audio"]["input"]["format"]["type"], "audio/pcmu")
        self.assertEqual(payload["session"]["audio"]["output"]["format"]["type"], "audio/pcmu")
        self.assertEqual(payload["session"]["audio"]["output"]["voice"], "shimmer")
        self.assertEqual(payload["session"]["output_modalities"], ["audio"])
        self.assertEqual(
            payload["session"]["audio"]["input"]["transcription"]["language"],
            "fi",
        )
        self.assertNotIn("temperature", payload["session"])
        self.assertNotIn("reasoning", payload["session"])

    async def test_request_initial_assistant_response_sends_opening_turn_request(self):
        openai_ws = AsyncMock()
        config = CallConfig(
            language="fi",
            opening_message="Aloita lyhyellä tervehdyksellä ja kysy, miten voit auttaa.",
        )

        await request_initial_assistant_response(openai_ws, config)

        self.assertEqual(openai_ws.send.await_count, 1)
        payload = json.loads(openai_ws.send.await_args.args[0])
        self.assertEqual(payload["type"], "response.create")
        self.assertEqual(payload["response"]["output_modalities"], ["audio"])
        self.assertEqual(
            payload["response"]["instructions"],
            "Aloita lyhyellä tervehdyksellä ja kysy, miten voit auttaa.",
        )


if __name__ == "__main__":
    unittest.main()
