"""Presentation deck: static slides about how the demo is built.

Separate from the display on purpose. It depends on nothing — no board, no models —
so it still presents if the demo is down, and a slide change cannot disturb a run.
"""

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from common.config import ROOT

DECK = ROOT / "app/deck"


def create_app():
    app = FastAPI(title="Refill Assist deck", docs_url=None, redoc_url=None)
    # Never cached: a slide fixed minutes before the talk should be the one shown.
    no_store = {"Cache-Control": "no-store"}

    class FreshStaticFiles(StaticFiles):
        def file_response(self, *args, **kwargs):
            response = super().file_response(*args, **kwargs)
            response.headers.update(no_store)
            return response

        def is_not_modified(self, *args, **kwargs):
            return False

    @app.get("/health")
    async def health():
        return {"status": "alive", "service": "Deck"}

    @app.get("/")
    async def index():
        return FileResponse(DECK / "index.html", headers=no_store)

    app.mount("/deck", FreshStaticFiles(directory=DECK), name="deck")
    return app
