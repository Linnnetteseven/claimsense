"""Africa's Talking USSD claim checker (SMS report sent in the background)."""

import logging

from fastapi import APIRouter, BackgroundTasks, Form
from fastapi.responses import PlainTextResponse

from api.deps import claims_repository
from ussd.handler import handle_ussd_session

logger = logging.getLogger("hakiki.ussd")
router = APIRouter(tags=["ussd"])


@router.post("/ussd", response_class=PlainTextResponse)
def ussd_callback(
    background_tasks: BackgroundTasks,
    sessionId: str = Form(...),
    phoneNumber: str = Form(...),
    networkCode: str = Form(default=""),
    serviceCode: str = Form(default=""),
    text: str = Form(default=""),
):
    """
    AT posts form data on every user input; we answer 'CON <msg>' to continue or
    'END <msg>' to close. Registered as the callback URL in the AT dashboard.
    """
    logger.info("USSD session=%s steps=%d", sessionId, len(text.split("*")) if text else 0)
    response = handle_ussd_session(
        session_id=sessionId, phone_number=phoneNumber, text=text, background_tasks=background_tasks,
        lookup=lambda claim_id: claims_repository().get_claim_by_number(claim_id),
    )
    logger.info("USSD response: %r", response[:60])
    return response
