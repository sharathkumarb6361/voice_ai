import os
import sys

# Ensure backend directory is in sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
try:
    from app.database import init_db
    from app.routers import businesses, workflows, records, ai, tools, webhooks
except ImportError:
    from backend.app.database import init_db
    from backend.app.routers import businesses, workflows, records, ai, tools, webhooks

app = FastAPI(
    title="Voice AI Personal Assistant Backend API",
    description="Python FastAPI backend powering Missed Call Workflows, Google Calendar Tool Calling, and Multi-Language Voice Assistant.",
    version="1.0.0"
)

# Enable CORS for React Frontend (Vite port 3000 / 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize SQLite Database & Seeds
init_db()

# Register Routers
app.include_router(businesses.router)
app.include_router(workflows.router)
app.include_router(records.router)
app.include_router(ai.router)
app.include_router(tools.router)
app.include_router(webhooks.router)

@app.get("/")
@app.get("/api")
@app.get("/health")
@app.get("/api/health")
def health_check():
    return {
        "status": "online",
        "system": "Python FastAPI Voice AI Backend",
        "version": "1.0.0"
    }

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    print(f"====================================================")
    print(f" Python FastAPI Backend Server Starting on Port {port}")
    print(f" API Docs: http://localhost:{port}/docs           ")
    print(f"====================================================")
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
