import os
import json
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

# Database Connection URI
DB_URL = os.getenv("DATABASE_URL")

if DB_URL:
    if DB_URL.startswith("prisma+postgres://"):
        DB_URL = DB_URL.replace("prisma+postgres://", "postgresql+pg8000://", 1)
    elif DB_URL.startswith("postgres://"):
        DB_URL = DB_URL.replace("postgres://", "postgresql+pg8000://", 1)
    elif DB_URL.startswith("postgresql://") and "pg8000" not in DB_URL:
        DB_URL = DB_URL.replace("postgresql://", "postgresql+pg8000://", 1)
    
    if "?" in DB_URL:
        base_url, query_str = DB_URL.split("?", 1)
        params = [p for p in query_str.split("&") if p and not p.startswith("api_key=") and not p.startswith("sslmode=")]
        DB_URL = f"{base_url}?{'&'.join(params)}" if params else base_url
else:
    is_serverless = os.getenv("AWS_LAMBDA_FUNCTION_NAME")
    if is_serverless:
        db_file = "/tmp/assistant.db"
    else:
        try:
            data_dir = os.path.join(os.path.dirname(__file__), "../data")
            os.makedirs(data_dir, exist_ok=True)
            db_file = os.path.join(data_dir, "assistant.db")
        except Exception:
            db_file = "/tmp/assistant.db"
    DB_URL = f"sqlite:///{db_file}"

print(f"[Database Engine] Connecting to: {DB_URL.split('@')[-1] if '@' in DB_URL else DB_URL}")

fallback_db_file = "/tmp/assistant.db" if os.getenv("AWS_LAMBDA_FUNCTION_NAME") else os.path.join(os.path.dirname(__file__), "../data/assistant.db")
fallback_engine = create_engine(f"sqlite:///{fallback_db_file}", connect_args={"check_same_thread": False})

try:
    if DB_URL.startswith("sqlite"):
        primary_engine = create_engine(DB_URL, connect_args={"check_same_thread": False})
    else:
        primary_engine = create_engine(DB_URL, pool_pre_ping=True)
