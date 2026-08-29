import sys
import os
import traceback

# Add the backend directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'backend'))

try:
    from main import app  # type: ignore[import-not-found]
    from mangum import Mangum
    handler = Mangum(app, lifespan="off")
except Exception as exc:
    # Surface the real import error as a 500 JSON response so it shows in logs
    _tb = traceback.format_exc()

    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    _err_app = FastAPI()

    @_err_app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def _error_handler(path: str):
        return JSONResponse(
            status_code=500,
            content={"startup_error": str(exc), "traceback": _tb},
        )

    from mangum import Mangum
    handler = Mangum(_err_app, lifespan="off")
