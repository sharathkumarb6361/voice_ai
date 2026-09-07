# System Architecture Blueprint & Workflow Data Model

This document details the decoupled architecture, tool calling execution engine, multi-language voice engine, entity-relationship database schema, and workflow data models for the **Voice AI Personal Assistant**.

---

## 1. High-Level Architecture Diagram

![System Architecture](docs/images/system-architecture.png)

```mermaid
flowchart TB
    subgraph ClientLayer ["1. Caller & Client Interface"]
        direction TB
        Caller["📞 Incoming Caller / Missed Call<br/>(Customer: Rahul / Vikram)"]
        Simulator["💻 Real-Time Phone Simulator UI<br/>(Continuous Hands-Free / Manual Audio)"]
        DashboardUI["📊 Small Business Dashboard UI<br/>(React.js + Vite + Tailwind CSS)"]
    end

    subgraph SpeechLayer ["2. Multi-Language Audio Pipeline (Pipecat / Native)"]
        direction TB
        Mic["Microphone Stream"] --> STT["Speech-to-Text (STT)<br/>• Sarvam AI (Saarika v2.5: Hindi & Kannada)<br/>• Groq Whisper-Large-v3<br/>• Web Speech API Backup"]
        TTS["Text-to-Speech (TTS)<br/>• Sarvam AI (Bulbul v3: hi-IN, kn-IN)<br/>• ElevenLabs Multilingual v2<br/>• gTTS Engine"] --> Speaker["Audio Playback / Real-time Equalizer"]
    end

    subgraph BackendLayer ["3. Python FastAPI Core Engine"]
        direction TB
        APIGateway["FastAPI Routing Gateway<br/>/api/ai/chat • /api/workflows • /api/records"]
        LangRouter["Language Detection & Dynamic Switching<br/>(EN ⇄ HI ⇄ KN)"]
        BizHoursEngine["Operating Hours & Availability Evaluator<br/>(Mon-Sat 9AM-6PM / After-Hours Flagging)"]
        Orchestrator["AI Orchestrator & Tool Calling Engine<br/>(AiService.process_conversation)"]
        GroqLLM["Groq LPU Cloud API<br/>(Llama-3.3-70b-versatile, <300ms latency)"]
        RuleEngine["Conditional Rule & Urgency Evaluator<br/>(Urgent &lt; 24h, Critical Emergency)"]
    end

    subgraph ToolIntegrations ["4. Automated External Tool Integrations"]
        direction TB
        CakeShopTools["🎂 Cake Shop Tools<br/>• create_order_enquiry<br/>• send_owner_summary_alert"]
        LogisticsTools["🚚 Logistics & Delivery Tools<br/>• create_delivery_request<br/>• track_delivery_status<br/>• create_callback_task<br/>• lookup_crm_customer"]
        CalendarTools["📅 Calendar & Clinic Tools<br/>• check_calendar_availability<br/>• create_calendar_event<br/>• update_calendar_event<br/>• cancel_calendar_event"]
    end

    subgraph PersistenceLayer ["5. Persistence & Data Layer"]
        direction TB
        PrimaryDB[("Primary Database<br/>SQLite / PostgreSQL (Neon/Supabase)")]
        GoogleCalAPI["Google Calendar Cloud API<br/>(Two-way Sync)"]
    end

    Caller <--> Simulator
    Simulator --> Mic
    STT --> APIGateway
    APIGateway --> LangRouter
    LangRouter --> BizHoursEngine
    BizHoursEngine --> Orchestrator
    Orchestrator <--> GroqLLM
    Orchestrator --> RuleEngine
    
    Orchestrator --> CakeShopTools
    Orchestrator --> LogisticsTools
    Orchestrator --> CalendarTools
    
    CalendarTools <--> GoogleCalAPI
    Orchestrator --> PrimaryDB
    RuleEngine --> PrimaryDB
    
    Orchestrator --> TTS
    DashboardUI <--> APIGateway
```

---

## 2. Directory Architecture

