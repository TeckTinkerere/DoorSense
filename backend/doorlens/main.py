"""One local process serves the frozen inference API and exported Next frontend."""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from doorlens.api.routes import router
from doorlens.inference import InputError
from doorlens.services.analysis import AnalysisService
from doorlens.services.settings import Settings
from doorlens.services.store import AnalysisStore


def create_app(settings: Settings | None = None, store: AnalysisStore | None = None,
               models: dict | None = None) -> FastAPI:
    settings = settings if settings is not None else Settings.from_env()
    store = store if store is not None else AnalysisStore(settings.max_analyses, settings.analysis_ttl_seconds)
    app = FastAPI(title="DoorLens", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.analysis_store = store
    app.state.analysis_service = AnalysisService(settings, store, models)
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.dev_origins),
                       allow_methods=["GET", "POST", "DELETE"], allow_headers=["Content-Type"])

    @app.middleware("http")
    async def local_headers(request: Request, call_next):
        response = await call_next(request)
        if request.url.path == "/api" or request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(InputError)
    async def invalid_input(request: Request, exc: InputError):
        return JSONResponse(status_code=422, content={"detail": {"code": exc.code, "message": exc.message}})

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        return JSONResponse(status_code=422, content={"detail": {
            "code": "invalid_request", "message": "The request is incomplete or has an unsupported value. Check the selected file, cycle, or probe."}})

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) and {"code", "message"} <= exc.detail.keys() else {
            "code": "not_found" if exc.status_code == 404 else "request_error", "message": str(exc.detail)}
        return JSONResponse(status_code=exc.status_code, content={"detail": detail}, headers=exc.headers)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logging.getLogger("doorlens").error("Request failed: %s", type(exc).__name__)
        return JSONResponse(status_code=500, content={"detail": {
            "code": "internal_error", "message": "The analysis could not be completed. Check the local server setup and bundled model artifacts."}})

    app.include_router(router)

    # Guard the whole API namespace before the frontend mount, for every method.
    @app.api_route("/api", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE", "CONNECT"])
    @app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE", "CONNECT"])
    async def unknown_api(path: str = ""):
        return JSONResponse(status_code=404, content={"detail": {
            "code": "api_not_found", "message": "This API endpoint does not exist."}})

    if settings.frontend_directory.is_dir():
        app.mount("/", StaticFiles(directory=str(settings.frontend_directory), html=True), name="frontend")
    return app


app = create_app()
