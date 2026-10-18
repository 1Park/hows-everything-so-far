"""Venue display: serves the read-only stage view on its own port.

It holds no state and talks to nothing. The page reads the Controller's websocket
directly, so this process is only a file server; keeping it separate means the
screen in the room cannot be mistaken for the tablet and cannot post anything.
"""

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from common.config import ROOT, load_settings

DISPLAY = ROOT / "app/display"


def create_app():
    app = FastAPI(title="Refill Assist display", docs_url=None, redoc_url=None)
    # Never cached: a display left running for a day should pick up a fix on reload.
    no_store = {"Cache-Control": "no-store"}

    class FreshStaticFiles(StaticFiles):
        def file_response(self, *args, **kwargs):
            response = super().file_response(*args, **kwargs)
            response.headers.update(no_store)
            return response

        def is_not_modified(self, *args, **kwargs):
            return False

    settings = load_settings()
    controller = f"http://127.0.0.1:{settings.controller_port}"

    @app.get("/health")
    async def health():
        return {"status": "alive", "service": "Display"}

    @app.get("/runtime")
    async def runtime():
        """What is running, relayed from the Controller.

        The page could not read it directly: a cross-origin fetch needs CORS the
        Controller does not grant, and widening that for a display would be the
        wrong trade. Websockets and images have no such restriction.
        """
        try:
            async with httpx.AsyncClient(timeout=4, trust_env=False) as client:
                response = await client.get(controller + "/ready")
                return response.json()
        except (httpx.HTTPError, ValueError):
            return {"ready": False, "dependencies": {}}

    @app.get("/")
    async def index():
        return FileResponse(DISPLAY / "index.html", headers=no_store)

    app.mount("/display", FreshStaticFiles(directory=DISPLAY), name="display")
    return app