```text
voice_ai/
├── frontend/                     # Pure React.js (Vite + TypeScript + Tailwind)
│   ├── src/
│   │   ├── components/           # Navbar, Dashboard, WorkflowBuilder, PhoneSimulator, BusinessProfiles, CalendarMonitor
│   │   ├── lib/                  # Frontend API Client (fetch wrapper)
│   │   ├── types/                # Shared TypeScript types (Business, Workflow, MissedCallRecord, CalendarEvent)
│   │   ├── App.tsx               # Main React Application shell
│   │   ├── main.tsx              # React Entry point
│   │   └── index.css             # Glassmorphism Tailwind styling
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   └── tailwind.config.js
│
├── backend/                      # Python FastAPI Backend Server
│   ├── app/
│   │   ├── database.py           # Database connection & seed scripts (SQLite / PostgreSQL)
│   │   ├── models.py             # Pydantic data schemas
│   │   ├── services/             # AI Service, Calendar Service, External API Service, Voice Service
│   │   │   ├── ai_service.py     # Core conversation handler, language switcher, industry tool caller
│   │   │   ├── calendar_service.py # Google Calendar integration
│   │   │   ├── external_api_service.py # Cake Shop & Logistics API tools
│   │   │   └── voice_service.py  # Sarvam AI Bulbul/Saarika, Groq Whisper, ElevenLabs, gTTS
│   │   ├── routers/              # FastAPI REST endpoints (businesses, workflows, records, ai, tools)
│   │   └── main.py               # FastAPI entry point
│   ├── requirements.txt
│   └── data/                     # Local SQLite DB store
│
├── .env                          # Local environment secrets (Groq, Sarvam AI, Google)
├── ARCHITECTURE.md               # Architecture documentation & diagrams
└── README.md                     # Setup & installation guide
```

---

## 3. Sequence Diagram for Tool Calling & Missed Call Processing

```mermaid
sequenceDiagram
    autonumber
    actor Customer as Customer / Caller
    participant PhoneUI as Phone Simulator / Webhook
    participant FastAPIEngine as FastAPI AI Service
    participant LangDetector as Language Router (EN/HI/KN)
    participant ToolCaller as Tool Execution Engine
    participant ExtAPI as External APIs (Logistics / Owner Alert / GCal)
    participant Database as Database (SQLite / Postgres)

    Customer->>PhoneUI: Initiates call or triggers Missed Call Callback
    PhoneUI->>FastAPIEngine: POST /api/ai/chat (business_id, workflow_id, caller details, messages)
    
    FastAPIEngine->>LangDetector: detect_language(last_user_msg)
    LangDetector-->>FastAPIEngine: Detected: 'kn' / 'hi' / 'en' (Flag switch if changed)
    
    FastAPIEngine->>FastAPIEngine: Check Business Operating Hours (e.g., 9:00 AM - 6:00 PM IST)
    
    alt Use Case A: Cake Shop
        FastAPIEngine->>ToolCaller: Parse order type, flavor, weight, required date, custom text, delivery pref, budget
        ToolCaller->>ExtAPI: create_order_enquiry() & send_owner_summary_alert()
        ExtAPI-->>ToolCaller: Enquiry ID (ENQ-XXXX) & Owner Alert Sent
    else Use Case B: Delivery & Logistics
        alt Customer wants New Delivery
            FastAPIEngine->>ToolCaller: Extract pickup, delivery, package type, preferred time
            ToolCaller->>ExtAPI: create_delivery_request()
            ExtAPI-->>ToolCaller: Delivery ID (DEL-XXXX-IN)
        else Customer wants Status Update
            FastAPIEngine->>ToolCaller: Extract tracking number (e.g. TRK-9821-IN)
            ToolCaller->>ExtAPI: track_delivery_status(tracking_no)
            ExtAPI-->>ToolCaller: Status: 'Out for Delivery', driver details
        else Customer needs Help / Callback
            FastAPIEngine->>ToolCaller: Extract issue & contact details
            ToolCaller->>ExtAPI: create_callback_task()
            ExtAPI-->>ToolCaller: Dispatch Task ID (TSK-XXXX-IN)
        end
    else Use Case C: Clinic / Appointments
        ToolCaller->>ExtAPI: check_calendar_availability() & create_calendar_event()
        ExtAPI-->>ToolCaller: Confirmed Slot & Google Event ID
    end

    FastAPIEngine->>FastAPIEngine: Evaluate conditional rules (Delivery < 24h -> URGENT, Emergency -> CRITICAL)
    FastAPIEngine->>Database: INSERT / UPDATE records (transcript, collected_data, tools_executed, urgency)
    FastAPIEngine-->>PhoneUI: Return assistant_reply, executed_tools, urgency, language
    PhoneUI->>Customer: Speak assistant reply via TTS audio in caller's preferred language
```

