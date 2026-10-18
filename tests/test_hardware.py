import asyncio


from app.hardware.io import BridgeHardware, MockHardware
from common.api import ApiError


async def test_mock_inputs_and_led():
    hardware = MockHardware()
    hardware.simulate_inputs(True, True)
    await hardware.set_led(True)
    assert (await hardware.read())["button"] is True
    assert (await hardware.read())["occupied"] is True
    assert (await hardware.read())["led"] is True


class FakeRouter:
    """Stands in for the Router socket; records calls, no board required."""

    def __init__(self):
        self.calls = []

    def call(self, name, *args):
        self.calls.append((name, args))
        return 3 if name == "refill_phase" else True

    def close(self):
        pass


async def test_bridge_adapter_contract_only():
    router = FakeRouter()
    calls = router.calls
    hardware = BridgeHardware(2, client=router)
    await hardware.start("command-id")
    await hardware.set_led(True)
    await hardware.cancel()
    state = await hardware.read()
    assert state["phase"] == "done" and state["verified_on_board"]
    assert ("refill_start", ("command-id",)) in calls
    assert ("refill_cancel", ("command-id",)) in calls


async def test_phase_colour_is_pushed_once_and_never_breaks_the_demo():
    from app.clients import ModelClients
    from app.controller import PHASE_COLOURS, Controller
    from common.config import load_settings

    settings = load_settings(None)
    controller = Controller(settings, ModelClients(settings))
    hardware = controller.hardware = MockHardware()
    calls = []
    original = hardware.set_color

    async def record(red, green, blue):
        calls.append((red, green, blue))
        await original(red, green, blue)

    hardware.set_color = record

    controller.emit("observing", "x")
    controller.emit("observing", "x again")  # unchanged colour must not re-send
    controller.emit("error", "boom")
    await asyncio.sleep(0)
    assert calls == [PHASE_COLOURS["observing"], PHASE_COLOURS["error"]]

    # The mock sequence owns the LED on the MCU, so Linux sends nothing for it.
    controller.emit("loading", "x")
    await asyncio.sleep(0)
    assert calls[-1] == PHASE_COLOURS["error"]

    async def boom(*_):
        raise ApiError("bridge_error", "down", 503, True)

    hardware.set_color = boom
    controller.emit("done", "finished")  # must not raise
    await asyncio.sleep(0)
    assert controller.phase == "done"