except Exception as e:
    print(f"[Database Warning] Primary DB engine creation failed: {e}. Falling back to SQLite.")
    primary_engine = fallback_engine

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
                    address TEXT,
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
                    business_hours TEXT,
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
                    description TEXT,
                    status VARCHAR(32) NOT NULL DEFAULT 'Confirmed',
                    google_event_id VARCHAR(128),
                    created_at VARCHAR(64) NOT NULL
                );
            """))
            seed_default_data(conn)
    except Exception:
        pass

def init_db():
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
                    address TEXT,
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
                    business_hours TEXT,
                    is_active INT NOT NULL DEFAULT 1,
                    created_at VARCHAR(64) NOT NULL
                );
            """))

            try:
                conn.execute(text("ALTER TABLE workflows ADD COLUMN business_hours TEXT"))
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
                    description TEXT,
                    status VARCHAR(32) NOT NULL DEFAULT 'Confirmed',
                    google_event_id VARCHAR(128),
                    created_at VARCHAR(64) NOT NULL
                );
            """))

            seed_default_data(conn)
    except Exception as e:
        print(f"[Database Warning] Database initialization deferred/failed: {e}")

def seed_default_data(conn):
    print("Verifying & seeding multi-industry businesses, workflows, & calendar events...")
    now = datetime.now(timezone.utc).isoformat()

    # 1. Cake Shop Business
    cake_biz_id = "biz-cake-01"
    cake_wf_id = "wf-cake-01"
    if not conn.execute(text("SELECT id FROM businesses WHERE id = :id"), {"id": cake_biz_id}).fetchone():
        conn.execute(text("""
            INSERT INTO businesses (id, name, industry, owner_name, phone, email, address, created_at)
            VALUES (:id, :name, :industry, :owner_name, :phone, :email, :address, :created_at)
        """), {
            "id": cake_biz_id, "name": "Sweet Treats Bakery & Confectionery", "industry": "Cake Shop",
            "owner_name": "Ananya Sharma", "phone": "+91 98765 43210", "email": "orders@sweettreats.com",
            "address": "MG Road, Indiranagar, Bengaluru", "created_at": now
        })
        cake_fields = [
            {"key": "order_type", "label": "Order Type", "type": "select", "options": ["New Cake Order", "General Enquiry", "Custom Design"], "required": True},
            {"key": "cake_flavor", "label": "Cake Flavor", "type": "text", "required": True, "description": "e.g. Belgian Dark Chocolate, Red Velvet, Vanilla Mango"},
            {"key": "weight_kg", "label": "Weight (in kg)", "type": "number", "required": True, "description": "e.g. 1, 2, 5"},
            {"key": "required_date", "label": "Required Date & Time", "type": "datetime", "required": True},
            {"key": "custom_message", "label": "Message on Cake", "type": "text", "required": False},
            {"key": "delivery_preference", "label": "Delivery or Pickup", "type": "select", "options": ["Home Delivery", "Store Pickup"], "required": True},
            {"key": "budget_inr", "label": "Budget (INR)", "type": "number", "required": False}
        ]
        cake_conditions = [
            {"field": "required_date", "operator": "within_hours", "value": 24, "action_override": "mark_urgent", "note": "Mark urgent if required within 24 hours"}
        ]
        default_bh = json.dumps({
            "enabled": True,
            "days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
            "start_time": "09:00",
            "end_time": "18:00",
            "after_hours_greeting": "We are currently closed for the day. Our business operating hours are Mon-Sat 9 AM to 6 PM. We have logged your request and will follow up tomorrow morning.",
            "after_hours_action": "flag_after_hours"
        })
        conn.execute(text("""
            INSERT INTO workflows (id, business_id, name, industry, trigger_event, greeting, fields, conditions, actions, closing_message, language, business_hours, is_active, created_at)
            VALUES (:id, :business_id, :name, :industry, :trigger_event, :greeting, :fields, :conditions, :actions, :closing_message, :language, :business_hours, 1, :created_at)
        """), {
            "id": cake_wf_id, "business_id": cake_biz_id, "name": "Missed Call Cake Order & Enquiry", "industry": "Cake Shop",
            "trigger_event": "Missed Call", "greeting": "Namaste! Thank you for calling Sweet Treats Bakery. We missed your call. Would you like to place a new cake order or ask a general enquiry?",
            "fields": json.dumps(cake_fields), "conditions": json.dumps(cake_conditions), "actions": json.dumps(["create_order_enquiry", "send_owner_sms_alert"]),
            "closing_message": "Thank you! Your cake order details have been recorded. Our head baker will contact you shortly to confirm design and pricing.",
            "language": "en-hi", "business_hours": default_bh, "created_at": now
        })

    # 2. Clinic Business
    clinic_biz_id = "biz-clinic-01"
    clinic_wf_id = "wf-clinic-01"
    if not conn.execute(text("SELECT id FROM businesses WHERE id = :id"), {"id": clinic_biz_id}).fetchone():
        conn.execute(text("""
            INSERT INTO businesses (id, name, industry, owner_name, phone, email, address, created_at)
            VALUES (:id, :name, :industry, :owner_name, :phone, :email, :address, :created_at)
        """), {
            "id": clinic_biz_id, "name": "Apex Health Care & Multi-Specialty Clinic", "industry": "Clinic / Healthcare",
            "owner_name": "Dr. Ramesh Kumar", "phone": "+91 91234 56789", "email": "contact@apexcare.com",
            "address": "Koramangala 5th Block, Bengaluru", "created_at": now
        })
        clinic_fields = [
            {"key": "request_type", "label": "Request Type", "type": "select", "options": ["Book Appointment", "Reschedule Appointment", "Cancel Appointment", "General Enquiry"], "required": True},
            {"key": "patient_name", "label": "Patient Name", "type": "text", "required": True},
            {"key": "specialty_or_doctor", "label": "Specialty / Doctor", "type": "select", "options": ["General Physician", "Dermatologist", "Cardiologist", "Pediatrician", "Dentist"], "required": True},
            {"key": "preferred_date_time", "label": "Preferred Date & Time", "type": "datetime", "required": True},
            {"key": "symptoms_or_notes", "label": "Symptoms / Brief Note", "type": "text", "required": False}
        ]
        clinic_conditions = [
            {"field": "request_type", "operator": "equals", "value": "Book Appointment", "tool_action": "check_and_create_google_calendar", "note": "Checks calendar availability and creates Google Calendar event"}
        ]
        conn.execute(text("""
            INSERT INTO workflows (id, business_id, name, industry, trigger_event, greeting, fields, conditions, actions, closing_message, language, business_hours, is_active, created_at)
            VALUES (:id, :business_id, :name, :industry, :trigger_event, :greeting, :fields, :conditions, :actions, :closing_message, :language, :business_hours, 1, :created_at)
        """), {
            "id": clinic_wf_id, "business_id": clinic_biz_id, "name": "Patient Appointment Booking & Callback", "industry": "Clinic / Healthcare",
            "trigger_event": "Missed Call", "greeting": "Hello! You have reached Apex Health Clinic. We noticed we missed your call. Are you calling to book a doctor appointment, reschedule, or ask an enquiry?",
            "fields": json.dumps(clinic_fields), "conditions": json.dumps(clinic_conditions), "actions": json.dumps(["create_google_calendar_event", "send_patient_confirmation_sms"]),
            "closing_message": "Your appointment request has been scheduled on our calendar. Please do not take this as medical emergency advice. Our front desk will verify your details.",
            "language": "en-hi", "business_hours": default_bh, "created_at": now
        })

    # 3. Logistics & Delivery Business
    logistics_biz_id = "biz-logistics-01"
    logistics_wf_id = "wf-logistics-01"
    if not conn.execute(text("SELECT id FROM businesses WHERE id = :id"), {"id": logistics_biz_id}).fetchone():
        conn.execute(text("""
            INSERT INTO businesses (id, name, industry, owner_name, phone, email, address, created_at)
            VALUES (:id, :name, :industry, :owner_name, :phone, :email, :address, :created_at)
        """), {
            "id": logistics_biz_id, "name": "SwiftMove Express Logistics & Delivery", "industry": "Logistics & Delivery",
            "owner_name": "Vikram Singh", "phone": "+91 99887 76655", "email": "support@swiftmove.com",
            "address": "Electronic City Phase 1, Bengaluru", "created_at": now
        })
        logistics_fields = [
            {"key": "tracking_number", "label": "Waybill / Tracking Number", "type": "text", "required": True, "description": "e.g. TRK-9821-IN"},
            {"key": "inquiry_type", "label": "Inquiry Type", "type": "select", "options": ["Package Status", "Delivery Delay", "Address Change"], "required": True}
        ]
        logistics_conditions = [
            {"field": "tracking_number", "operator": "exists", "tool_action": "track_delivery_status", "note": "Calls REST API endpoint to query parcel location"}
        ]
        conn.execute(text("""
            INSERT INTO workflows (id, business_id, name, industry, trigger_event, greeting, fields, conditions, actions, closing_message, language, business_hours, is_active, created_at)
            VALUES (:id, :business_id, :name, :industry, :trigger_event, :greeting, :fields, :conditions, :actions, :closing_message, :language, :business_hours, 1, :created_at)
        """), {
            "id": logistics_wf_id, "business_id": logistics_biz_id, "name": "Parcel Tracking & Delivery Status Callback", "industry": "Logistics & Delivery",
            "trigger_event": "Missed Call", "greeting": "Hello! Welcome to SwiftMove Express. We missed your call. Please speak or type your tracking number (e.g. TRK-9821-IN) to get real-time delivery updates.",
            "fields": json.dumps(logistics_fields), "conditions": json.dumps(logistics_conditions), "actions": json.dumps(["track_delivery_status_api", "send_whatsapp_tracking_link"]),
            "closing_message": "Your parcel status has been retrieved from our live delivery API. Our courier agent will contact you upon dispatch.",
            "language": "en-hi", "business_hours": default_bh, "created_at": now
        })

    # 4. Real Estate Agency Business
    re_biz_id = "biz-re-01"
    re_wf_id = "wf-re-01"
    if not conn.execute(text("SELECT id FROM businesses WHERE id = :id"), {"id": re_biz_id}).fetchone():
        conn.execute(text("""
            INSERT INTO businesses (id, name, industry, owner_name, phone, email, address, created_at)
            VALUES (:id, :name, :industry, :owner_name, :phone, :email, :address, :created_at)
        """), {
            "id": re_biz_id, "name": "Prime Haven Realty & Property Solutions", "industry": "Real Estate",
            "owner_name": "Rajesh Mehta", "phone": "+91 97766 55443", "email": "sales@primehaven.com",
            "address": "Whitefield Main Road, Bengaluru", "created_at": now
        })
        re_fields = [
            {"key": "property_type", "label": "Property Type", "type": "select", "options": ["3BHK Villa", "2BHK Apartment", "Commercial Plot", "Penthouse"], "required": True},
            {"key": "budget_range", "label": "Budget Range", "type": "text", "required": True, "description": "e.g. 80 Lakhs - 1.5 Crore"},
            {"key": "visit_date_time", "label": "Preferred Site Visit Time", "type": "datetime", "required": True}
        ]
        re_conditions = [
            {"field": "visit_date_time", "operator": "exists", "tool_action": "create_calendar_event", "note": "Schedules property site visit on Google Calendar"}
        ]
        conn.execute(text("""
            INSERT INTO workflows (id, business_id, name, industry, trigger_event, greeting, fields, conditions, actions, closing_message, language, business_hours, is_active, created_at)
            VALUES (:id, :business_id, :name, :industry, :trigger_event, :greeting, :fields, :conditions, :actions, :closing_message, :language, :business_hours, 1, :created_at)
        """), {
            "id": re_wf_id, "business_id": re_biz_id, "name": "Property Lead Qualification & Site Visit", "industry": "Real Estate",
            "trigger_event": "Missed Call", "greeting": "Hello! Thank you for contacting Prime Haven Realty. We missed your call. Are you interested in scheduling a property site visit or inquiring about buyer listings?",
            "fields": json.dumps(re_fields), "conditions": json.dumps(re_conditions), "actions": json.dumps(["schedule_site_visit_gcal", "assign_lead_to_agent"]),
            "closing_message": "Your property site visit has been scheduled on Google Calendar. Our lead relationship executive will guide you at the location.",
            "language": "en-hi", "business_hours": default_bh, "created_at": now
        })

    # 5. Home & Repair Service Business
    repair_biz_id = "biz-repair-01"
    repair_wf_id = "wf-repair-01"
    if not conn.execute(text("SELECT id FROM businesses WHERE id = :id"), {"id": repair_biz_id}).fetchone():
        conn.execute(text("""
            INSERT INTO businesses (id, name, industry, owner_name, phone, email, address, created_at)
            VALUES (:id, :name, :industry, :owner_name, :phone, :email, :address, :created_at)
        """), {
            "id": repair_biz_id, "name": "FixIt Pro Maintenance & Emergency Repair", "industry": "Home Repair Services",
            "owner_name": "Suresh Babu", "phone": "+91 96655 44332", "email": "dispatch@fixitpro.com",
            "address": "Jayanagar 4th Block, Bengaluru", "created_at": now
        })
        repair_fields = [
            {"key": "service_category", "label": "Service Category", "type": "select", "options": ["Plumbing Emergency", "Electrical Repair", "AC Servicing", "Carpentry"], "required": True},
            {"key": "urgency_level", "label": "Urgency Level", "type": "select", "options": ["Immediate Emergency", "Same Day", "Scheduled"], "required": True},
            {"key": "problem_description", "label": "Problem Description", "type": "text", "required": False}
        ]
        repair_conditions = [
            {"field": "urgency_level", "operator": "equals", "value": "Immediate Emergency", "action_override": "flag_critical", "note": "Flag CRITICAL for immediate technician dispatch"}
        ]
        conn.execute(text("""
            INSERT INTO workflows (id, business_id, name, industry, trigger_event, greeting, fields, conditions, actions, closing_message, language, business_hours, is_active, created_at)
            VALUES (:id, :business_id, :name, :industry, :trigger_event, :greeting, :fields, :conditions, :actions, :closing_message, :language, :business_hours, 1, :created_at)
        """), {
            "id": repair_wf_id, "business_id": repair_biz_id, "name": "Emergency Repair Request & Technician Dispatch", "industry": "Home Repair Services",
            "trigger_event": "Missed Call", "greeting": "Hello! FixIt Pro Repair Services missed your call. What repair service do you require, and is this an immediate emergency?",
            "fields": json.dumps(repair_fields), "conditions": json.dumps(repair_conditions), "actions": json.dumps(["dispatch_technician_alert", "send_status_tracking_sms"]),
            "closing_message": "Your repair request has been logged. If marked CRITICAL emergency, our nearest technician is already dispatched to your location.",
            "language": "en-hi", "business_hours": default_bh, "created_at": now
        })

    # Seed Sample Call Records if empty
    rec_count = conn.execute(text("SELECT COUNT(*) FROM records")).fetchone()[0]
    if rec_count == 0:
        conn.execute(text("""
            INSERT INTO records (id, business_id, workflow_id, caller_name, caller_phone, intent, collected_data, ai_summary, urgency, followup_status, transcript, tools_executed, created_at)
            VALUES (:id, :business_id, :workflow_id, :caller_name, :caller_phone, :intent, :collected_data, :ai_summary, :urgency, :followup_status, :transcript, :tools_executed, :created_at)
        """), {
            "id": "rec-cake-01", "business_id": cake_biz_id, "workflow_id": cake_wf_id,
            "caller_name": "Rahul Kapur", "caller_phone": "+91 98112 33445", "intent": "New Cake Order - Birthday",
            "collected_data": json.dumps({
                "order_type": "New Cake Order", "cake_flavor": "Belgian Dark Chocolate Fudge", "weight_kg": 2,
                "required_date": (datetime.now() + timedelta(hours=18)).isoformat(), "custom_message": "Happy 30th Birthday Sameer!",
                "delivery_preference": "Home Delivery", "budget_inr": 2500
            }),
            "ai_summary": "Customer wants a 2kg Belgian Dark Chocolate Fudge cake delivered within 18 hours. Custom message requested. Marked URGENT as delivery is required under 24h.",
            "urgency": "Urgent", "followup_status": "Pending",
            "transcript": json.dumps([
                {"role": "assistant", "content": "Namaste! Thank you for calling Sweet Treats Bakery. We missed your call. Would you like to place a new cake order or ask a general enquiry?"},
                {"role": "user", "content": "Hi! I want to order a birthday cake for tomorrow evening."},
                {"role": "assistant", "content": "Great! What flavor and weight would you prefer?"},
                {"role": "user", "content": "Belgian Dark Chocolate Fudge, 2kg. Deliver to HSR layout by 6 PM tomorrow."}
            ]),
            "tools_executed": json.dumps([{"tool": "evaluate_urgency_condition", "result": "Urgent flag set (delivery < 24h)"}]),
            "created_at": (datetime.now() - timedelta(hours=2)).isoformat()
        })

    # Seed Sample Google Calendar Events if empty
    cal_count = conn.execute(text("SELECT COUNT(*) FROM calendar_events")).fetchone()[0]
    if cal_count == 0:
        start1 = datetime.now() + timedelta(days=1)
        start1 = start1.replace(hour=16, minute=0, second=0, microsecond=0)
        end1 = start1 + timedelta(minutes=30)

        start2 = datetime.now() + timedelta(days=2)
        start2 = start2.replace(hour=11, minute=0, second=0, microsecond=0)
        end2 = start2 + timedelta(minutes=45)

        conn.execute(text("""
            INSERT INTO calendar_events (id, business_id, title, start_time, end_time, attendee_name, attendee_phone, description, status, google_event_id, created_at)
            VALUES (:id, :bid, :title, :st, :et, :aname, :aphone, :desc, 'Confirmed', :gid, :cat)
        """), {
            "id": "cal-seed-01", "bid": clinic_biz_id, "title": "Clinic / Healthcare - Meera Nair",
            "st": start1.isoformat(), "et": end1.isoformat(), "aname": "Meera Nair", "aphone": "+91 97441 22334",
            "desc": "Scheduled via Voice AI Assistant (Dermatology Consultation)", "gid": "gcal_py_cal_991823", "cat": now
        })

        conn.execute(text("""
            INSERT INTO calendar_events (id, business_id, title, start_time, end_time, attendee_name, attendee_phone, description, status, google_event_id, created_at)
            VALUES (:id, :bid, :title, :st, :et, :aname, :aphone, :desc, 'Confirmed', :gid, :cat)
        """), {
            "id": "cal-seed-02", "bid": re_biz_id, "title": "Real Estate - Ankit Mehta",
            "st": start2.isoformat(), "et": end2.isoformat(), "aname": "Ankit Mehta", "aphone": "+91 98765 12345",
            "desc": "Scheduled via Voice AI Assistant (3BHK Villa Property Site Visit)", "gid": "gcal_py_cal_991824", "cat": now
        })
