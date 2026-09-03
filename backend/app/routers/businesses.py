from fastapi import APIRouter, HTTPException
import uuid
from datetime import datetime, timezone
from sqlalchemy import text
from app.database import get_db_connection
from app.models import Business, BusinessCreate

router = APIRouter(prefix="/api/businesses", tags=["Businesses"])

@router.get("")
def list_businesses():
    with get_db_connection() as conn:
        result = conn.execute(text("SELECT * FROM businesses ORDER BY created_at DESC"))
        rows = [dict(r._mapping) for r in result]
    return {"success": True, "data": rows}

@router.get("/{business_id}")
def get_business(business_id: str):
    with get_db_connection() as conn:
        result = conn.execute(text("SELECT * FROM businesses WHERE id = :id"), {"id": business_id}).fetchone()
    if not result:
        raise HTTPException(status_code=404, detail="Business not found")
    return {"success": True, "data": dict(result._mapping)}

@router.post("")
def create_business(data: BusinessCreate):
    biz_id = f"biz-{str(uuid.uuid4())[:8]}"
    now = datetime.now(timezone.utc).isoformat()

    with get_db_connection() as conn:
        conn.execute(text("""
            INSERT INTO businesses (id, name, industry, owner_name, phone, email, address, created_at)
            VALUES (:id, :name, :industry, :owner_name, :phone, :email, :address, :created_at)
        """), {
            "id": biz_id, "name": data.name, "industry": data.industry,
            "owner_name": data.owner_name, "phone": data.phone, "email": data.email,
            "address": data.address or "", "created_at": now
        })
        conn.commit()

        result = conn.execute(text("SELECT * FROM businesses WHERE id = :id"), {"id": biz_id}).fetchone()
        created = dict(result._mapping)

    return {"success": True, "data": created}
