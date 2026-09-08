import os
import json
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

def _local_sqlite_path():
    is_serverless = os.getenv("AWS_LAMBDA_FUNCTION_NAME")
    if is_serverless:
        return "/tmp/assistant.db"
    try:
        data_dir = os.path.join(os.path.dirname(__file__), "../data")
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, "assistant.db")
    except Exception:
        return "/tmp/assistant.db"

def _normalize_database_url(raw_url: str | None) -> str:
    value = (raw_url or "").strip()
    placeholder = (
        not value
        or "your_" in value.lower()
        or "postgres:password@localhost" in value
        or value.endswith("/voice_ai_assistant") and "localhost" in value
    )
    if placeholder:
        return f"sqlite:///{_local_sqlite_path()}"

    if value.startswith("prisma+postgres://"):
        value = value.replace("prisma+postgres://", "postgresql+pg8000://", 1)
    elif value.startswith("postgres://"):
        value = value.replace("postgres://", "postgresql+pg8000://", 1)
    elif value.startswith("postgresql://") and "pg8000" not in value:
        value = value.replace("postgresql://", "postgresql+pg8000://", 1)

    if "?" in value:
        base_url, query_str = value.split("?", 1)
        params = [p for p in query_str.split("&") if p and not p.startswith("api_key=") and not p.startswith("sslmode=")]
        value = f"{base_url}?{'&'.join(params)}" if params else base_url
    return value

# Database Connection URI — local SQLite unless a real remote DATABASE_URL is set
DB_URL = _normalize_database_url(os.getenv("DATABASE_URL"))

print(f"[Database Engine] Connecting to: {DB_URL.split('@')[-1] if '@' in DB_URL else DB_URL}")

fallback_db_file = _local_sqlite_path()
fallback_engine = create_engine(f"sqlite:///{fallback_db_file}", connect_args={"check_same_thread": False})

try:
    if DB_URL.startswith("sqlite"):
        primary_engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
    else:
        primary_engine = create_engine(DB_URL, pool_pre_ping=True)
        with primary_engine.connect() as probe:
            probe.execute(text("SELECT 1"))
except Exception as e:
    print(f"[Database Warning] Primary DB engine unavailable ({e}). Falling back to SQLite.")
    primary_engine = fallback_engine
    DB_URL = f"sqlite:///{fallback_db_file}"

engine = primary_engine

def get_db_connection():
    try:
        conn = primary_engine.connect()
        # Verify connection works
        conn.execute(text("SELECT 1"))
        return conn
    except Exception as e:
        print(f"[Database Warning] Primary connection failed ({e}), using SQLite fallback.")
        try:
            init_sqlite_fallback()
        except Exception:
            pass
        return fallback_engine.connect()

def init_sqlite_fallback():
    try:
        with fallback_engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS businesses (
                    id VARCHAR(64) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    industry VARCHAR(128) NOT NULL,
                    owner_name VARCHAR(255) NOT NULL,
                    phone VARCHAR(64) NOT NULL,
                    email VARCHAR(255) NOT NULL,
                    address TEXT NOT NULL DEFAULT '',
                    created_at VARCHAR(64) NOT NULL
                );
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS workflows (
                    id VARCHAR(64) PRIMARY KEY,
                    business_id VARCHAR(64) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    industry VARCHAR(128) NOT NULL,
                    trigger_event VARCHAR(128) NOT NULL,
                    greeting TEXT NOT NULL,
                    fields TEXT NOT NULL,
                    conditions TEXT NOT NULL,
                    actions TEXT NOT NULL,
                    closing_message TEXT NOT NULL,
                    language VARCHAR(32) NOT NULL DEFAULT 'en-hi',
                    business_hours TEXT NOT NULL DEFAULT '',
                    is_active INT NOT NULL DEFAULT 1,
                    created_at VARCHAR(64) NOT NULL
                );
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS records (
                    id VARCHAR(64) PRIMARY KEY,
                    business_id VARCHAR(64) NOT NULL,
                    workflow_id VARCHAR(64) NOT NULL,
                    caller_name VARCHAR(255) NOT NULL,
                    caller_phone VARCHAR(64) NOT NULL,
                    intent VARCHAR(255) NOT NULL,
                    collected_data TEXT NOT NULL,
                    ai_summary TEXT NOT NULL,
                    urgency VARCHAR(32) NOT NULL DEFAULT 'Normal',
                    followup_status VARCHAR(32) NOT NULL DEFAULT 'Pending',
                    transcript TEXT NOT NULL,
                    tools_executed TEXT NOT NULL,
                    created_at VARCHAR(64) NOT NULL
                );
            """))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS calendar_events (
                    id VARCHAR(64) PRIMARY KEY,
                    business_id VARCHAR(64) NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    start_time VARCHAR(64) NOT NULL,
                    end_time VARCHAR(64) NOT NULL,
                    attendee_name VARCHAR(255) NOT NULL,
                    attendee_phone VARCHAR(64) NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    status VARCHAR(32) NOT NULL DEFAULT 'Confirmed',
                    google_event_id VARCHAR(128) NOT NULL DEFAULT '',
                    created_at VARCHAR(64) NOT NULL
                );
            """))
            seed_default_data(conn)
    except Exception:
        pass

