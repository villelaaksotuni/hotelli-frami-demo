from fastapi import APIRouter, Request
from fastapi.responses import Response
from twilio.twiml.messaging_response import MessagingResponse

from app.services.feedback_survey import feedback_survey_service

router = APIRouter()


@router.post("/sms/feedback")
async def receive_feedback_sms(request: Request):
    form = await request.form()
    from_phone = str(form.get("From") or "")
    body = str(form.get("Body") or "")
    message_sid = str(form.get("MessageSid") or "")

    result = feedback_survey_service.record_response(
        from_phone=from_phone,
        body=body,
        message_sid=message_sid or None,
    )

    twiml = MessagingResponse()
    twiml.message(result.reply_message)
    return Response(content=str(twiml), media_type="application/xml")
