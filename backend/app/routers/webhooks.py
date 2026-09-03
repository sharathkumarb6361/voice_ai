from fastapi import APIRouter, Request, Response
from app.services.ai_service import AiService

router = APIRouter(prefix="/api/webhooks", tags=["Telephony & Missed Call Webhooks"])

@router.post("/missed-call")
async def handle_missed_call_webhook(request: Request):
    """
    Webhook handler for real telephony providers (Twilio, Exotel, Plivo).
    Triggers when a customer places a missed call from a real mobile phone.
    """
    form_data = await request.form()
    caller_phone = form_data.get("From") or form_data.get("Caller") or "+91 98765 12345"
    caller_name = form_data.get("CallerName") or "Mobile Caller"
    
    print(f"[Telephony Webhook] Real phone missed call received from: {caller_phone}")

    # Process initial turn callback
    res = AiService.process_conversation({
        "business_id": "biz-cake-01",
        "workflow_id": "wf-cake-01",
        "caller_name": caller_name,
        "caller_phone": caller_phone,
        "language": "auto",
        "messages": [{"role": "user", "content": "I missed a call from this number."}]
    })

    # Return TwiML XML response for Twilio voice playback
    twiml_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Aditi">{res['assistant_reply']}</Say>
</Response>"""
    return Response(content=twiml_xml, media_type="application/xml")

@router.post("/twilio-voice")
async def handle_twilio_voice(request: Request):
    twiml_xml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="Polly.Aditi">Hello! Thank you for calling our Voice AI Assistant. Your call has been registered.</Say>
</Response>"""
    return Response(content=twiml_xml, media_type="application/xml")
