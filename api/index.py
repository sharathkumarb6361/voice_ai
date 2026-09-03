import os
import sys

# Add backend directory to python path for Vercel Serverless Function
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.main import app

# Export app for Vercel Serverless Function
