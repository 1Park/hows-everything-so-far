"""Wire-level checks for the Router client over a real unix socket. No board required."""

import shutil
import socket
import time
import tempfile
import threading
from pathlib import Path

import msgpack
import pytest

from app.hardware.io import BridgeHardware
from app.hardware.router import RouterClient, RouterError
from common.api import ApiError

pytestmark = pytest.mark.skipif(
    not hasattr(socket, "AF_UNIX"), reason="Router transport requires Unix-domain sockets"
)


class FakeRouterServer:
    """Accepts one connection at a time and replies with whatever the test supplies."""

    def __init__(self, path, responder):
        self.path = str(path)
        self.responder = responder
        self.requests = []
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(self.path)
        self.server.listen(4)
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        while True:
            try:
                connection, _ = self.server.accept()
            except OSError:
                return
            with connection:
                unpacker = msgpack.Unpacker(raw=False)
                hangup = False
                while not hangup:
                    try:
                        data = connection.recv(4096)
                    except OSError:
                        break
                    if not data:
                        break
                    unpacker.feed(data)
                    for request in unpacker:
                        self.requests.append(request)
                        reply = self.responder(request)
                        if reply is None:  # emulate a peer that drops the link
                            hangup = True
                            break
                        connection.sendall(reply)

    def close(self):
        self.server.close()


@pytest.fixture
def sockdir():
    # AF_UNIX paths are capped near 104 bytes, below pytest's tmp_path on macOS.
    directory = Path(tempfile.mkdtemp(prefix="rt", dir="/tmp"))
    yield directory
    shutil.rmtree(directory, ignore_errors=True)


@pytest.fixture
def router(sockdir):
    servers = []

    def start(responder):
        server = FakeRouterServer(sockdir / "router.sock", responder)
        servers.append(server)
        return server

    yield start
    for server in servers:
        server.close()


def ok(request):
    return msgpack.packb([1, request[1], None, True])


def test_request_frame_matches_the_guide_protocol(router, sockdir):
    server = router(ok)
    client = RouterClient(2, str(sockdir / "router.sock"))
    assert client.call("set_led_color", 1, 2, 3) is True
    kind, msgid, method, params = server.requests[0]
    assert (kind, method, params) == (0, "set_led_color", [1, 2, 3])
    assert msgid == 1
    assert client.call("refill_phase")  # msgid increments per call
    assert server.requests[1][1] == 2
    client.close()


def test_peer_error_is_raised_even_when_falsey(router, sockdir):
    server = router(lambda request: msgpack.packb([1, request[1], 0, None]))
    client = RouterClient(2, str(sockdir / "router.sock"))
    with pytest.raises(RouterError):
        client.call("refill_start", "id")
    assert server.requests
    client.close()


def test_stale_reply_is_skipped_not_mistaken_for_the_answer(router, sockdir):
    # A reply to an earlier, timed-out call must not satisfy the current one.
    def responder(request):
        return msgpack.packb([1, request[1] - 1, None, "stale"]) + msgpack.packb(
            [1, request[1], None, "fresh"]
        )

    router(responder)
    client = RouterClient(2, str(sockdir / "router.sock"))
    assert client.call("refill_phase") == "fresh"
    client.close()


def test_malformed_reply_is_rejected(router, sockdir):
    router(lambda request: msgpack.packb([1, request[1], None]))
    client = RouterClient(2, str(sockdir / "router.sock"))
    with pytest.raises(RouterError):
        client.call("refill_phase")
    client.close()


def test_disconnect_drops_the_socket_so_the_next_call_reconnects(router, sockdir):
    state = {"first": True}

    def responder(request):
        if state["first"]:
            state["first"] = False
            return None  # close without replying
        return ok(request)

    router(responder)
    client = RouterClient(2, str(sockdir / "router.sock"))
    with pytest.raises(RouterError):
        client.call("refill_phase")
    assert client.socket is None
    assert client.call("refill_phase") is True
    client.close()


def test_missing_socket_surfaces_as_a_retryable_503(sockdir):
    client = RouterClient(1, str(sockdir / "absent.sock"))
    with pytest.raises(RouterError):
        client.call("refill_phase")


async def test_bridge_hardware_reports_router_failure_as_503(sockdir):
    hardware = BridgeHardware(1, client=RouterClient(1, str(sockdir / "absent.sock")))
    with pytest.raises(ApiError) as failure:
        await hardware.set_color(1, 2, 3)
    assert failure.value.status == 503 and failure.value.retryable


def test_transport_failures_all_arrive_as_one_error(router, sockdir):
    # Callers handle RouterError; a msgpack or type failure escaping as itself
    # would surface as a 500 instead of the retryable 503 the demo expects.
    router(lambda request: b"\xc1\xc1\xc1not msgpack at all")
    client = RouterClient(2, str(sockdir / "router.sock"))
    with pytest.raises(RouterError):
        client.call("refill_phase")
    assert client.socket is None
    client.close()


async def test_a_timed_out_call_does_not_share_its_socket(sockdir):
    # The worker thread cannot be killed, so it may still be using the socket.
    # The next call must not write into the same stream.
    class SlowClient:
        def __init__(self):
            self.closed = 0

        def call(self, *_):
            time.sleep(5)

        def close(self):
            self.closed += 1

    slow = SlowClient()
    hardware = BridgeHardware(0.2, client=slow)
    with pytest.raises(ApiError) as failure:
        await hardware.set_color(1, 2, 3)
    assert failure.value.status == 503
    # Once per attempt: each abandoned socket may still be in use by its thread.
    assert slow.closed == 2, "an abandoned connection was left open for the next call"


async def test_a_reply_of_the_wrong_shape_is_a_fault_not_a_crash():
    class OddClient:
        def call(self, method, *_):
            return None if method == "refill_phase" else True

        def close(self):
            pass

    assert await BridgeHardware(1, client=OddClient()).advance() == "fault"


async def test_one_transport_failure_does_not_stop_the_demo():
    # A restarted Router or a socket left dirty by an earlier timeout clears on a
    # fresh connection, so confirmation should survive it.
    class FlakyClient:
        def __init__(self):
            self.calls = 0
            self.closed = 0

        def call(self, method, *_):
            self.calls += 1
            if self.calls == 1:
                raise RouterError("Router socket unavailable")
            return True

        def close(self):
            self.closed += 1

    flaky = FlakyClient()
    hardware = BridgeHardware(1, client=flaky)
    await hardware.start("command-1")
    assert flaky.calls == 2 and flaky.closed == 1


async def test_a_start_whose_reply_was_lost_is_not_reported_as_refused():
    # The MCU refuses a command id it has already seen, so a retry of a start that
    # did arrive looks like a rejection. A running sequence settles it.
    class LostReplyClient:
        def __init__(self):
            self.first = True

        def call(self, method, *_):
            if method == "refill_start":
                if self.first:
                    self.first = False
                    raise RouterError("reply lost")
                return False  # the MCU already has this command id
            return 1  # LOADING: it really did start

        def close(self):
            pass

    await BridgeHardware(1, client=LostReplyClient()).start("command-2")


async def test_a_genuine_refusal_still_raises():
    class BusyClient:
        def call(self, method, *_):
            return False if method == "refill_start" else 0  # IDLE: nothing running

        def close(self):
            pass

    with pytest.raises(ApiError) as failure:
        await BridgeHardware(1, client=BusyClient()).start("command-3")
    assert failure.value.status == 409