def init_db():
    global engine, primary_engine
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS businesses (
                    id VARCHAR(64) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    industry VARCHAR(128) NOT NULL,
                    owner_name VARCHAR(255) NOT NULL,
                    phone VARCHAR(64) NOT NULL,
                    email VARCHAR(255) NOT NULL,
                    address TEXT NOT NULL DEFAULT '',
                    created_at VARCHAR(64) NOT NULL
                );
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS workflows (
                    id VARCHAR(64) PRIMARY KEY,
                    business_id VARCHAR(64) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    industry VARCHAR(128) NOT NULL,
                    trigger_event VARCHAR(128) NOT NULL,
                    greeting TEXT NOT NULL,
                    fields TEXT NOT NULL,
                    conditions TEXT NOT NULL,
                    actions TEXT NOT NULL,
                    closing_message TEXT NOT NULL,
                    language VARCHAR(32) NOT NULL DEFAULT 'en-hi',
                    business_hours TEXT NOT NULL DEFAULT '',
                    is_active INT NOT NULL DEFAULT 1,
                    created_at VARCHAR(64) NOT NULL
                );
            """))

            try:
                conn.execute(text("ALTER TABLE workflows ADD COLUMN business_hours TEXT NOT NULL DEFAULT ''"))
            except Exception:
                pass

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS records (
                    id VARCHAR(64) PRIMARY KEY,
                    business_id VARCHAR(64) NOT NULL,
                    workflow_id VARCHAR(64) NOT NULL,
                    caller_name VARCHAR(255) NOT NULL,
                    caller_phone VARCHAR(64) NOT NULL,
                    intent VARCHAR(255) NOT NULL,
                    collected_data TEXT NOT NULL,
                    ai_summary TEXT NOT NULL,
                    urgency VARCHAR(32) NOT NULL DEFAULT 'Normal',
                    followup_status VARCHAR(32) NOT NULL DEFAULT 'Pending',
                    transcript TEXT NOT NULL,
                    tools_executed TEXT NOT NULL,
                    created_at VARCHAR(64) NOT NULL
                );
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS calendar_events (
                    id VARCHAR(64) PRIMARY KEY,
                    business_id VARCHAR(64) NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    start_time VARCHAR(64) NOT NULL,
                    end_time VARCHAR(64) NOT NULL,
                    attendee_name VARCHAR(255) NOT NULL,
                    attendee_phone VARCHAR(64) NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    status VARCHAR(32) NOT NULL DEFAULT 'Confirmed',
                    google_event_id VARCHAR(128) NOT NULL DEFAULT '',
                    created_at VARCHAR(64) NOT NULL
                );
            """))

            seed_default_data(conn)
    except Exception as e:
        print(f"[Database Warning] Primary database initialization failed: {e}. Seeding SQLite fallback.")
        primary_engine = fallback_engine
        engine = fallback_engine
        init_sqlite_fallback()

