"""FastAPI application factory.

Run with ``uv run inventura serve`` (or ``uvicorn --factory inventura.web.app:create_app``).
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from inventura.core.counting import CountError, DocumentClosedError
from inventura.db.session import make_engine, make_session_factory
from inventura.io.column_mapping import load_column_mapping
from inventura.services import ConflictError, NotFoundError
from inventura.settings import Settings, get_settings
from inventura.web.routes import api, pages
from inventura.web.templating import STATIC_DIR

# Handlers are looked up along the exception's MRO, so DocumentClosedError (a CountError)
# gets 409 and other CountErrors 422.
ERROR_STATUS: dict[type[Exception], int] = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ConflictError: status.HTTP_409_CONFLICT,
    DocumentClosedError: status.HTTP_409_CONFLICT,
    CountError: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title="Inventura Toolkit",
        summary="Warehouse stock count: rack documents, counting and variances.",
        version="0.1.0",
    )
    app.state.settings = settings
    app.state.session_factory = make_session_factory(make_engine(settings.database_url))
    app.state.column_mapping = load_column_mapping(settings.column_mapping)
    app.include_router(api.router)
    app.include_router(pages.router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    for error_type in ERROR_STATUS:
        app.add_exception_handler(error_type, _domain_error)
    return app


async def _domain_error(request: Request, exc: Exception) -> JSONResponse:
    code = next(ERROR_STATUS[t] for t in type(exc).__mro__ if t in ERROR_STATUS)
    return JSONResponse({"detail": str(exc)}, status_code=code)
