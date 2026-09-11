import asyncio
import base64
import json
import logging
from typing import List, Optional

import websockets
from fastapi import APIRouter, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.websockets import WebSocketDisconnect
from starlette.websockets import WebSocketState
from twilio.twiml.voice_response import Connect, VoiceResponse

from app.config.settings import SettingsError, settings
from app.models.call import CallConfig
from app.services.call_config import build_call_config_from_payload, build_default_call_config
from app.services.feedback_survey import feedback_survey_service
from app.services.realtime_session import (
    initialize_session,
    request_initial_assistant_response,
)
from app.services.live_broadcast import LIVE_STATUS_IN_PROGRESS, live_broadcast_hub
from app.services.realtime_tools import execute_realtime_tool
from app.services.runtime_state import session_store
from app.services.transcript_service import save_conversation_log
from app.services.twilio_voice import get_incoming_call_greeting

router = APIRouter()
logger = logging.getLogger(__name__)

OPENAI_CONNECT_TIMEOUT_SECONDS = 10
OPENAI_PING_INTERVAL_SECONDS = 20
OPENAI_PING_TIMEOUT_SECONDS = 20
OPENAI_CLOSE_TIMEOUT_SECONDS = 5


@router.api_route("/incoming-call", methods=["GET", "POST"])
async def handle_incoming_call(request: Request):
    try:
        public_base_url = settings.normalized_public_base_url
        public_websocket_base_url = settings.public_websocket_base_url
        if not public_base_url or not public_websocket_base_url:
            raise ValueError("Missing PUBLIC_BASE_URL environment variable.")

        if request.method == "POST":
            webhook_payload = await request.form()
        else:
            webhook_payload = request.query_params

        call_sid = str(webhook_payload.get("CallSid") or "").strip() or None
        from_number = str(webhook_payload.get("From") or "").strip() or None
        to_number = str(webhook_payload.get("To") or "").strip() or None
        if call_sid:
            session_store.get_or_create_session(
                call_sid=call_sid,
                config=build_default_call_config(),
                metadata={
                    "direction": "inbound",
                    "from_number": from_number,
                    "to_number": to_number,
                },
            )

        response = VoiceResponse()
        greeting_text, greeting_language = get_incoming_call_greeting()
        if greeting_text:
            response.say(greeting_text, language=greeting_language)

        connect = Connect()
        connect.stream(url=f"{public_websocket_base_url}/media-stream")
        response.append(connect)

        logger.info(
            "Incoming call handled, connecting to media stream with Twilio greeting language=%s",
            greeting_language,
        )
        return HTMLResponse(content=str(response), media_type="application/xml")

    except Exception as exc:
        logger.error("Error handling incoming call: %s", exc)
        response = VoiceResponse()
        response.say(
            "Sorry, there was a problem connecting your call. Please try again later.",
            language="en-US",
        )
        return HTMLResponse(content=str(response), media_type="application/xml")


@router.post("/start-call")
async def start_call(request: Request):
    """
    Minimal outbound call endpoint.

    Expected JSON:
    {
      "phone_number": "+358...",
      "system_message": "... optional ...",
      "voice": "shimmer",
      "language": "en",
      "temperature": 0.6,
      "reasoning_effort": "medium",
      "metadata": {
        "customer_id": "...",
        "use_case": "hotel-receptionist"
      }
    }
    """
    try:
        settings.validate_twilio()

        body = await request.json()
        phone_number = body.get("phone_number")
        if not phone_number:
            return JSONResponse(
                status_code=400,
                content={"error": "phone_number is required"},
            )

        public_base_url = settings.normalized_public_base_url
        if not public_base_url:
            return JSONResponse(
                status_code=400,
                content={
                    "error": (
                        "Missing PUBLIC_BASE_URL environment variable"
                    )
                },
            )

        call_config = await build_call_config_from_payload(body)

        call = settings.twilio_client.calls.create(
            to=phone_number,
            from_=settings.twilio_phone_number,
            url=f"{public_base_url}/incoming-call",
        )

        session_metadata = {
            "direction": "outbound",
            "to_number": phone_number,
            "from_number": settings.twilio_phone_number,
            "request_payload": body,
        }
        session_store.create_outbound_session(
            call_sid=call.sid,
            config=call_config,
            metadata=session_metadata,
        )

        return JSONResponse(
            content={
                "status": "success",
                "call_sid": call.sid,
                "message": f"Call initiated to {phone_number}",
                "to_number": phone_number,
                "from_number": settings.twilio_phone_number,
                "language": call_config.language,
                "voice": call_config.voice,
            }
        )

    except SettingsError as exc:
        return JSONResponse(status_code=400, content={"error": str(exc)})
    except Exception as exc:
        logger.error("Error starting call: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to start call: {str(exc)}"},
        )