---

## 4. Database Architecture & Schema

### 4.1 Database Architecture Overview

The **Voice AI Personal Assistant** employs a resilient, hybrid persistence architecture engineered for high availability, low-latency conversational state management, and deployment flexibility across cloud production, local development, and serverless environments.

```mermaid
flowchart TB
    subgraph AppLayer ["FastAPI Application Services"]
        direction TB
        Routers["REST Routers<br/>(/api/businesses, /api/workflows, /api/records)"]
        AiSvc["AI Conversation Service<br/>(Tool execution & State persistence)"]
        CalSvc["Calendar Service<br/>(Booking & Conflict checks)"]
    end

    subgraph DBLayer ["Database Abstraction & Resilience Engine (SQLAlchemy)"]
        direction TB
        ConnHandler["Connection Router: get_db_connection()"]
        PoolMgr["Connection Pool (pool_pre_ping=True)"]
        HealthCheck{"Health Probe<br/>(SELECT 1)"}
        FallbackTrigger["Fallback Interceptor<br/>(Automatic SQLite Failover)"]
    end

    subgraph StorageLayer ["Persistence Storage Targets"]
        direction TB
        PostgreSQL[("Primary Cloud PostgreSQL<br/>Neon / Supabase (pg8000 driver)<br/>Pooled, Persistent, Production")]
        SQLite[("Embedded Fallback SQLite<br/>data/assistant.db or /tmp/assistant.db<br/>Zero-config, Serverless ready")]
    end

    subgraph ExternalSync ["Cloud Data Synchronization"]
        direction TB
        GCalAPI["Google Calendar Cloud API<br/>(External Two-way Event Sync)"]
    end

    Routers --> ConnHandler
    AiSvc --> ConnHandler
    CalSvc --> ConnHandler

    ConnHandler --> PoolMgr
    PoolMgr --> HealthCheck
    HealthCheck -- "Connected (Healthy)" --> PostgreSQL
    HealthCheck -- "Connection Failed / Unreachable" --> FallbackTrigger
    FallbackTrigger --> SQLite

    CalSvc <--> GCalAPI
```

#### Key Architecture Principles

1. **Dual-Engine Hybrid Persistence**:
   - **Production (Cloud PostgreSQL)**: Powered by PostgreSQL (via SQLAlchemy with `pg8000` driver compatible with Neon, Supabase, and Prisma Accelerate connection strings). Employs connection pooling with pre-ping validation (`pool_pre_ping=True`) to automatically reconnect on stale connections.
   - **Local & Serverless Fallback (SQLite)**: Operates out-of-the-box using embedded SQLite stored at `backend/data/assistant.db` (or `/tmp/assistant.db` in AWS Lambda / serverless runtimes). Configured with `check_same_thread=False` to support asynchronous multi-threaded FastAPI request workers.
2. **Zero-Downtime Connection Failover**:
   - The `get_db_connection()` utility executes an active connection probe (`SELECT 1`). If the cloud PostgreSQL instance fails or times out, the engine automatically catches the exception and falls back to the embedded SQLite store, ensuring the voice agent never drops calls due to transient database outages.
3. **Hybrid Relational + Document Model**:
   - High-cardinality core entities (`businesses`, `workflows`, `records`, `calendar_events`) are modeled as relational tables with strict foreign-key relations and standard indexing fields.
   - Variable, schema-less data (such as industry-specific workflow fields, dynamic condition rules, caller-extracted JSON attributes, conversational transcripts, and tool execution logs) are stored as JSON-serialized document columns. This eliminates complex migration overhead when creating new industry templates.
