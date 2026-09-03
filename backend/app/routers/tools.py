from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from app.services.calendar_service import CalendarService
from app.services.external_api_service import ExternalApiService
from app.models import CalendarEventRequest, CalendarEventUpdate

router = APIRouter(prefix="/api/tools", tags=["Tools & Integrations"])

@router.get("/calendar/events")
def list_calendar_events(
    business_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None)
):
    events = CalendarService.list_events(business_id=business_id, status=status, search=search)
    return {"success": True, "data": events}

@router.post("/calendar/check-availability")
def check_availability(data: dict):
    date_str = data.get("date", "today")
    time_str = data.get("time", "16:00")
    duration = data.get("duration", 30)
    business_id = data.get("business_id")
    res = CalendarService.check_availability(date_str, time_str, duration_minutes=duration, business_id=business_id)
    return {"success": True, "data": res}

@router.post("/calendar/create-event")
@router.post("/calendar/events")
def create_event(data: CalendarEventRequest):
    res = CalendarService.create_event(
        business_id=data.business_id,
        title=data.title,
        start_time=data.start_time,
        end_time=data.end_time,
        attendee_name=data.attendee_name,
        attendee_phone=data.attendee_phone,
        description=data.description
    )
    return {"success": True, "data": res}

@router.put("/calendar/events/{event_id}")
def update_event(event_id: str, data: CalendarEventUpdate):
    res = CalendarService.update_event(
        event_id=event_id,
        title=data.title,
        new_start_time=data.start_time,
        new_end_time=data.end_time,
        attendee_name=data.attendee_name,
        attendee_phone=data.attendee_phone,
        description=data.description,
        status=data.status
    )
    if not res.get("success"):
        raise HTTPException(status_code=4404 if "No active" in res.get("message", "") else 400, detail=res.get("message"))
    return {"success": True, "data": res}

@router.post("/calendar/cancel-event")
def cancel_event_post(data: dict):
    event_id = data.get("event_id", "latest")
    business_id = data.get("business_id")
    res = CalendarService.cancel_event(event_id, business_id)
    return {"success": True, "data": res}

@router.delete("/calendar/events/{event_id}")
def cancel_event_by_id(event_id: str):
    res = CalendarService.cancel_event(event_id)
    return {"success": True, "data": res}

@router.post("/calendar/sync")
def sync_google_calendar():
    res = CalendarService.sync_events()
    return {"success": True, "data": res}

@router.get("/delivery/track/{tracking_number}")
def track_delivery(tracking_number: str):
    res = ExternalApiService.track_delivery_status(tracking_number)
    return {"success": True, "data": res}

@router.get("/crm/customer/{phone}")
def crm_lookup(phone: str):
    res = ExternalApiService.lookup_crm_customer(phone)
    return {"success": True, "data": res}
