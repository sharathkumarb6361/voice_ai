from fastapi import APIRouter, HTTPException, Query
import uuid
import json
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import text
from app.database import get_db_connection
from app.models import WorkflowCreate, WorkflowUpdate

router = APIRouter(prefix="/api/workflows", tags=["Workflows"])

@router.get("")
def list_workflows(business_id: Optional[str] = Query(None)):
    with get_db_connection() as conn:
        if business_id:
            result = conn.execute(text("""
                SELECT w.*, b.name as business_name 
                FROM workflows w JOIN businesses b ON w.business_id = b.id 
                WHERE w.business_id = :bid ORDER BY w.created_at DESC
            """), {"bid": business_id})
        else:
            result = conn.execute(text("""
                SELECT w.*, b.name as business_name 
                FROM workflows w JOIN businesses b ON w.business_id = b.id 
                ORDER BY w.created_at DESC
            """))
        rows = result.fetchall()

    formatted = []
    for r in rows:
        d = dict(r._mapping)
        d["fields"] = json.loads(d["fields"] or "[]")
        d["conditions"] = json.loads(d["conditions"] or "[]")
        d["actions"] = json.loads(d["actions"] or "[]")
        try:
            d["business_hours"] = json.loads(d.get("business_hours")) if d.get("business_hours") else None
        except Exception:
            d["business_hours"] = None
        formatted.append(d)

    return {"success": True, "data": formatted}

@router.get("/{workflow_id}")
def get_workflow(workflow_id: str):
    with get_db_connection() as conn:
        result = conn.execute(text("""
            SELECT w.*, b.name as business_name 
            FROM workflows w JOIN businesses b ON w.business_id = b.id 
            WHERE w.id = :id
        """), {"id": workflow_id}).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Workflow not found")

    d = dict(result._mapping)
    d["fields"] = json.loads(d["fields"] or "[]")
    d["conditions"] = json.loads(d["conditions"] or "[]")
    d["actions"] = json.loads(d["actions"] or "[]")
    try:
        d["business_hours"] = json.loads(d.get("business_hours")) if d.get("business_hours") else None
    except Exception:
        d["business_hours"] = None
    return {"success": True, "data": d}

@router.post("")
def create_workflow(data: WorkflowCreate):
    wf_id = f"wf-{str(uuid.uuid4())[:8]}"
    now = datetime.now(timezone.utc).isoformat()

    fields_json = json.dumps([f.model_dump() for f in data.fields])
    conditions_json = json.dumps([c.model_dump() for c in data.conditions])
    actions_json = json.dumps(data.actions)
    biz_hours_json = json.dumps(data.business_hours.model_dump()) if data.business_hours else None

    with get_db_connection() as conn:
        conn.execute(text("""
            INSERT INTO workflows (id, business_id, name, industry, trigger_event, greeting, fields, conditions, actions, closing_message, language, business_hours, is_active, created_at)
            VALUES (:id, :business_id, :name, :industry, :trigger_event, :greeting, :fields, :conditions, :actions, :closing_message, :language, :b_hours, :is_active, :created_at)
        """), {
            "id": wf_id, "business_id": data.business_id, "name": data.name, "industry": data.industry,
            "trigger_event": data.trigger_event, "greeting": data.greeting,
            "fields": fields_json, "conditions": conditions_json, "actions": actions_json,
            "closing_message": data.closing_message, "language": data.language,
            "b_hours": biz_hours_json, "is_active": data.is_active,
            "created_at": now
        })
        conn.commit()

        result = conn.execute(text("SELECT * FROM workflows WHERE id = :id"), {"id": wf_id}).fetchone()
        created = dict(result._mapping)
        created["fields"] = json.loads(created["fields"])
        created["conditions"] = json.loads(created["conditions"])
        created["actions"] = json.loads(created["actions"])
        try:
            created["business_hours"] = json.loads(created["business_hours"]) if created.get("business_hours") else None
        except Exception:
            created["business_hours"] = None

    return {"success": True, "data": created}

@router.put("/{workflow_id}")
def update_workflow(workflow_id: str, data: WorkflowUpdate):
    with get_db_connection() as conn:
        existing = conn.execute(text("SELECT * FROM workflows WHERE id = :id"), {"id": workflow_id}).fetchone()
        if not existing:
            raise HTTPException(status_code=404, detail="Workflow not found")

        ex_dict = dict(existing._mapping)

        name = data.name if data.name is not None else ex_dict["name"]
        greeting = data.greeting if data.greeting is not None else ex_dict["greeting"]
        closing = data.closing_message if data.closing_message is not None else ex_dict["closing_message"]
        language = data.language if data.language is not None else ex_dict["language"]
        is_active = data.is_active if data.is_active is not None else ex_dict["is_active"]

        fields_json = json.dumps([f.model_dump() for f in data.fields]) if data.fields is not None else ex_dict["fields"]
        conditions_json = json.dumps([c.model_dump() for c in data.conditions]) if data.conditions is not None else ex_dict["conditions"]
        actions_json = json.dumps(data.actions) if data.actions is not None else ex_dict["actions"]
        biz_hours_json = json.dumps(data.business_hours.model_dump()) if data.business_hours is not None else ex_dict.get("business_hours")

        conn.execute(text("""
            UPDATE workflows 
            SET name = :name, greeting = :greeting, closing_message = :closing, 
                language = :lang, fields = :fields, conditions = :conds, 
                actions = :actions, business_hours = :b_hours, is_active = :is_active
            WHERE id = :id
        """), {
            "name": name, "greeting": greeting, "closing": closing, "lang": language,
            "fields": fields_json, "conds": conditions_json, "actions": actions_json,
            "b_hours": biz_hours_json, "is_active": is_active, "id": workflow_id
        })
        conn.commit()

        result = conn.execute(text("SELECT * FROM workflows WHERE id = :id"), {"id": workflow_id}).fetchone()
        updated = dict(result._mapping)
        updated["fields"] = json.loads(updated["fields"])
        updated["conditions"] = json.loads(updated["conditions"])
        updated["actions"] = json.loads(updated["actions"])
        try:
            updated["business_hours"] = json.loads(updated["business_hours"]) if updated.get("business_hours") else None
        except Exception:
            updated["business_hours"] = None

    return {"success": True, "data": updated}
