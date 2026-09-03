import os
import sys

# Add current, root, and backend directories to Python path for Vercel Serverless Function
api_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(api_dir)
backend_dir = os.path.join(root_dir, "backend")

for path in [backend_dir, root_dir, api_dir]:
    if path not in sys.path:
        sys.path.insert(0, path)

from app.main import app

# Export handler for Vercel Serverless Functions
handler = app


# Export app for Vercel Serverless Function
