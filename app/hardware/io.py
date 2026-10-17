"""Mock movement only. Bridge adapter is prepared but has NOT been tested on hardware."""

import asyncio
from dataclasses import asdict, dataclass
from typing import Protocol

from common.api import ApiError


@dataclass
class HardwareState:
    backend: str = "mock"
    phase: str = "idle"
    led: bool = False
    color: tuple[int, int, int] = (0, 0, 0)
    button: bool = False
    occupied: bool = False
    command_id: str | None = None


class HardwareIO(Protocol):
    async def set_led(self, on: bool): ...
    async def set_color(self, red: int, green: int, blue: int): ...
    async def start(self, command_id: str): ...
    async def advance(self) -> str: ...
    async def cancel(self): ...
    async def read(self) -> dict: ...


class MockHardware:
    def __init__(self):
        self.state = HardwareState()
        self.commands: list[str] = []

    async def set_led(self, on: bool):
        self.state.led = on
        self.state.color = (255, 255, 255) if on else (0, 0, 0)

    async def set_color(self, red: int, green: int, blue: int):
        self.state.color = (red, green, blue)
        self.state.led = any((red, green, blue))

    async def start(self, command_id: str):
        if self.state.phase not in ("idle", "done", "cancelled"):
            raise ApiError("hardware_busy", "The mock sequence is already running", 409)
        if command_id in self.commands:
            raise ApiError("duplicate_command", "This command has already been started", 409)
        self.commands.append(command_id)
        self.state.command_id, self.state.phase, self.state.led = command_id, "loading", True

    async def advance(self):
        self.state.phase = {"loading": "returning", "returning": "done"}.get(
            self.state.phase, self.state.phase
        )
        self.state.led = self.state.phase not in ("done", "cancelled", "idle")
        return self.state.phase

    async def cancel(self):
        self.state.phase, self.state.led = "cancelled", False

    async def read(self):
        return asdict(self.state)

    def simulate_inputs(self, button: bool, occupied: bool):
        self.state.button, self.state.occupied = button, occupied


class BridgeHardware:
    """Official arduino.app_utils transport; serialized RPC. No invented UART/socket path."""

    def __init__(self, timeout: float):
        self.timeout = timeout
        self.rpc_lock = asyncio.Lock()
        self.command_id = ""

    async def rpc(self, name, *args):
        def invoke():
            from arduino.app_utils import Bridge

            return Bridge.call(name, *args, timeout=self.timeout)

        try:
            async with self.rpc_lock:
                return await asyncio.wait_for(asyncio.to_thread(invoke), self.timeout)
        except Exception:
            # A timed-out thread cannot be killed. MCU watchdog is authoritative for stopping.
            raise ApiError(
                "bridge_error",
                "Bridge did not acknowledge the command; check the MCU watchdog",
                503,
                True,
            ) from None

    async def start(self, command_id):
        self.command_id = command_id
        if not await self.rpc("refill_start", command_id):
            raise ApiError("hardware_rejected", "MCU rejected the mock sequence", 409)

    async def set_led(self, on: bool):
        await self.rpc("set_led_state", on)

    async def set_color(self, red: int, green: int, blue: int):
        if not await self.rpc("set_led_color", red, green, blue):
            raise ApiError("hardware_rejected", "MCU rejected the colour", 409)

    async def advance(self):
        return {0: "idle", 1: "loading", 2: "returning", 3: "done", 4: "cancelled"}.get(
            int(await self.rpc("refill_phase")), "fault"
        )

    async def cancel(self):
        await self.rpc("refill_cancel", self.command_id)

    async def read(self):
        phase = await self.advance()
        return {
            "backend": "bridge",
            "phase": phase,
            "led": phase in ("loading", "returning"),
            "button": bool(await self.rpc("refill_button")),
            "occupied": bool(await self.rpc("refill_occupied")),
            "verified_on_board": False,
        }
