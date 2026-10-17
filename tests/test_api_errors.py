from fastapi.testclient import TestClient

from common.api import create_api


def test_internal_error_keeps_request_id():
    app = create_api("Test")

    @app.get("/fail")
    async def fail():
        raise RuntimeError("private error details")

    with TestClient(app, raise_server_exceptions=False) as c:
        response = c.get("/fail", headers={"x-request-id": "correlation-1"})
        assert response.status_code == 500
        assert response.headers["x-request-id"] == "correlation-1"
        assert response.json()["error"]["request_id"] == "correlation-1"
        assert "private" not in response.text
