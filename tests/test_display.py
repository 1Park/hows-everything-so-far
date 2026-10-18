"""The venue display is read-only and must stay that way."""

import json
import pathlib
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from services.display.server import create_app


@pytest.fixture
def client():
    with TestClient(create_app()) as session:
        yield session


def test_the_page_and_its_assets_are_served_fresh(client):
    # A screen left running all day should pick up a fix on reload.
    for path in ("/", "/display/display.js", "/display/display.css"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers.get("cache-control") == "no-store", path


def test_nothing_can_be_posted_to_it(client):
    # A stray touch on a projector must not be able to disturb a run.
    for path in ("/", "/runtime", "/api/observe", "/api/confirm"):
        assert client.post(path).status_code in (404, 405), path


def test_runtime_answers_even_when_the_controller_is_down(client):
    # The display should show "not ready" rather than a blank screen.
    body = client.get("/runtime").json()
    assert "dependencies" in body


def _drive():
    """Run display.js against a stub DOM and report what the image was pointed at.

    The live view is an MJPEG stream the browser holds open, so the bug this
    guards against is invisible to a request-level test: the display keeps a
    connection the Controller has already dropped.
    """
    node = shutil.which("node")
    if not node:
        pytest.skip("node is needed to exercise the display's browser logic")
    root = pathlib.Path(__file__).resolve().parent.parent
    out = subprocess.run(
        [node, str(root / "tests/support/drive_display.js"), str(root / "app/display/display.js")],
        capture_output=True, text=True, timeout=30, check=True,
    )
    return dict(json.loads(out.stdout))


def test_the_live_view_comes_back_after_the_controller_restarts():
    # An aborted multipart stream does not reliably fire the image's error event,
    # so without the instance check the display kept showing the last frame it got
    # before the restart, for the rest of the demo.
    steps = _drive()
    assert steps["after-controller-restart"] != steps["restart-same-process"], (
        "the display reused a video connection that died with the old Controller"
    )
    assert "/api/video" in steps["after-controller-restart"]


def test_an_analyzed_frame_replaces_the_live_view_and_gives_it_back():
    steps = _drive()
    assert "/api/snapshot/" in steps["snapshot"]
    assert "/api/video" in steps["live"]
    assert "/api/video" in steps["restart-same-process"]
