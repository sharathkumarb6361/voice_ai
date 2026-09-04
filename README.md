# Voice AI Personal Assistant (Python FastAPI & Pure React.js)

An end-to-end multi-tenant, multi-industry AI Voice Assistant and Workflow Automation web application for small business owners (Cake Shops, Clinics, Logistics, Real Estate, Home Repair, and Custom Businesses).

Architected with a **Python FastAPI** backend server and a **Pure React.js (Vite + TypeScript + Tailwind CSS)** frontend application.

---

## 🌟 Tech Stack

- **Backend**: Python 3.10+, **FastAPI**, `uvicorn`, SQLite DB (`data/assistant.db`), `pydantic`, `gTTS` voice engine, Google Calendar API tools.
- **Frontend**: **Pure React.js** (Vite + React 18 + TypeScript + Tailwind CSS), Lucide Icons, Glassmorphism UI design.

---

## 🌟 Key Features

### 1. Multi-Industry Support (5 Pre-Configured Use Cases)
- 🍰 **Cake Shop ("Sweet Treats Bakery")**: Collects cake flavor, weight, date/time, custom message, delivery preference, budget. Evaluates 24-hour delivery rule to set **URGENT** priority.
- 🏥 **Clinic / Doctor ("Apex Health Clinic")**: Manages appointment bookings, rescheduling, and doctor availability using **Google Calendar Tool Calling** (`check_calendar_availability` & `create_calendar_event`). Strictly avoids medical advice.
- 🚚 **Logistics & Delivery ("SwiftMove Express")**: Real-time package tracking using **External REST API Tool Calling** (`track_delivery_status` for waybill `#TRK-9821-IN`).
- 🏡 **Real Estate ("Prime Haven Realty")**: Qualifies leads, collects budget/location, schedules property site visits on Google Calendar.
- 🔧 **Home & Repair Services ("FixIt Pro Maintenance")**: Captures emergency repair requests and flags *Immediate Emergency* as **CRITICAL** priority.

### 2. Custom Workflow Builder
- Form & step-by-step visual workflow editor.
- Configure: Workflow Name, Industry, Trigger (Missed Call), Opening Voice Greeting, Form Fields (Required vs Optional), Conditional Rules, Post-collection Actions, and Closing Messages.

### 3. AI Tool Calling & Google Calendar Integration
- **Google Calendar Tools**:
  - `check_calendar_availability`: Checks slot conflicts before booking.
  - `create_calendar_event`: Schedules confirmed Google Calendar events.
  - `update_calendar_event`: Reschedules existing entries.
  - `cancel_calendar_event`: Cancels or frees calendar slots.
- **External REST API Tools (Bonus)**:
  - `track_delivery_status`: Calls live logistics REST endpoint.
  - `lookup_crm_customer`: Queries customer CRM profile by phone number.

### 4. Multi-Language Support (English & Hindi)
- Speech-to-text input recording, Text-to-speech audio synthesis playback in **English** and **Hindi / Hinglish**.
- Dynamic auto-detection switching between languages mid-conversation.

### 5. Management Dashboard & Customer Records
- View caller name, phone number, business used, date & time, customer intent, collected data fields, AI summary, priority badge (Normal / Urgent / Critical), and transcript.
- Update follow-up status: **Pending**, **Owner Contacted**, **Completed**, **Closed**.

---

## 📁 Folder Structure

```text
voice_ai/
├── frontend/                     # Pure React.js Web Application (Vite)
│   ├── src/
│   │   ├── components/           # Navbar, Dashboard, WorkflowBuilder, PhoneSimulator, BusinessProfiles, CalendarMonitor
│   │   ├── lib/                  # Frontend API client
│   │   ├── types/                # TypeScript interfaces
│   │   ├── App.tsx               # Main React Application
│   │   ├── main.tsx              # React entry point
│   │   └── index.css             # Glassmorphism Tailwind styling
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   └── tailwind.config.js
│
├── backend/                      # Python FastAPI Server
│   ├── app/
│   │   ├── database.py           # SQLite schema & seed scripts
│   │   ├── models.py             # Pydantic data schemas
│   │   ├── services/             # AI, Google Calendar, External REST API, Voice services
│   │   ├── routers/              # FastAPI router endpoints
│   │   └── main.py               # FastAPI entry point
│   ├── requirements.txt
│   └── data/                     # SQLite database file directory
│
├── .env.example                  # Environment variable configuration template
├── ARCHITECTURE.md               # Architecture documentation & diagrams
└── README.md                     # Project documentation
```

---

## 🚀 Quick Setup Instructions

### Prerequisites
- Python 3.10+ and Node.js v18+ installed on your system.

### 1. Install Backend Dependencies & Run FastAPI Server
```bash
cd backend
pip install -r requirements.txt
python -m app.main
```
The Python FastAPI server will start at `http://localhost:8000`. API documentation available at `http://localhost:8000/docs`!

### 2. Install Frontend Dependencies & Start React App
Open a new terminal window:
```bash
cd frontend
npm install
npm run dev
```
The Pure React web application will run at `http://localhost:3000`.

---

## ⚙️ Environment Variables Template (`.env.example`)

To enable live Google Calendar API sync or OpenAI/Gemini models, create a `.env` file inside `backend/`:

```env
PORT=8000

# Optional: AI Model Keys
OPENAI_API_KEY=
GEMINI_API_KEY=

# Google Calendar API Integration
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REFRESH_TOKEN=
GOOGLE_CALENDAR_ID=primary
```

---

## 🌐 Deploying to Render

This repository is pre-configured for 1-click or step-by-step deployment on **Render**.

### Method 1: Render Blueprint (Recommended - Automated 1-Click Setup)
1. Push this repository to GitHub / GitLab.
2. Log in to [Render Dashboard](https://dashboard.render.com).
3. Click **New +** -> **Blueprint**.
4. Connect your GitHub repository. Render will automatically detect [`render.yaml`](file:///d:/voice_ai/render.yaml) and configure the Web Service with build & start commands!
5. Fill in optional Environment Variables (`GEMINI_API_KEY`, `OPENAI_API_KEY`, etc.) and click **Apply**.

### Method 2: Manual Web Service Setup on Render
1. Log in to [Render Dashboard](https://dashboard.render.com).
2. Click **New +** -> **Web Service**.
3. Connect your repository.
4. Set the following settings:
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt && cd frontend && npm install && npm run build`
   - **Start Command**: `uvicorn backend.app.main:app --host 0.0.0.0 --port $PORT`
5. Add Environment Variables in Render Dashboard (`GEMINI_API_KEY`, `OPENAI_API_KEY`, etc.).
6. Click **Deploy Web Service**. Render will host both your FastAPI backend and built React frontend on a live `https://<your-app>.onrender.com` URL!