4. **Idempotent Self-Bootstrapping & Seeding**:
   - The schema initializes automatically at startup (`init_db()`), generating required tables if absent and running non-destructive column migrations (e.g., `ALTER TABLE workflows ADD COLUMN business_hours TEXT`).
   - The engine automatically seeds target industry profiles (Sweet Treats Bakery & SwiftMove Express) and default workflows if empty, ensuring instant turnkey deployment.

---

### 4.2 Entity-Relationship (ER) Schema

![Database Schema](docs/images/database-schema.png)

```mermaid
erDiagram
    BUSINESSES ||--o{ WORKFLOWS : "configures"
    BUSINESSES ||--o{ RECORDS : "receives"
    BUSINESSES ||--o{ CALENDAR_EVENTS : "schedules"
    WORKFLOWS ||--o{ RECORDS : "executes"

    BUSINESSES {
        string id PK "e.g. biz-cake-01, biz-logistics-01"
        string name "Business display name"
        string industry "Cake Shop, Logistics & Delivery, Clinic, etc."
        string owner_name "Owner/Manager full name"
        string phone "Business contact phone"
        string email "Business notification email"
        string address "Physical address / branch"
        string created_at "ISO 8601 UTC timestamp"
    }

    WORKFLOWS {
        string id PK "e.g. wf-cake-01, wf-logistics-01"
        string business_id FK "References BUSINESSES.id"
        string name "Workflow title"
        string industry "Industry vertical"
        string trigger_event "e.g. 'Missed Call'"
        text greeting "Initial AI speech greeting"
        text fields "JSON array of WorkflowField definitions"
        text conditions "JSON array of WorkflowCondition rules"
        text actions "JSON array of action tool identifiers"
        text closing_message "Closing message after info collection"
        string language "Default language code ('en', 'hi', 'kn', 'en-hi')"
        text business_hours "JSON object of operating schedule & after-hours rules"
        int is_active "1 = active, 0 = inactive"
        string created_at "ISO 8601 UTC timestamp"
    }

    RECORDS {
        string id PK "e.g. rec-cake-01, rec-xxxx"
        string business_id FK "References BUSINESSES.id"
        string workflow_id FK "References WORKFLOWS.id"
        string caller_name "Caller name"
        string caller_phone "Caller phone number (+91...)"
        string intent "Classified customer intent"
        text collected_data "JSON object with extracted structured fields"
        text ai_summary "Concise AI-generated summary"
        string urgency "Normal | Urgent | Critical"
        string followup_status "Pending | Contacted | Completed | Closed"
        text transcript "JSON array of conversation messages"
        text tools_executed "JSON array of tool invocation logs"
        string created_at "ISO 8601 UTC timestamp"
    }

    CALENDAR_EVENTS {
        string id PK "e.g. cal-seed-01, evt-xxxx"
        string business_id FK "References BUSINESSES.id"
        string title "Event title"
        string start_time "ISO 8601 start timestamp"
        string end_time "ISO 8601 end timestamp"
        string attendee_name "Customer attendee name"
        string attendee_phone "Customer phone number"
        text description "Notes / booking source"
        string status "Confirmed | Rescheduled | Cancelled"
        string google_event_id "Google Calendar Event ID if synced"
        string created_at "ISO 8601 UTC timestamp"
    }
```

---

### 4.3 Detailed Table Specifications & Data Dictionary

#### 1. `businesses` Table
Represents multi-tenant business profiles registered within the system.

