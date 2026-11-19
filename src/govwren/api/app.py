"""The application factory."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from govwren import PRODUCT_NAME, __version__, mail
from govwren.access.middleware import install_access
from govwren.access.policy import authorize
from govwren.api.problems import install_problem_handlers
from govwren.api.routers import (
    branding,
    evidence,
    intake,
    inventory,
    people,
    program,
    review,
    session,
    sso,
    system,
)
from govwren.api.routers.branding import install_branding
from govwren.api.security import install_security_headers
from govwren.api.static import install_static
from govwren.config import ENV_CONFIG, Config, load_config
from govwren.db.engine import Database
from govwren.home import DataHome

ROUTERS = (system, session, sso, people, branding, inventory, evidence, intake, review, program)


def create_app(config: Config) -> FastAPI:
    home = DataHome(config.data.home)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        home.require()
        app.state.db = Database(config.database_url)
        # The mailer runs beside the server for as long as it is up, if email is set up.
        stop_mail = mail.start_worker(app.state.db, config) if config.mail.enabled else None
        try:
            yield
        finally:
            if stop_mail is not None:
                stop_mail.set()
            app.state.db.dispose()

    app = FastAPI(
        title=PRODUCT_NAME,
        version=__version__,
        summary="An open system of record for AI governance.",
        lifespan=lifespan,
        docs_url=None,  # the bundled documentation pages load third-party scripts
        redoc_url=None,
        openapi_url="/api/openapi.json",
        dependencies=[Depends(authorize)],  # every API route is checked against the policy table
    )
    app.state.config = config
    app.state.home = home

    install_access(app)  # runs inside the header middleware, so refusals carry the headers
    install_security_headers(app)
    install_problem_handlers(app)
    for module in ROUTERS:
        app.include_router(module.router)
    install_branding(app)
    install_static(app)  # last: its catch-all would shadow anything registered after it
    return app


def create_app_from_env() -> FastAPI:
    """The factory uvicorn's workers call. ``govwren serve`` names the configuration."""
    return create_app(load_config(os.environ.get(ENV_CONFIG)))
