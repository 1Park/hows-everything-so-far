# HardwareIO

Controller 내부 모듈 `io.py`, HTTP 서버 아님. `MockHardware`는 phase/LED/button/occupied/command_id와 중복 명령 이력을 갖는다. `simulate_inputs`로 버튼/센서 시뮬레이션 가능. 버튼만으로 고객 확인을 대체하지 않는다.

`BridgeHardware`는 공식 `arduino.app_utils.Bridge.call(..., timeout=...)`을 thread에서 실행한다. **보드에서 미검증**. 계약: refill_start(command_id)->bool, refill_cancel(command_id)->bool, refill_phase()->int(0idle/1loading/2returning/3done/4cancelled), refill_button/occupied()->bool, set_led_state(bool). GPIO handler는 MCU provide_safe. 취소 command_id를 tombstone으로 기록해 취소보다 늦게 도착한 같은 start를 거부한다.

호스트가 phase를 polling하면 MCU watchdog 갱신, 5초 끊기면 취소. timeout thread는 강제 종료 불가하므로 보드에서 RPC 수명/단절/늦은 응답 검증이 필요하다. 이 시퀀스는 LED 기반 mock이며 실제 모터/집기 없음. [MCU 초안](../../firmware/README.md). [공식 Python Bridge 소스](https://github.com/arduino/app-bricks-py/blob/main/src/arduino/app_utils/bridge.py)는 first-use 연결과 call timeout을 제공하며 실제 설치 버전과 일치 여부를 보드에서 확인한다.