| Column | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `VARCHAR(64)` | PRIMARY KEY | Unique business identifier (e.g., `biz-cake-01`, `biz-logistics-01`) |
| `name` | `VARCHAR(255)` | NOT NULL | Registered trading name displayed across dashboards |
| `industry` | `VARCHAR(128)` | NOT NULL | Vertical classification (e.g., `Cake Shop`, `Logistics & Delivery`) |
| `owner_name` | `VARCHAR(255)` | NOT NULL | Primary point of contact / business owner name |
| `phone` | `VARCHAR(64)` | NOT NULL | Contact phone number for SMS/voice alerts |
| `email` | `VARCHAR(255)` | NOT NULL | Notification dispatch email |
| `address` | `TEXT` | NULLABLE | Physical branch or dispatch center address |
| `created_at` | `VARCHAR(64)` | NOT NULL | ISO 8601 timestamp of record creation |

#### 2. `workflows` Table
Configures the behavioral rules, dynamic speech greetings, form fields, and conditional actions executed by the AI engine.

| Column | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `VARCHAR(64)` | PRIMARY KEY | Unique workflow identifier (e.g., `wf-cake-01`) |
| `business_id` | `VARCHAR(64)` | NOT NULL, FK | References `businesses(id)` |
| `name` | `VARCHAR(255)` | NOT NULL | Descriptive title of the workflow |
| `industry` | `VARCHAR(128)` | NOT NULL | Target industry vertical |
| `trigger_event`| `VARCHAR(128)` | NOT NULL | Activation event (e.g., `Missed Call`, `Inbound Call`) |
| `greeting` | `TEXT` | NOT NULL | Initial opening line synthesized by TTS |
| `fields` | `TEXT (JSON)` | NOT NULL | Serialized JSON array of required/optional data fields (`WorkflowField[]`) |
| `conditions` | `TEXT (JSON)` | NOT NULL | Serialized JSON array of evaluation logic rules (`WorkflowCondition[]`) |
| `actions` | `TEXT (JSON)` | NOT NULL | Serialized JSON array of tool execution IDs to trigger |
| `closing_message`| `TEXT` | NOT NULL | Wrap-up speech prompt spoken when data collection finishes |
| `language` | `VARCHAR(32)` | DEFAULT `'en-hi'` | Primary default language code (`en`, `hi`, `kn`, `en-hi`) |
| `business_hours`| `TEXT (JSON)` | NULLABLE | Operating schedule, timezone, and out-of-hours response strategy |
| `is_active` | `INT` | DEFAULT `1` | Boolean flag (1 = Active, 0 = Disabled) |
| `created_at` | `VARCHAR(64)` | NOT NULL | ISO 8601 timestamp of record creation |

#### 3. `records` Table
Stores call interaction audit logs, AI-extracted form values, urgency ratings, and tool telemetry.

| Column | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `VARCHAR(64)` | PRIMARY KEY | Unique interaction ID (e.g., `rec-cake-01`, `rec-xxxx`) |
| `business_id` | `VARCHAR(64)` | NOT NULL, FK | References `businesses(id)` |
| `workflow_id` | `VARCHAR(64)` | NOT NULL, FK | References `workflows(id)` |
| `caller_name` | `VARCHAR(255)` | NOT NULL | Extracted caller identity or default `"Customer"` |
| `caller_phone` | `VARCHAR(64)` | NOT NULL | Customer caller phone number (+91 E.164 format) |
| `intent` | `VARCHAR(255)` | NOT NULL | Classified customer intent |
| `collected_data`| `TEXT (JSON)` | NOT NULL | Structured key-value object containing extracted entities |
| `ai_summary` | `TEXT` | NOT NULL | Concise LLM-generated call abstract |
| `urgency` | `VARCHAR(32)` | DEFAULT `'Normal'`| Priority classification: `Normal`, `Urgent`, or `Critical` |
| `followup_status`| `VARCHAR(32)`| DEFAULT `'Pending'`| Workflow state: `Pending`, `Contacted`, `Completed`, `Closed` |
| `transcript` | `TEXT (JSON)` | NOT NULL | Complete dialogue history array (`[{role, content}]`) |
| `tools_executed`| `TEXT (JSON)` | NOT NULL | Array of triggered tool records and execution payloads |
| `created_at` | `VARCHAR(64)` | NOT NULL | ISO 8601 timestamp of interaction |

#### 4. `calendar_events` Table
Manages slot reservations, delivery appointments, and two-way Google Calendar synchronization.

