import os
import sys

# Ensure all directory levels are in sys.path for serverless runtimes
current_file = os.path.abspath(__file__)
app_dir = os.path.dirname(current_file)
backend_dir = os.path.dirname(app_dir)
root_dir = os.path.dirname(backend_dir)

for p in [backend_dir, app_dir, root_dir]:
    if p and p not in sys.path:
        sys.path.insert(0, p)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn

try:
    from app.database import init_db
    from app.routers import businesses, workflows, records, ai, tools, webhooks
except Exception:
    from backend.app.database import init_db
    from backend.app.routers import businesses, workflows, records, ai, tools, webhooks

app = FastAPI(
    title="Voice AI Personal Assistant Backend API",
    description="Python FastAPI backend powering Missed Call Workflows, Google Calendar Tool Calling, and Multi-Language Voice Assistant.",
    version="1.0.0"
)

# Enable CORS for React Frontend (Vite port 3000 / 5173 or custom domain)
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

@app.get("/health")
@app.get("/api/health")
def health_check():
    return {
        "status": "online",
        "system": "Python FastAPI Voice AI Backend",
        "version": "1.0.0"
    }

# Serve Frontend static files if frontend/dist exists (Production deployment on Render)
frontend_dist = os.path.join(root_dir, "frontend", "dist")
if os.path.exists(frontend_dist):
    assets_dir = os.path.join(frontend_dist, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def serve_react_app(full_path: str):
        if full_path.startswith("api"):
            return {"detail": "Not Found"}
        file_path = os.path.join(frontend_dist, full_path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_dist, "index.html"))
else:
    @app.get("/")
    @app.get("/api")
    def root_info():
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
