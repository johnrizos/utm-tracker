from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from utm_tracker.routers import links, redirect


def create_app() -> FastAPI:
    app = FastAPI(
        title="UTM Tracker",
        version="0.1.0",
        summary="Build consistent UTM links, shorten them and count real clicks.",
    )
    app.include_router(links.router)
    app.include_router(redirect.router)

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/docs")

    return app


app = create_app()