| Column | Data Type | Constraints | Description |
| :--- | :--- | :--- | :--- |
| `id` | `VARCHAR(64)` | PRIMARY KEY | Unique calendar booking identifier |
| `business_id` | `VARCHAR(64)` | NOT NULL, FK | References `businesses(id)` |
| `title` | `VARCHAR(255)` | NOT NULL | Event title / summary header |
| `start_time` | `VARCHAR(64)` | NOT NULL | ISO 8601 start timestamp |
| `end_time` | `VARCHAR(64)` | NOT NULL | ISO 8601 end timestamp |
| `attendee_name`| `VARCHAR(255)` | NOT NULL | Customer / booking attendee full name |
| `attendee_phone`| `VARCHAR(64)` | NOT NULL | Contact phone number for reminders |
| `description` | `TEXT` | NULLABLE | Metadata, internal notes, and booking origins |
| `status` | `VARCHAR(32)` | DEFAULT `'Confirmed'`| Lifecycle status: `Confirmed`, `Rescheduled`, `Cancelled` |
| `google_event_id`| `VARCHAR(128)`| NULLABLE | External Google Calendar identifier for two-way synchronization |
| `created_at` | `VARCHAR(64)` | NOT NULL | ISO 8601 timestamp of reservation |

---

### 4.4 Data Access Patterns & Security

1. **Parameterized Query Execution**:
   - All database queries utilize SQLAlchemy's `text()` wrapper with strict parameter binding (e.g. `:bid`, `:status`, `:id`) across all routers. This protects against SQL injection attacks across dynamic search filters and status patch operations.
2. **Read-Heavy Query Optimization**:
   - Dashboard endpoints (such as `GET /api/records`) perform optimized join queries:
     ```sql
     SELECT r.*, b.name as business_name, w.name as workflow_name
     FROM records r
     JOIN businesses b ON r.business_id = b.id
     JOIN workflows w ON r.workflow_id = w.id
     WHERE 1=1 AND r.business_id = :bid
     ORDER BY r.created_at DESC;
     ```
3. **Transaction Management & Thread Safety**:
   - Connection transactions are managed through Python context managers (`with get_db_connection() as conn:`), guaranteeing safe session commits and automatic connection return to the pool.
   - For SQLite fallback mode, connection threading checks are disabled (`check_same_thread=False`) to avoid SQLite worker affinity lockouts during concurrent async FastAPI calls.

---

## 5. Workflow Data Model

Every workflow is dynamic and defined by three core data structures:

### A. `WorkflowField` Data Model
```typescript
interface WorkflowField {
  key: string;          // Normalized JSON property key (e.g. "cake_flavor", "pickup_location")
  label: string;        // Human-readable label (e.g. "Cake Flavor", "Pickup Location")
  type: 'text' | 'select' | 'number' | 'datetime';
  options?: string[];   // Dropdown choices (e.g. ["Documents", "Electronics", "Parcels"])
  required: boolean;    // Whether the field is mandatory
  description?: string; // AI extraction hint (e.g. "e.g. Belgian Dark Chocolate")
}
```

### B. `WorkflowCondition` Data Model
```typescript
interface WorkflowCondition {
  field: string;               // Field evaluated (e.g. "required_date", "service_option")
  operator: 'equals' | 'within_hours' | 'exists';
  value?: any;                 // Comparative value (e.g. 24, "New Delivery Request")
  action_override?: string;    // Override behavior (e.g. "mark_urgent", "flag_critical")
  tool_action?: string;        // Automated tool triggered (e.g. "create_delivery_request")
  note?: string;               // Audit trail description
}
```

### C. `BusinessHours` Data Model
```typescript
interface BusinessHours {
  enabled: boolean;            // Whether schedule enforcement is active
  days: string[];              // Operating days (e.g. ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"])
  start_time: string;          // "09:00"
  end_time: string;            // "18:00"
  after_hours_greeting?: string; // Message played outside operating hours
  after_hours_action?: string; // "flag_after_hours"
}
```

---

## 6. Schema-Driven Dynamic Slot-Filling & Multi-Turn State Persistence