DEFAULT_BUSINESS_HOURS = {
    "enabled": True,
    "days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
    "start_time": "09:00",
    "end_time": "18:00",
    "after_hours_greeting": "We are currently closed for the day. Our business operating hours are Mon-Sat 9 AM to 6 PM. We have logged your request and will follow up tomorrow morning.",
    "after_hours_action": "flag_after_hours"
}

def cake_shop_workflow_spec(business_name: str = "Sweet Treats Bakery"):
    return {
        "name": "Missed Call Cake Order & Enquiry",
        "industry": "Cake Shop",
        "trigger_event": "Missed Call",
        "greeting": f"Namaste! Thank you for calling {business_name}. We missed your call. Are you looking to order a cake or do you have a general enquiry?",
        "fields": [
            {"key": "order_type", "label": "Order Type", "type": "select", "options": ["New Cake Order", "General Enquiry", "Custom Design"], "required": True},
            {"key": "cake_type", "label": "Cake Type / Occasion", "type": "select", "options": ["Birthday Cake", "Anniversary Cake", "Tier Wedding Cake", "Theme Custom Cake", "Pastry Box"], "required": False},
            {"key": "cake_flavor", "label": "Cake Flavor", "type": "text", "required": True, "description": "e.g. Belgian Dark Chocolate, Red Velvet, Vanilla Mango"},
            {"key": "weight_kg", "label": "Weight (in kg)", "type": "number", "required": True, "description": "e.g. 1, 2, 5"},
            {"key": "required_date", "label": "Required Date & Time", "type": "datetime", "required": True},
            {"key": "custom_message", "label": "Message on Cake", "type": "text", "required": True, "description": "Custom inscription or message on cake"},
            {"key": "delivery_preference", "label": "Delivery or Pickup", "type": "select", "options": ["Home Delivery", "Store Pickup"], "required": True},
            {"key": "budget_inr", "label": "Budget (INR)", "type": "number", "required": True, "description": "Estimated budget in INR"}
        ],
        "conditions": [
            {"field": "required_date", "operator": "within_hours", "value": 24, "action_override": "mark_urgent", "note": "Mark urgent if required within 24 hours"}
        ],
        "actions": ["create_order_enquiry", "send_owner_summary_alert", "create_calendar_event"],
        "closing_message": "Thank you! Your cake order enquiry details have been recorded. Our head baker will contact you shortly to confirm design and pricing.",
        "language": "en-hi",
    }

def logistics_workflow_spec(business_name: str = "SwiftMove Express"):
    return {
        "name": "Missed Call Delivery & Logistics Assistant",
        "industry": "Logistics & Delivery",
        "trigger_event": "Missed Call",
        "greeting": f"Hi, this is the delivery assistant calling you back regarding your missed call. Are you looking to create a new delivery, check the status of an existing delivery, or get help with an existing delivery?",
        "fields": [
            {"key": "intent", "label": "Request Type", "type": "select", "options": ["NEW_DELIVERY", "STATUS_UPDATE", "EXISTING_DELIVERY_HELP"], "required": True, "description": "New Delivery, Status Update, or Existing Help"},
            {"key": "pickup_location", "label": "Pickup Location", "type": "text", "required": True, "description": "Package pickup address/hub"},
            {"key": "delivery_location", "label": "Delivery Location", "type": "text", "required": True, "description": "Destination address"},
            {"key": "package_type", "label": "Package Type", "type": "select", "options": ["documents", "small package", "electronics", "fragile item", "furniture or heavy item", "parcel"], "required": True},
            {"key": "preferred_time", "label": "Preferred Pickup Time", "type": "text", "required": True, "description": "e.g. Tomorrow 10 AM, Today evening"},
            {"key": "contact_details", "label": "Contact Number", "type": "text", "required": True, "description": "Driver dispatch phone number"},
            {"key": "tracking_number", "label": "Tracking / Order Number", "type": "text", "required": False, "description": "e.g. TRK-9821-IN, ORD-5544"},
            {"key": "issue_description", "label": "Issue / Help Description", "type": "text", "required": False, "description": "Details of delivery problem or delay"}
        ],
        "conditions": [
            {"field": "intent", "operator": "equals", "value": "NEW_DELIVERY", "tool_action": "create_delivery_request", "note": "Creates a new delivery pickup task"},
            {"field": "tracking_number", "operator": "exists", "tool_action": "track_delivery_status", "note": "Queries live parcel location and status"},
            {"field": "intent", "operator": "equals", "value": "EXISTING_DELIVERY_HELP", "tool_action": "create_callback_task", "note": "Creates a dispatch team callback task"}
        ],
        "actions": ["create_delivery_request", "track_delivery_status_api", "create_dispatch_callback_task"],
        "closing_message": "Your delivery request has been processed. Our dispatch team will follow up as scheduled. Thank you for choosing SwiftMove Express, goodbye!",
        "language": "en-hi",
    }

