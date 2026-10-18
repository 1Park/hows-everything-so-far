# HardwareIO

Controller 내부 [`io.py`](io.py)의 `MockHardware` 또는 `BridgeHardware`를 사용한다. 기본은 mock이며 실제 주행·집기는 없다. 버튼 입력은 고객의 카드 Confirm을 대체하지 않는다.

Bridge는 [`router.py`](router.py)의 MessagePack-RPC 클라이언트로 `/var/run/arduino-router.sock`에 연결한다. `arduino.app_utils`를 import하지 않으며 UART는 호스트 arduino-router가 소유한다. `/tmp/.../router.sock`은 테스트의 가짜 서버에만 사용한다.

MCU RPC는 refill_start/cancel/phase/button/occupied와 set_led_state/color다. 호출은 직렬화하며 timeout·단절을 오류로 반환한다. timeout 뒤 thread를 강제 중단할 수 없으므로 MCU watchdog이 정지를 책임진다.

[MCU 초안·실기 검증 범위](../../firmware/README.md), [wire 테스트](../../tests/test_router.py). 테스트는 실제 Unix 소켓의 가짜 peer이며 보드 하드웨어 검증은 아니다.
