"""The deck must stand on its own: it is shown while the demo may be restarting."""

import pytest
from fastapi.testclient import TestClient

from services.deck.server import create_app


@pytest.fixture
def client():
    with TestClient(create_app()) as session:
        yield session


def test_slides_are_served_fresh(client):
    for path in ("/", "/deck/deck.js", "/deck/deck.css"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers.get("cache-control") == "no-store", path


def test_it_needs_nothing_from_the_board(client):
    # No call to the Controller, the models or the board: the page is self-contained.
    page = client.get("/").text
    script = client.get("/deck/deck.js").text
    assert "new WebSocket(" not in script, "the deck should not open a connection"
    assert "fetch(" not in script, "the deck should not call the board"
    assert "<svg" in script or "<svg" in page  # the architecture is drawn, not fetched
