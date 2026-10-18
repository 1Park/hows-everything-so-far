# MCU prep — not verified on hardware

`refill_mock/refill_mock.ino`: draft LED mock sequence based on Arduino_RouterBridge. Build and upload it with a separate Arduino toolchain/core. No real motor/gripper. No claim of successful compilation or on-hardware run is made before the provided board core is installed.

provide_safe, short handlers, no nested RPC/logging, millis-based nonblocking state, duplicate command_id rejection, cancellation, 5-second watchdog on polling loss. [Python RPC contract](../app/hardware/README.md). LED_BUILTIN active-low is a draft that follows the guide example; the board pin/polarity needs to be checked. Button/occupied are simulator values that are false, because the sensors to use have not been decided. No real pins have been assigned arbitrarily.

The host arduino-router is a separate service. For installation and constraints, see the [competition IoT guide](../qc-executorch-guide/IoT/README.md).
