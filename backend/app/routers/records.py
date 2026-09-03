from fastapi import APIRouter, HTTPException, Query
import json
from typing import Optional
from sqlalchemy import text
from app.database import get_db_connection
from app.models import RecordStatusUpdate

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
        d["collected_data"] = json.loads(d["collected_data"] or "{}")
        d["transcript"] = json.loads(d["transcript"] or "[]")
        d["tools_executed"] = json.loads(d["tools_executed"] or "[]")
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