@router.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    logger.info("Client connected to media stream")
    await websocket.accept()

    effective_key = settings.azure_openai_api_key if settings.is_azure_openai else settings.openai_api_key
    if not effective_key:
        logger.error("OpenAI API key not configured")
        await websocket.close(code=1008, reason="OpenAI API key not configured")
        return

    openai_ws = None
    stream_sid = None
    latest_media_timestamp = 0
    last_assistant_item = None
    mark_queue: List[str] = []
    response_start_timestamp_twilio = None
    call_ended = False
    ai_audio_ms_sent = 0
    termination_reason = "unknown"
    handled_tool_call_ids: set[str] = set()

    try:
        openai_ws = await asyncio.wait_for(
            websockets.connect(
                settings.realtime_websocket_url,
                additional_headers=settings.realtime_ws_auth_headers,
                ping_interval=OPENAI_PING_INTERVAL_SECONDS,
                ping_timeout=OPENAI_PING_TIMEOUT_SECONDS,
                close_timeout=OPENAI_CLOSE_TIMEOUT_SECONDS,
                max_size=None,
            ),
            timeout=OPENAI_CONNECT_TIMEOUT_SECONDS,
        )
        logger.info("Connected to OpenAI Realtime API")

        async def send_mark(connection: WebSocket, active_stream_sid: Optional[str]):
            if active_stream_sid and connection.client_state == WebSocketState.CONNECTED:
                await connection.send_json(
                    {
                        "event": "mark",
                        "streamSid": active_stream_sid,
                        "mark": {"name": "responsePart"},
                    }
                )
                mark_queue.append("responsePart")

        async def handle_speech_started_event():
            nonlocal response_start_timestamp_twilio, last_assistant_item, ai_audio_ms_sent

            if not last_assistant_item:
                logger.info("No active assistant item to interrupt")
                return

            if ai_audio_ms_sent <= 0:
                logger.info("No AI audio sent yet, skipping truncate")
                return

            min_ai_speech_ms = 1000
            if ai_audio_ms_sent < min_ai_speech_ms:
                logger.info(
                    "AI audio too short (%sms); letting it continue",
                    ai_audio_ms_sent,
                )
                return

            truncate_buffer_ms = 150
            audio_end_ms = max(0, ai_audio_ms_sent - truncate_buffer_ms)
            if audio_end_ms <= 0:
                return

            if settings.show_timing_math:
                print(f"[DEBUG] truncating at {audio_end_ms}ms")

            try:
                await openai_ws.send(
                    json.dumps(
                        {
                            "type": "conversation.item.truncate",
                            "item_id": last_assistant_item,
                            "content_index": 0,
                            "audio_end_ms": audio_end_ms,
                        }
                    )
                )

                if websocket.client_state == WebSocketState.CONNECTED:
                    await websocket.send_json({"event": "clear", "streamSid": stream_sid})

                mark_queue.clear()
                logger.info(
                    "Truncated assistant audio at %sms (total sent=%sms)",
                    audio_end_ms,
                    ai_audio_ms_sent,
                )

            except Exception as exc:
                logger.warning("Audio truncation failed: %s", exc)
                mark_queue.clear()

            finally:
                last_assistant_item = None
                response_start_timestamp_twilio = None
                ai_audio_ms_sent = 0

        async def receive_from_twilio():
            nonlocal stream_sid, latest_media_timestamp, call_ended
            nonlocal last_assistant_item, response_start_timestamp_twilio, termination_reason

            try:
                async for message in websocket.iter_text():
                    data = json.loads(message)
                    event_type = data.get("event")

                    if event_type == "media":
                        if "timestamp" in data.get("media", {}):
                            latest_media_timestamp = int(data["media"]["timestamp"])

                        await openai_ws.send(
                            json.dumps(
                                {
                                    "type": "input_audio_buffer.append",
                                    "audio": data["media"]["payload"],
                                }
                            )
                        )

                    elif event_type == "start":
                        stream_sid = data["start"]["streamSid"]
                        response_start_timestamp_twilio = None
                        latest_media_timestamp = 0
                        last_assistant_item = None

                        call_sid = data["start"].get("callSid")
                        existing_session = session_store.get_by_call_sid(call_sid)
                        is_new_inbound_session = existing_session is None
                        session = session_store.get_or_create_session(
                            call_sid=call_sid,
                            stream_sid=stream_sid,
                            config=existing_session.config if existing_session else build_default_call_config(),
                            metadata={
                                "direction": "inbound" if is_new_inbound_session else None,
                                "twilio_start_event": data.get("start", {}),
                            },
                        )

                        try:
                            await initialize_session(openai_ws, session.config)
                            await request_initial_assistant_response(
                                openai_ws, session.config
                            )
                        except Exception as exc:
                            error_message = f"Failed to initialize OpenAI session: {exc}"
                            session_store.mark_session_error(
                                call_sid=call_sid,
                                stream_sid=stream_sid,
                                error=error_message,
                            )
                            termination_reason = "openai_session_init_failed"
                            logger.error(
                                "%s stream_sid=%s call_sid=%s",
                                error_message,
                                stream_sid,
                                call_sid,
                            )
                            call_ended = True
                            break

                        live_broadcast_hub.publish_status(LIVE_STATUS_IN_PROGRESS)
                        logger.info(
                            "Published live status state=%s stream_sid=%s",
                            LIVE_STATUS_IN_PROGRESS,
                            stream_sid,
                        )

                        logger.info(
                            "Stream started: stream_sid=%s call_sid=%s",
                            stream_sid,
                            call_sid,
                        )

                    elif event_type == "stop":
                        logger.info("Stream stopped: %s", stream_sid)
                        termination_reason = "twilio_stop"
                        session_store.add_session_metadata(
                            stream_sid=stream_sid,
                            metadata={"twilio_stop_event": data},
                        )
                        call_ended = True
                        break

                    elif event_type == "mark" and mark_queue:
                        mark_queue.pop(0)

            except WebSocketDisconnect:
                logger.info("Twilio websocket disconnected")
                termination_reason = "twilio_disconnect"
                call_ended = True
            except Exception as exc:
                logger.error("Error in receive_from_twilio: %s", exc)
                termination_reason = "twilio_receive_error"
                session_store.mark_session_error(
                    stream_sid=stream_sid,
                    error=f"Twilio receive error: {exc}",
                )
                call_ended = True

        async def send_to_twilio():
            nonlocal call_ended, last_assistant_item
            nonlocal response_start_timestamp_twilio, ai_audio_ms_sent, termination_reason

            try:
                async for openai_message in openai_ws:
                    if call_ended:
                        break

                    response = json.loads(openai_message)
                    response_type = response.get("type")

                    if response_type == "error":
                        logger.error("OpenAI realtime error: %s", response)
                        session_store.add_session_metadata(
                            stream_sid=stream_sid,
                            metadata={"last_openai_error": response},
                        )
                        continue

                    if response_type == "session.created":
                        logger.info("OpenAI session created")

                    if response_type == "session.updated":
                        logger.info("OpenAI session updated")

                    if response_type == "response.output_item.done":
                        item = response.get("item", {})
                        if item.get("type") == "function_call":
                            await handle_realtime_function_call(item)
                            continue

                    if response_type == "response.function_call_arguments.done":
                        await handle_realtime_function_call(
                            {
                                "type": "function_call",
                                "name": response.get("name"),
                                "call_id": response.get("call_id"),
                                "arguments": response.get("arguments"),
                            }
                        )
                        continue

                    if response_type == "conversation.item.input_audio_transcription.completed":
                        transcript_text = response.get("transcript", "").strip()
                        if transcript_text and stream_sid:
                            updated_session = session_store.append_transcript(
                                stream_sid,
                                speaker="user",
                                text=transcript_text,
                            )
                            if updated_session is None:
                                logger.warning(
                                    "Dropped user transcript because no active session exists for stream_sid=%s",
                                    stream_sid,
                                )
                            logger.info("User: %s", transcript_text)

                    if response_type == "response.done":
                        response_start_timestamp_twilio = None
                        ai_audio_ms_sent = 0
                        mark_queue.clear()

                        for item in response.get("response", {}).get("output", []):
                            if item.get("type") != "message":
                                continue

                            last_assistant_item = item.get("id")
                            final_assistant_reply_parts = []
                            for part in item.get("content", []):
                                if part.get("type") in {"audio", "output_audio"} and "transcript" in part:
                                    transcript = part["transcript"]
                                    if transcript and stream_sid:
                                        updated_session = session_store.append_transcript(
                                            stream_sid,
                                            speaker="assistant",
                                            text=transcript,
                                        )
                                        if updated_session is None:
                                            logger.warning(
                                                "Dropped assistant transcript because no active session exists for stream_sid=%s",
                                                stream_sid,
                                            )
                                    if transcript:
                                        final_assistant_reply_parts.append(transcript.strip())
                                    logger.info("Assistant: %s", transcript)

                            final_assistant_reply = " ".join(
                                part for part in final_assistant_reply_parts if part
                            ).strip()
                            if final_assistant_reply:
                                logger.info(
                                    "[assistant-debug] final_assistant_reply=%r stream_sid=%s item_id=%s",
                                    final_assistant_reply,
                                    stream_sid,
                                    last_assistant_item,
                                )

                    if response_type == "response.output_audio.delta" and stream_sid:
                        decoded_bytes = base64.b64decode(response["delta"])
                        audio_payload = base64.b64encode(decoded_bytes).decode("utf-8")

                        if websocket.client_state != WebSocketState.CONNECTED:
                            logger.info("Twilio websocket no longer connected")
                            termination_reason = "twilio_not_connected"
                            break

                        await websocket.send_json(
                            {
                                "event": "media",
                                "streamSid": stream_sid,
                                "media": {"payload": audio_payload},
                            }
                        )

                        if response_start_timestamp_twilio is None:
                            ai_audio_ms_sent = 0
                            response_start_timestamp_twilio = latest_media_timestamp

                        ai_audio_ms_sent += int(len(decoded_bytes) / 8)
                        await send_mark(websocket, stream_sid)

                    if response_type == "response.output_audio.done":
                        logger.info("Assistant finished speaking")
                        if websocket.client_state == WebSocketState.CONNECTED:
                            await websocket.send_json({"event": "ai_response_done"})

                    if response_type == "input_audio_buffer.speech_started":
                        logger.info("User speech detected during assistant turn")
                        if last_assistant_item:
                            await handle_speech_started_event()

            except WebSocketDisconnect:
                logger.info("Websocket disconnected while sending to Twilio")
                termination_reason = "twilio_send_disconnect"
            except Exception as exc:
                logger.error("Error in send_to_twilio: %s", exc)
                termination_reason = "openai_send_error"
                session_store.mark_session_error(
                    stream_sid=stream_sid,
                    error=f"OpenAI/Twilio send error: {exc}",
                )

        async def handle_realtime_function_call(item: dict) -> None:
            tool_name = item.get("name")
            call_id = item.get("call_id")
            arguments = item.get("arguments")
            if not tool_name or not call_id:
                logger.warning("Dropped malformed realtime function call item=%s", item)
                return
            if call_id in handled_tool_call_ids:
                return

            handled_tool_call_ids.add(call_id)
            session = session_store.get_by_stream_sid(stream_sid) if stream_sid else None
            tool_result = await execute_realtime_tool(tool_name, arguments, session=session)
            logger.info(
                "Realtime tool completed name=%s call_id=%s status=%s error_code=%s",
                tool_name,
                call_id,
                tool_result.get("status"),
                tool_result.get("error_code"),
            )
            await openai_ws.send(
                json.dumps(
                    {
                        "type": "conversation.item.create",
                        "item": {
                            "type": "function_call_output",
                            "call_id": call_id,
                            "output": json.dumps(tool_result, ensure_ascii=False),
                        },
                    }
                )
            )
            await openai_ws.send(json.dumps({"type": "response.create"}))

        tasks = [
            asyncio.create_task(receive_from_twilio()),
            asyncio.create_task(send_to_twilio()),
        ]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        for task in done:
            if task.cancelled():
                continue
            exception = task.exception()
            if exception:
                logger.error("Media stream task failed: %s", exception)
                session_store.mark_session_error(
                    stream_sid=stream_sid,
                    error=f"Media stream task failed: {exception}",
                )
                if termination_reason == "unknown":
                    termination_reason = "media_stream_task_failed"

        call_ended = True

        for task in pending:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    except asyncio.TimeoutError as exc:
        termination_reason = "openai_connect_timeout"
        logger.error(
            "Timed out connecting to OpenAI Realtime API url=%s error=%s",
            settings.realtime_websocket_url,
            exc,
        )
        session_store.mark_session_error(
            stream_sid=stream_sid,
            error="Timed out connecting to OpenAI Realtime API",
        )
    except Exception as exc:
        termination_reason = "media_stream_error"
        logger.error(
            "Error in media stream url=%s error=%s",
            settings.realtime_websocket_url,
            exc,
        )
        session_store.mark_session_error(
            stream_sid=stream_sid,
            error=f"Media stream error: {exc}",
        )

    finally:
        logger.info("Cleaning up media stream resources")

        if openai_ws:
            try:
                if hasattr(openai_ws, "closed"):
                    if not openai_ws.closed:
                        await openai_ws.close()
                else:
                    if getattr(openai_ws, "open", False):
                        await openai_ws.close()
            except Exception as exc:
                logger.warning("Error closing OpenAI websocket: %s", exc)

        try:
            if websocket.client_state != WebSocketState.DISCONNECTED:
                await websocket.close()
        except Exception as exc:
            logger.warning("Error closing Twilio websocket: %s", exc)

        session = session_store.finish_session(stream_sid, reason=termination_reason)
        if session:
            dialogue_turns = await save_conversation_log(session)
            feedback_survey_service.send_invite_if_needed(
                metadata=session.metadata,
                call_sid=session.call_sid,
                stream_sid=session.stream_sid,
                language=session.config.language,
                dialogue_turns=dialogue_turns,
            )
            logger.info(
                "Call finished stream_sid=%s call_sid=%s reason=%s duration=%ss",
                session.stream_sid,
                session.call_sid,
                session.termination_reason,
                session.duration_seconds(),
            )
            session_store.remove_session(session)
