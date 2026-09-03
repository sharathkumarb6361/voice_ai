# System Architecture Blueprint - Python FastAPI & Pure React.js

This document details the decoupled architecture, tool calling execution engine, multi-language voice engine, and database models for the **Voice AI Personal Assistant**.

---

## 1. System Component Diagram

```mermaid
graph TD
    User([Customer / Missed Call]) -->|Simulated Phone Call| Simulator[AI Phone Call Simulator]
    Owner([Small Business Owner]) -->|Manages Workflows & Records| DashboardUI[Dashboard & Builder UI]

    subgraph Frontend [Pure React.js + Vite Application]
        DashboardUI --> APIClient[React API Client]
        Simulator --> AudioRecorder[Web Audio Recorder / Player]
        AudioRecorder --> APIClient
    end

    subgraph Backend [Python FastAPI Server]
        APIClient --> FastAPIRoutes[FastAPI Router Gateway]
        FastAPIRoutes --> AIService[AI Engine & Tool Calling Orchestrator]
        FastAPIRoutes --> VoiceService[STT / TTS Voice Synthesis Service]
        FastAPIRoutes --> WorkflowEngine[Conditional Rule Evaluator]
        
        AIService --> GCalService[Google Calendar Tool Integration]
        AIService --> RESTTools[External REST APIs - CRM & Delivery]
        
        AIService --> DB[(SQLite Database Store)]
        WorkflowEngine --> DB
    end

    subgraph ExternalIntegrations [External Services]
        GCalService -->|Google API Client| GoogleCalAPI[Google Calendar API]
        RESTTools -->|HTTPX REST| ExternalAPIs[Logistics / CRM REST APIs]
    end
```

---

## 2. Directory Architecture

```text
voice_ai/
├── frontend/                     # Pure React.js (Vite + TS + Tailwind)
│   ├── src/
│   │   ├── components/           # Navbar, Dashboard, WorkflowBuilder, PhoneSimulator, BusinessProfiles, CalendarMonitor
│   │   ├── lib/                  # Frontend API Client
│   │   ├── types/                # Shared TypeScript types
│   │   ├── App.tsx               # Main React Component
│   │   ├── main.tsx              # React Entry point
│   │   └── index.css             # Glassmorphism Tailwind CSS
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   └── tailwind.config.js
│
├── backend/                      # Python FastAPI Backend Server
│   ├── app/
│   │   ├── database.py           # SQLite connection & seed scripts
│   │   ├── models.py             # Pydantic schemas
│   │   ├── services/             # AI, Google Calendar, External REST API, Voice services
│   │   ├── routers/              # FastAPI endpoints (businesses, workflows, records, ai, tools)
│   │   └── main.py               # FastAPI entry point
│   ├── requirements.txt
│   └── data/                     # SQLite database file directory
│
├── .env.example                  # Environment variables template
├── ARCHITECTURE.md               # Architecture documentation
└── README.md                     # Setup instructions
```

---

## 3. Sequence Diagram for Tool Calling

```mermaid
sequenceDiagram
    autonumber
    actor Customer as Customer / Caller
    participant Simulator as React Phone Simulator UI
    participant Backend as Python FastAPI Backend
    participant GCal as Google Calendar API
    participant ExtAPI as External REST API
    participant DB as SQLite DB

    Customer->>Simulator: Speaks/Types request ("Book doctor appointment for tomorrow at 4 PM")
    Simulator->>Backend: POST /api/ai/chat (Messages, Business, Workflow)
    Backend->>Backend: Analyze intent & inspect tool registry
    
    alt Google Calendar Appointment Request
        Backend->>GCal: check_calendar_availability(date, time)
        GCal-->>Backend: Slot available
        Backend->>GCal: create_calendar_event(title, start_time, attendee)
        GCal-->>Backend: Google Event ID #gcal_py_cal_9912
    else Parcel Tracking Request
        Backend->>ExtAPI: GET /api/tools/delivery/track/TRK-9821-IN
        ExtAPI-->>Backend: { status: 'Out for Delivery', driver: 'Rohan' }
    end

    Backend->>Backend: Evaluate conditional rules (e.g. required < 24h -> URGENT)
    Backend->>DB: Save customer record & update transcript/tools log
    Backend-->>Simulator: Returns AI response + Executed Tools Payload
    Simulator->>Customer: Plays synthesized TTS Audio in English/Hindi
```
