"""MessagePack-RPC client for the Arduino Router socket.

The official `arduino.app_utils` Bridge package is not distributable: it is not on
PyPI, not in the board's apt packages, and not inside the App Lab brick images, so
an application venv cannot import it. The IoT guide ships a raw client for the same
Router socket (`IoT/artifacts/msgpack_test.py`), which is the transport used here.

This still goes through `arduino-router`, so the rule it protects holds: the Bridge
UART is never opened directly and the Router stays the only owner of the link.

Request  [0, msgid, method, params]
Response [1, msgid, error, result]
"""

import socket

import msgpack

SOCKET_PATH = "/var/run/arduino-router.sock"


class RouterError(RuntimeError):
    """The Router or the peer refused, or the link is unusable."""


class RouterClient:
    """One connection, one call at a time. Callers serialise; see BridgeHardware."""

    def __init__(self, timeout: float, path: str = SOCKET_PATH):
        self.timeout = timeout
        self.path = path
        self.socket: socket.socket | None = None
        self.unpacker = msgpack.Unpacker(raw=False, max_buffer_size=65536)
        self.msgid = 0

    def connect(self):
        if self.socket is not None:
            return self.socket
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.settimeout(self.timeout)
        try:
            client.connect(self.path)
        except OSError as error:
            client.close()
            raise RouterError(f"Router socket unavailable at {self.path}: {error}") from error
        # A fresh stream must not be read with buffered bytes from a dead one.
        self.unpacker = msgpack.Unpacker(raw=False, max_buffer_size=65536)
        self.socket = client
        return client

    def close(self):
        if self.socket is not None:
            self.socket.close()
            self.socket = None

    def call(self, method: str, *params):
        client = self.connect()
        self.msgid += 1
        expected = self.msgid
        try:
            client.sendall(msgpack.packb([0, expected, method, list(params)], use_bin_type=True))
            return self.await_reply(client, expected)
        except (OSError, msgpack.UnpackException, RouterError):
            # Never reuse a stream whose framing or state is in doubt; reconnect next call.
            self.close()
            raise

    def await_reply(self, client, expected):
        while True:
            for response in self.unpacker:
                result = self.read_response(response, expected)
                if result is not NOT_MINE:
                    return result
            data = client.recv(4096)
            if not data:
                raise RouterError("Router disconnected before replying")
            self.unpacker.feed(data)

    def read_response(self, response, expected):
        if (
            not isinstance(response, list)
            or len(response) != 4
            or type(response[0]) is not int
            or response[0] != 1
            or type(response[1]) is not int
        ):
            raise RouterError(f"Unexpected RPC response: {response!r}")
        if response[1] != expected:
            # A reply to a call that already timed out. Drop it, keep waiting.
            return NOT_MINE
        if response[2] is not None:
            raise RouterError(f"RPC failed: {response[2]!r}")
        return response[3]


NOT_MINE = object()
