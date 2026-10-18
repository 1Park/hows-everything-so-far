# HardwareIO

Inside the Controller, uses `MockHardware` or `BridgeHardware` from [`io.py`](io.py). The default is mock, and there is no real driving or grasping. Button input does not replace the customer's card Confirm.

Bridge is the MessagePack-RPC client in [`router.py`](router.py) and connects to `/var/run/arduino-router.sock`. It does not import `arduino.app_utils`; the host arduino-router owns the UART. `/tmp/.../router.sock` is used only for the fake server in tests.

The MCU RPCs are refill_start/cancel/phase/button/occupied and set_led_state/color. Calls are serialized, and timeouts and disconnects are returned as errors. A thread cannot be forcibly stopped after a timeout, so the MCU watchdog is responsible for stopping.

[MCU draft and on-hardware validation scope](../../firmware/README.md), [wire tests](../../tests/test_router.py). The tests use a fake peer over a real Unix socket; they are not board hardware validation.
