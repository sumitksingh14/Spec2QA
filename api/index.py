import sys
import os

# Ensure backend directory is in Python path for Vercel Serverless Function execution
_backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend')
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from main import app as app
