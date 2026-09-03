import os
import sys

# Add current directory, root directory, and backend directory to sys.path
api_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(api_dir)
backend_dir = os.path.join(root_dir, "backend")

for path in [backend_dir, root_dir, api_dir]:
    if path and path not in sys.path:
        sys.path.insert(0, path)

try:
    from app.main import app
except Exception:
    try:
        from backend.app.main import app
    except Exception as e:
        raise RuntimeError(f"Failed to import FastAPI app in Vercel function: {e}")

handler = app

