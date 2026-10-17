import time

import pytest

from app.media import VideoSource
from common.api import ApiError
from common.config import ROOT


def test_missing_source_never_returns_fixture(tmp_path):
    source = VideoSource(str(tmp_path / "missing.avi"))
    assert source.latest is None
    source.start()
    for _ in range(100):
        if source.error:
            break
        time.sleep(0.02)
    with pytest.raises(ApiError):
        source.frame()
    source.close()


def test_video_file_loop_transport(tmp_path):
    cv2 = pytest.importorskip("cv2")
    path = tmp_path / "sample.avi"
    image = cv2.imread(str(ROOT / "docs/assets/cups-example.jpg"))
    writer = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (image.shape[1], image.shape[0])
    )
    assert writer.isOpened()
    for _ in range(3):
        writer.write(image)
    writer.release()
    source = VideoSource(str(path))
    source.start()
    try:
        for _ in range(100):
            if source.latest is not None:
                break
            time.sleep(0.02)
        first, _ = source.frame()
        assert first.startswith(b"\xff\xd8")
        time.sleep(0.5)  # reads past EOF and loops
        second, _ = source.frame()
        assert second.startswith(b"\xff\xd8") and not source.error
    finally:
        source.close()


def test_unavailable_camera_index_never_returns_fixture():
    # A camera index that is not present must fail loudly, like a missing file does.
    # CAMERA_SOURCE is left empty until the real index is known, so a wrong value
    # must not silently degrade into the static fixture image.
    source = VideoSource("99")
    assert source.mode == "camera-or-file"
    assert source.latest is None
    source.start()
    for _ in range(250):
        if source.error:
            break
        time.sleep(0.02)
    assert source.error, "an unopenable camera index must surface an error"
    with pytest.raises(ApiError) as failure:
        source.frame()
    assert failure.value.status == 503
    assert source.latest is None
    source.close()


def test_empty_source_is_the_explicit_fixture():
    # Empty CAMERA_SOURCE is the declared fixture mode, not an implicit /dev/video0.
    source = VideoSource("")
    assert source.mode == "fixture-image"
    source.start()
    assert source.thread is None
    data, mime = source.frame()
    assert data.startswith(b"\xff\xd8") and mime == "image/jpeg"
    source.close()


def test_stream_survives_a_gap_instead_of_ending(tmp_path):
    # A browser never retries a dead <img> stream, so a momentary gap must not
    # close the response.
    import asyncio

    source = VideoSource(str(tmp_path / "unused.avi"))
    source.latest, source.content_type = b"\xff\xd8frame", "image/jpeg"
    source.stream_interval = 0.01

    async def collect():
        chunks = []
        stream = source.frames()
        chunks.append(await anext(stream))
        source.error = "temporarily unavailable"  # the gap
        gapped = asyncio.ensure_future(anext(stream))
        await asyncio.sleep(0.05)
        assert not gapped.done(), "the stream ended instead of waiting out the gap"
        source.error = None
        chunks.append(await gapped)
        await stream.aclose()
        return chunks

    try:
        chunks = asyncio.run(collect())
    finally:
        source.close()
    assert all(b"\xff\xd8frame" in chunk for chunk in chunks)


def test_capture_is_retried_after_the_camera_goes_away(tmp_path):
    # A USB drop used to be permanent: the capture thread exited and every later
    # frame request failed until the app restarted.
    source = VideoSource(str(tmp_path / "missing.avi"))
    attempts = []
    original = source.capture

    def counted():
        attempts.append(1)
        original()

    source.capture = counted
    source.start()
    for _ in range(200):
        if len(attempts) >= 2:
            break
        time.sleep(0.02)
    source.close()
    assert len(attempts) >= 2, "the capture loop gave up after the first failure"
    assert source.error, "a source that is still down must keep reporting the error"


def test_ui_assets_are_never_served_from_cache():
    # A tablet kept running an older app.js after a deploy, so a UI fix looked
    # like it had not shipped at all.
    from fastapi.testclient import TestClient

    from app.server import create_app

    with TestClient(create_app()) as client:
        for path in ("/", "/ui/app.js", "/ui/style.css"):
            response = client.get(path)
            assert response.status_code == 200, path
            assert response.headers.get("cache-control") == "no-store", path
