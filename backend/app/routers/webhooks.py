from fastapi import APIRouter, Request, Response
from app.models import DeliveryMissedCallRequest
from app.services.ai_service import AiService
from app.services.delivery_workflow_service import DeliveryWorkflowService
from app.services.cake_workflow_service import CakeWorkflowService

router = APIRouter(prefix="/api/webhooks", tags=["Telephony & Missed Call Webhooks"])

@router.post("/delivery/missed-call")
def start_delivery_callback(data: DeliveryMissedCallRequest):
    """Create the missed-call callback task and initialise the delivery state."""
    result = DeliveryWorkflowService.start_missed_call(
        caller_name=data.caller_name or "Mobile Caller",
        caller_phone=data.caller_phone,
        language=data.language or "auto",
    )
    return {"success": True, "data": result}

@router.post("/cake/missed-call")
def start_cake_callback(data: DeliveryMissedCallRequest):
    """Create the missed-call callback task and initialise the cake shop state."""
    result = CakeWorkflowService.start_missed_call(
        caller_name=data.caller_name or "Customer",
        caller_phone=data.caller_phone,
        language=data.language or "auto",
    )
    return {"success": True, "data": result}

@router.post("/missed-call")
async def handle_missed_call_webhook(request: Request):
    """
    Webhook handler for real telephony providers (Twilio, Exotel, Plivo).
    Triggers when a customer places a missed call from a real mobile phone.
    """
    form_data = await request.form()
    caller_phone = form_data.get("From") or form_data.get("Caller") or "+91 98765 12345"
    caller_name = form_data.get("CallerName") or "Mobile Caller"
    workflow_id = form_data.get("workflow_id") or form_data.get("WorkflowId")
    business_id = form_data.get("business_id") or form_data.get("BusinessId")
    
    print(f"[Telephony Webhook] Real phone missed call received from: {caller_phone}")

    if workflow_id == DeliveryWorkflowService.WORKFLOW_ID or business_id == DeliveryWorkflowService.BUSINESS_ID:
        res = DeliveryWorkflowService.start_missed_call(caller_name, caller_phone)
    elif workflow_id == CakeWorkflowService.WORKFLOW_ID or business_id == CakeWorkflowService.BUSINESS_ID or not workflow_id:
        res = CakeWorkflowService.start_missed_call(caller_name, caller_phone)
    else:
        res = AiService.process_conversation({
            "business_id": business_id or "biz-cake-01",
            "workflow_id": workflow_id or "wf-cake-01",
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
