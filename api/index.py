"""
Vercel Python serverless entry point for Spec2QA.

The modern Vercel Python runtime (using `functions` in vercel.json) discovers
a top-level ASGI callable named `app`, `application`, or `handler`.
We expose `app` unconditionally so static analysis always finds it.
"""

import sys
import os
import json
import traceback

# ---------------------------------------------------------------------------
# Make backend/ importable at runtime.
# Vercel bundles backend/** into the function package via includeFiles.
# ---------------------------------------------------------------------------
_backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'backend')
sys.path.insert(0, _backend_dir)

# ---------------------------------------------------------------------------
# Build the real ASGI app (Mangum-wrapped FastAPI).
# Any import/startup errors are captured and returned as a JSON 500.
# ---------------------------------------------------------------------------
_startup_error: dict | None = None
_real_app = None

try:
    from main import app as _fastapi_app   # type: ignore[import]
    from mangum import Mangum
    _real_app = Mangum(_fastapi_app, lifespan="off")
except Exception as _exc:
    _startup_error = {
        "startup_error": str(_exc),
        "traceback": traceback.format_exc(),
        "python": sys.version,
        "sys_path": sys.path,
        "backend_dir": _backend_dir,
        "backend_exists": os.path.isdir(_backend_dir),
        "backend_files": os.listdir(_backend_dir) if os.path.isdir(_backend_dir) else [],
    }


async def app(scope, receive, send):
    """Top-level ASGI entry point — always present, always at module level."""
    if _real_app is not None:
        await _real_app(scope, receive, send)  # type: ignore[misc]
        return

    # Startup failed — return structured JSON error for diagnosis.
    if scope["type"] != "http":
        return

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
