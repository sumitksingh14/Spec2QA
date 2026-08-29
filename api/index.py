"""
Vercel Python serverless entry point for Spec2QA.

`handler` MUST be a top-level name so @vercel/python can find it.
We import lazily inside the function so startup errors surface as JSON.
"""

import sys
import os
import json
import traceback

# Make backend/ importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

# Try to build the real Mangum handler at module load
_startup_error: dict | None = None
_mangum_handler = None

try:
    from main import app          # noqa: F401  (resolved via sys.path above)
    from mangum import Mangum
    _mangum_handler = Mangum(app, lifespan="off")
except Exception as _exc:
    _startup_error = {
        "startup_error": str(_exc),
        "traceback": traceback.format_exc(),
        "python": sys.version,
        "sys_path": sys.path,
        "api_dir": os.listdir(os.path.dirname(os.path.abspath(__file__))),
        "backend_exists": os.path.isdir(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend')
        ),
    }


# Top-level `handler` — always present so @vercel/python can find it
async def handler(scope, receive, send):
    """ASGI entry point called by Vercel for every request."""
    if _mangum_handler is not None:
        # Happy path — delegate to real Mangum/FastAPI handler
        await _mangum_handler(scope, receive, send)
        return

    # Startup failed — return the full diagnostic JSON
    if scope["type"] == "http":
        body = json.dumps(_startup_error, indent=2).encode()
        await send({
            "type": "http.response.start",
            "status": 500,
            "headers": [
                [b"content-type", b"application/json"],
                [b"content-length", str(len(body)).encode()],
            ],
        })
        await send({"type": "http.response.body", "body": body})
