"""The venue display is read-only and must stay that way."""

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
