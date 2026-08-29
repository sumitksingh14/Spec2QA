"""
Vercel Python serverless entry point for Spec2QA.

Imports are guarded so that startup errors are surfaced as readable JSON
rather than opaque FUNCTION_INVOCATION_FAILED responses.
"""

import sys
import os
import json
import traceback

# Make backend/ importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

_STARTUP_ERROR = None

try:
    from main import app  # noqa: F401
    from mangum import Mangum

    handler = Mangum(app, lifespan="off")

except Exception as _exc:
    _STARTUP_ERROR = {
        "error": str(_exc),
        "traceback": traceback.format_exc(),
        "python": sys.version,
        "path": sys.path,
        "cwd": os.getcwd(),
        "files": os.listdir(os.path.dirname(__file__)),
        "backend_files": (
            os.listdir(os.path.join(os.path.dirname(__file__), '..', 'backend'))
            if os.path.isdir(os.path.join(os.path.dirname(__file__), '..', 'backend'))
            else "backend/ not found"
        ),
    }

    # Pure-stdlib WSGI/ASGI fallback — no fastapi/mangum needed
    async def handler(scope, receive, send):  # type: ignore[misc]
        if scope["type"] == "http":
            body = json.dumps(_STARTUP_ERROR, indent=2).encode()
            await send({
                "type": "http.response.start",
                "status": 500,
                "headers": [
                    [b"content-type", b"application/json"],
                    [b"content-length", str(len(body)).encode()],
                ],
            })
            await send({"type": "http.response.body", "body": body})
