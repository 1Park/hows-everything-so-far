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
