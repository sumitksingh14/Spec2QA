"""
Vercel Python serverless entry point for Spec2QA.

When using `builds` in vercel.json, @vercel/python requires a top-level
callable named `app`, `application`, or `handler`.  We expose `app`.
"""
from __future__ import annotations  # enables dict | None on Python 3.9

import sys
import os
import json
import traceback

# Make backend/ importable at runtime (Vercel bundles backend/** via includeFiles)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

_startup_error: dict | None = None

try:
    from main import app as _fastapi_app   # type: ignore[import]  # resolved via sys.path at runtime
    from mangum import Mangum

    # `app` is the top-level name @vercel/python will discover and invoke.
    app = Mangum(_fastapi_app, lifespan="off")

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

    # Fallback: a bare ASGI app that returns the startup error as JSON.
    async def app(scope, receive, send):  # type: ignore[misc]  # noqa: E302
        """Minimal ASGI fallback when the real app fails to import."""
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