To provide completely conversational, form-filling capabilities without robotic rigidity, the system implements dynamic schema-driven slot filling:

```mermaid
sequenceDiagram
    autonumber
    actor Caller as 📞 Caller (Voice / Speech)
    participant Client as 💻 Phone Simulator (React)
    participant API as 🚀 FastAPI (/api/ai/chat)
    participant Engine as 🧠 AiService (Slot-Filling Engine)
    participant Groq as ⚡ Groq LPU (GPT-OSS-120B)
    participant DB as 🗄️ SQLite / PostgreSQL (records)
    participant Tools as 🛠️ Domain Tools (External APIs)

    Caller->>Client: "I want to order a birthday cake"
    Client->>API: POST /api/ai/chat (record_id=null)
    API->>Engine: process_conversation(request_data)
    Engine->>Groq: Extract fields matching workflow['fields']
    Groq-->>Engine: {"order_type": "New Cake Order"}
    Engine->>DB: INSERT INTO records (collected_data={"order_type": "..."})
    Engine->>Engine: Evaluate missing required fields: [cake_flavor, weight_kg, required_date, delivery_pref]
    Engine->>Groq: Generate conversational question for next 1-2 missing fields
    Groq-->>Engine: "Sure! What flavor of cake would you like, and how many kilograms?"
    Engine-->>Client: Return reply, record_id: "rec-xxx", collected_data
    Client-->>Caller: Speaks AI question via Sarvam AI TTS (continuous mic stays active)

    Caller->>Client: "Dark chocolate, 2 kg"
    Client->>API: POST /api/ai/chat (record_id="rec-xxx")
    API->>Engine: process_conversation(record_id="rec-xxx")
    Engine->>DB: SELECT collected_data WHERE id="rec-xxx"
    Engine->>Groq: Extract new fields from utterance
    Groq-->>Engine: {"cake_flavor": "Dark chocolate", "weight_kg": 2}
    Engine->>DB: UPDATE records (collected_data merged)
    Engine->>Engine: Missing: [required_date, delivery_pref]
    Engine-->>Client: "A 2 kg dark chocolate cake sounds delicious! When do you need it by, and home delivery or pickup?"

    Caller->>Client: "Tomorrow 6 PM, home delivery please"
    Client->>API: POST /api/ai/chat (record_id="rec-xxx")
    Engine->>Groq: Extract {"required_date": "...", "delivery_pref": "Home Delivery"}
    Engine->>DB: UPDATE records (all required fields now complete!)
    Engine->>Engine: All required fields satisfied -> Trigger completion tools!
    Engine->>Tools: execute create_order_enquiry & send_owner_summary_alert
    Tools-->>Engine: Enquiry ID ENQ-xxxx created, owner alert dispatched
    Engine->>DB: UPDATE records (status="Completed", tools_executed=[...])
    Engine-->>Client: Confirm order details + workflow['closing_message']
    Client-->>Caller: Speaks final confirmation with human-like voice
```

### Key Architectural Highlights:
1. **Schema-Driven (Zero Hardcoding)**:
   - Fields are loaded directly from `workflows.fields` in SQLite.
   - Any new workflow created via the Workflow Builder automatically gains progressive slot-filling.
2. **Multi-Turn Session Continuity**:
   - `record_id` is maintained across conversational turns.
   - Each turn updates the existing database record with merged slot data in `records.collected_data`.
3. **Multilingual Entity Extraction**:
   - Groq LPUs (`openai/gpt-oss-120b`) extract entities directly from English, Hindi, Hinglish, and Kannada speech.
   - Dual-layer extraction: LLM JSON mode extraction is backed by heuristic regex extractors for date/time, weights, flavors, waybill numbers, and locations.
4. **Completion Tool Gating**:
   - Business actions (`create_order_enquiry`, `track_delivery_status`, `create_calendar_event`) are held until all required fields are provided.
5. **Real-Time UI Tracker**:
   - Phone Simulator features a live "Database Fields" status card showing captured fields, pending questions, and live percentage progress.


