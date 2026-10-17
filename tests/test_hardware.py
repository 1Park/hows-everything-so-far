import sys
import types

from app.hardware.io import BridgeHardware, MockHardware


async def test_mock_inputs_and_led():
    hardware = MockHardware()
    hardware.simulate_inputs(True, True)
    await hardware.set_led(True)
    assert (await hardware.read())["button"] is True
    assert (await hardware.read())["occupied"] is True
    assert (await hardware.read())["led"] is True


async def test_bridge_adapter_contract_only(monkeypatch):
    calls = []

    class Bridge:
        @staticmethod
        def call(name, *args, timeout):
            calls.append((name, args, timeout))
            return 3 if name == "refill_phase" else True

    module = types.ModuleType("arduino.app_utils")
    module.Bridge = Bridge
    monkeypatch.setitem(sys.modules, "arduino", types.ModuleType("arduino"))
    monkeypatch.setitem(sys.modules, "arduino.app_utils", module)
    hardware = BridgeHardware(2)
    await hardware.start("command-id")
    await hardware.set_led(True)
    await hardware.cancel()
    state = await hardware.read()
    assert state["phase"] == "done" and not state["verified_on_board"]
    assert ("refill_start", ("command-id",), 2) in calls
    assert ("refill_cancel", ("command-id",), 2) in calls
