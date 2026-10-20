"""App factory. Run with: uvicorn flakehunter.main:create_app --factory --reload"""

import logging
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import sessionmaker

from flakehunter import __version__, ai_api, api, models, webhooks  # noqa: F401  (models registers tables)
from flakehunter.config import Settings, get_settings
from flakehunter.db import Base, make_engine
from flakehunter.github import GitHubClient
from flakehunter.sandbox import Sandbox, make_sandbox


def create_app(
    settings: Settings | None = None,
    github_client: GitHubClient | None = None,
    llm_client: Any = None,
    sandbox: Sandbox | None = None,
) -> FastAPI:
    logging.basicConfig(level=logging.INFO)
    settings = settings or get_settings()
    engine = make_engine(settings.database_url)
    # TODO: replace with Alembic migrations before the first real deployment.
    Base.metadata.create_all(engine)

    app = FastAPI(title="FlakeHunter", version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.settings = settings
    app.state.sessionmaker = sessionmaker(engine, expire_on_commit=False)
    app.state.github = github_client or GitHubClient.from_settings(settings)
    app.state.llm = llm_client  # created on first use, so the server starts without a key
    app.state.sandbox = sandbox or make_sandbox(settings)

    app.include_router(api.router)
    app.include_router(ai_api.router)
    app.include_router(webhooks.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
