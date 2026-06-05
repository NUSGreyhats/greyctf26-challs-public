from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.bootstrap import bootstrap_schema
from app.core.config import settings
from app.core.exceptions import AppError
from app.observability.http import instrument_fastapi_app
from app.web import configure_spa

app = FastAPI(
    title=settings.app_name,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
instrument_fastapi_app(app)
app.include_router(api_router)
configure_spa(app, settings.app_static_dir)

@app.on_event("startup")
def on_startup() -> None:
    bootstrap_schema()

@app.exception_handler(AppError)
def handle_app_error(_request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.error, "message": exc.message},
    )
