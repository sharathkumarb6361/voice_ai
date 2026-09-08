from fastapi import APIRouter, HTTPException, Query
import json
from typing import Optional
from sqlalchemy import text
from app.database import get_db_connection
from app.models import RecordStatusUpdate
from app.services.summary_service import SummaryService

router = APIRouter(prefix="/api/records", tags=["Records"])

@router.get("")
def list_records(business_id: Optional[str] = Query(None), status: Optional[str] = Query(None), urgency: Optional[str] = Query(None)):
    query = """
        SELECT r.*, b.name as business_name, w.name as workflow_name
        FROM records r
        JOIN businesses b ON r.business_id = b.id
        JOIN workflows w ON r.workflow_id = w.id
        WHERE 1=1
    """
    params = {}

    if business_id:
        query += " AND r.business_id = :bid"
        params["bid"] = business_id
    if status:
        query += " AND r.followup_status = :status"
        params["status"] = status
    if urgency:
        query += " AND r.urgency = :urgency"
        params["urgency"] = urgency

    query += " ORDER BY r.created_at DESC"

    with get_db_connection() as conn:
        result = conn.execute(text(query), params)
        rows = result.fetchall()

    formatted = []
    for r in rows:
        d = dict(r._mapping)
        raw_cd = d.get("collected_data")
        parsed_cd = json.loads(raw_cd or "{}") if isinstance(raw_cd, str) else (raw_cd or {})
        d["collected_data"] = parsed_cd
        d["transcript"] = json.loads(d["transcript"] or "[]")
        d["tools_executed"] = json.loads(d["tools_executed"] or "[]")

        # Upgrade legacy/terse summaries on the fly
        curr_sum = d.get("ai_summary") or ""
        if not curr_sum or "Delivery missed-call workflow" in curr_sum or "Fields: [" in curr_sum or "Status: Collecting Fields" in curr_sum:
            d["ai_summary"] = SummaryService.generate_clear_summary({
                "caller_name": d.get("caller_name"),
                "caller_phone": d.get("caller_phone"),
                "business_id": d.get("business_id"),
                "intent": d.get("intent"),
                "followup_status": d.get("followup_status"),
                "urgency": d.get("urgency"),
                "collected_data": parsed_cd
            })

        formatted.append(d)

    return {"success": True, "data": formatted}

@router.patch("/{record_id}/status")
def update_status(record_id: str, data: RecordStatusUpdate):
    if data.status not in ["Pending", "Contacted", "Completed", "Closed"]:
        raise HTTPException(status_code=400, detail="Invalid status. Must be Pending, Contacted, Completed, or Closed.")

    with get_db_connection() as conn:
        conn.execute(text("UPDATE records SET followup_status = :status WHERE id = :id"), {"status": data.status, "id": record_id})
        conn.commit()

        result = conn.execute(text("SELECT * FROM records WHERE id = :id"), {"id": record_id}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Record not found")

    d = dict(result._mapping)
    d["collected_data"] = json.loads(d["collected_data"] or "{}")
    d["transcript"] = json.loads(d["transcript"] or "[]")
    d["tools_executed"] = json.loads(d["tools_executed"] or "[]")
    return {"success": True, "data": d}

@router.delete("")
def delete_all_records(business_id: Optional[str] = Query(None)):
    with get_db_connection() as conn:
        if business_id:
            conn.execute(text("DELETE FROM records WHERE business_id = :bid"), {"bid": business_id})
        else:
            conn.execute(text("DELETE FROM records"))
        conn.commit()
    return {"success": True, "message": "All call records deleted successfully."}

@router.delete("/{record_id}")
def delete_record(record_id: str):
    with get_db_connection() as conn:
        existing = conn.execute(text("SELECT id FROM records WHERE id = :id"), {"id": record_id}).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail=f"Record '{record_id}' not found.")
        conn.execute(text("DELETE FROM records WHERE id = :id"), {"id": record_id})
        conn.commit()

    return {"success": True, "message": f"Call record '{record_id}' deleted successfully."}

@router.post("/{record_id}/regenerate-summary")
def regenerate_summary(record_id: str):
    with get_db_connection() as conn:
        result = conn.execute(text("SELECT * FROM records WHERE id = :id"), {"id": record_id}).fetchone()
        if not result:
            raise HTTPException(status_code=404, detail=f"Record '{record_id}' not found.")

        d = dict(result._mapping)
        raw_cd = d.get("collected_data")
        parsed_cd = json.loads(raw_cd or "{}") if isinstance(raw_cd, str) else (raw_cd or {})

        new_summary = SummaryService.generate_clear_summary({
            "caller_name": d.get("caller_name"),
            "caller_phone": d.get("caller_phone"),
            "business_id": d.get("business_id"),
            "intent": d.get("intent"),
            "followup_status": d.get("followup_status"),
            "urgency": d.get("urgency"),
            "collected_data": parsed_cd
        })

        conn.execute(text("UPDATE records SET ai_summary = :sum WHERE id = :id"), {"sum": new_summary, "id": record_id})
        conn.commit()

    return {"success": True, "ai_summary": new_summary, "record_id": record_id}