def workflow_spec_for_industry(industry: str, business_name: str):
    if "logistics" in (industry or "").lower() or "delivery" in (industry or "").lower():
        return logistics_workflow_spec(business_name)
    return cake_shop_workflow_spec(business_name)

def insert_workflow(conn, workflow_id: str, business_id: str, spec: dict, created_at: str):
    conn.execute(text("""
        INSERT INTO workflows (id, business_id, name, industry, trigger_event, greeting, fields, conditions, actions, closing_message, language, business_hours, is_active, created_at)
        VALUES (:id, :business_id, :name, :industry, :trigger_event, :greeting, :fields, :conditions, :actions, :closing_message, :language, :business_hours, 1, :created_at)
    """), {
        "id": workflow_id, "business_id": business_id, "name": spec["name"], "industry": spec["industry"],
        "trigger_event": spec["trigger_event"], "greeting": spec["greeting"],
        "fields": json.dumps(spec["fields"]), "conditions": json.dumps(spec["conditions"]), "actions": json.dumps(spec["actions"]),
        "closing_message": spec["closing_message"], "language": spec["language"],
        "business_hours": json.dumps(DEFAULT_BUSINESS_HOURS), "created_at": created_at
    })

def create_industry_workflow(conn, business_id: str, industry: str, business_name: str, workflow_id: str | None = None):
    spec = workflow_spec_for_industry(industry, business_name)
    wf_id = workflow_id or f"wf-{business_id.replace('biz-', '')}"
    now = datetime.now(timezone.utc).isoformat()
    insert_workflow(conn, wf_id, business_id, spec, now)
    return wf_id

def _ensure_business_and_workflow(conn, biz_id: str, biz: dict, wf_id: str, spec: dict, created_at: str):
    if not conn.execute(text("SELECT id FROM businesses WHERE id = :id"), {"id": biz_id}).fetchone():
        conn.execute(text("""
            INSERT INTO businesses (id, name, industry, owner_name, phone, email, address, created_at)
            VALUES (:id, :name, :industry, :owner_name, :phone, :email, :address, :created_at)
        """), {**biz, "id": biz_id, "created_at": created_at})
    if not conn.execute(text("SELECT id FROM workflows WHERE id = :id"), {"id": wf_id}).fetchone():
        insert_workflow(conn, wf_id, biz_id, spec, created_at)

def seed_default_data(conn):
    print("Verifying & seeding target businesses (Cake Shop & Logistics/Delivery)...")
    now = datetime.now(timezone.utc).isoformat()

    _ensure_business_and_workflow(conn, "biz-cake-01", {
        "name": "Sweet Treats Bakery & Confectionery", "industry": "Cake Shop",
        "owner_name": "Ananya Sharma", "phone": "+91 98765 43210", "email": "orders@sweettreats.com",
        "address": "MG Road, Indiranagar, Bengaluru"
    }, "wf-cake-01", cake_shop_workflow_spec("Sweet Treats Bakery"), now)

    _ensure_business_and_workflow(conn, "biz-logistics-01", {
        "name": "SwiftMove Express Logistics & Delivery", "industry": "Logistics & Delivery",
        "owner_name": "Vikram Singh", "phone": "+91 99887 76655", "email": "support@swiftmove.com",
        "address": "Electronic City Phase 1, Bengaluru"
    }, "wf-logistics-01", logistics_workflow_spec("SwiftMove Express"), now)
