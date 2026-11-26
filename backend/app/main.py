from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.api.auth_oidc import router as auth_oidc_router
from app.api.auth_settings import router as auth_settings_router
from app.api.mealie_routes import router as mealie_router
from app.api.picnic_routes import router as picnic_router
from app.api.tesserae_routes import router as tesserae_router
from app.config import APP_VERSION, get_settings
from app.db import create_all_tables, get_db, get_session_factory, init_db_engine
from app.schemas import HealthResponse
from app.services.enrichment import enrich_pending_products
from app.services.mealie_service import is_mealie_configured, seed_demo_mealie_data, sync_mealie
from app.services.oidc_service import (
    SESSION_COOKIE_NAME,
    get_session_user_from_cookie,
    is_session_user_allowed,
)
from app.services.picnic_service import (
    PicnicReauthRequiredError,
    PicnicServiceError,
    get_picnic_status,
    get_sync_lock,
    seed_demo_picnic_data,
    sync_picnic,
)
from app.services.settings_store import (
    get_effective_oidc_config,
    get_effective_sync_interval_minutes,
    is_demo_mode,
)

logger = logging.getLogger("stats_for_picnic")


def _resolve_static_dir() -> Path | None:
    settings = get_settings()
    candidates = []
    if settings.static_dir:
        candidates.append(Path(settings.static_dir))
    candidates.extend(
        [
            Path("/app/static"),
            Path(__file__).resolve().parents[2] / "frontend" / "dist",
        ]
    )
    for candidate in candidates:
        if candidate.is_dir() and (candidate / "index.html").is_file():
            return candidate
    return None


async def _periodic_sync_loop() -> None:
    elapsed_sec = 0
    tick_sec = 60
    while True:
        await asyncio.sleep(tick_sec)
        elapsed_sec += tick_sec
        session = get_session_factory()()
        try:
            interval_min = get_effective_sync_interval_minutes(session)
            if interval_min <= 0 or is_demo_mode(session):
                elapsed_sec = 0
                continue
            if elapsed_sec < interval_min * 60:
                continue
            elapsed_sec = 0

            lock = get_sync_lock()
            if lock.locked():
                continue

            async with lock:
                status = get_picnic_status(session)
                if status == "ok":
                    try:
                        await asyncio.to_thread(sync_picnic, session)
                    except (PicnicReauthRequiredError, PicnicServiceError) as exc:
                        logger.warning("Scheduled Picnic sync skipped/failed: %s", exc)
                elif status == "reauth_required":
                    logger.debug("Skipping scheduled Picnic sync until user completes re-auth.")

                await enrich_pending_products(session)

                if is_mealie_configured(session):
                    try:
                        await sync_mealie(session)
                    except Exception as exc:
                        logger.warning("Scheduled Mealie sync failed: %s", exc)
        except Exception as exc:
            logger.exception("Periodic sync loop iteration failed: %s", exc)
        finally:
            session.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    init_db_engine(settings)
    create_all_tables()

    session = get_session_factory()()
    try:
        effective_demo = is_demo_mode(session, settings)
        if effective_demo:
            seed_demo_picnic_data(session)
            seed_demo_mealie_data(session)
    finally:
        session.close()

    sync_task = asyncio.create_task(_periodic_sync_loop())

    logger.info(
        "Stats for Picnic started (demo_mode=%s, data_dir=%s)",
        effective_demo,
        settings.app_data_dir,
    )
    try:
        yield
    finally:
        sync_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sync_task


def create_app() -> FastAPI:
    app = FastAPI(
        title="Stats for Picnic",
        version=APP_VERSION,
        description="Self-hosted grocery & recipe nutrition companion for Picnic, Mealie, and Tesserae.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def oidc_guard_middleware(request, call_next):
        path = request.url.path
        # Only protect internal /api/v1/* endpoints; keep /api/v1/summary & /widget/eink (API_KEY),
        # /api/health, /api/auth/oidc/*, and static SPA assets publicly reachable.
        if path.startswith("/api/v1/") and path != "/api/v1/summary":
            session = get_session_factory()()
            try:
                oidc_cfg = get_effective_oidc_config(session)
            finally:
                session.close()
            if oidc_cfg["enabled"]:
                user = get_session_user_from_cookie(request.cookies.get(SESSION_COOKIE_NAME))
                allowed_emails: list[str] = list(oidc_cfg["allowed_emails"])  # type: ignore[arg-type]
                if not is_session_user_allowed(user, allowed_emails):
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Anmeldung erforderlich.", "oidc_required": True},
                    )
        return await call_next(request)

    @app.get("/api/health", response_model=HealthResponse, tags=["system"])
    def health(db: Session = Depends(get_db)) -> HealthResponse:
        return HealthResponse(status="ok", demo_mode=is_demo_mode(db), version=APP_VERSION)

    app.include_router(auth_oidc_router)
    app.include_router(auth_settings_router)
    app.include_router(picnic_router)
    app.include_router(mealie_router)
    app.include_router(tesserae_router)

    static_dir = _resolve_static_dir()
    if static_dir is not None:
        assets_dir = static_dir / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def serve_spa(full_path: str):
            if (
                full_path.startswith("api/")
                or full_path == "api"
                or full_path.startswith("widget/")
                or full_path == "widget"
            ):
                return JSONResponse(status_code=404, content={"detail": "Not found"})
            candidate = (static_dir / full_path).resolve()
            if (
                full_path
                and candidate.is_file()
                and static_dir.resolve() in candidate.parents
            ):
                return FileResponse(candidate)
            return FileResponse(static_dir / "index.html")

    return app


app = create_app()
