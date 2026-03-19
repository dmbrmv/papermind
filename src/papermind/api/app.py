"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def create_app(kb_path: Path) -> FastAPI:
    """Create a FastAPI application bound to a knowledge base.

    Args:
        kb_path: Path to the PaperMind knowledge base.

    Returns:
        Configured FastAPI instance.
    """
    app = FastAPI(
        title="PaperMind",
        description="Scientific knowledge base — papers, packages, codebases.",
        version="3.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Store KB path in app state for dependency injection
    app.state.kb_path = kb_path

    # CORS — permissive for localhost development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register route modules
    from papermind.api.routes.analysis import router as analysis_router
    from papermind.api.routes.catalog import router as catalog_router
    from papermind.api.routes.diff import router as diff_router
    from papermind.api.routes.search import router as search_router
    from papermind.api.routes.sessions import router as sessions_router

    app.include_router(search_router, prefix="/api/v1", tags=["search"])
    app.include_router(catalog_router, prefix="/api/v1", tags=["catalog"])
    app.include_router(sessions_router, prefix="/api/v1", tags=["sessions"])
    app.include_router(analysis_router, prefix="/api/v1", tags=["analysis"])
    app.include_router(diff_router, prefix="/api/v1", tags=["diff"])

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "kb_path": str(kb_path)}

    return app
