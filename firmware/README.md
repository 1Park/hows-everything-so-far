# MCU 준비 — 실기 미검증

`refill_mock/refill_mock.ino`: Arduino_RouterBridge 기반 LED mock 시퀀스 초안. 별도 Arduino toolchain/core로 빌드·업로드한다. 실제 모터/그리퍼 없음. 제공 board core 설치 전 컴파일/실기 성공을 주장하지 않는다.

provide_safe, 짧은 handler, nested RPC/logging 금지, millis 기반 nonblocking 상태, command_id 중복 거부, 취소, polling 단절5초 watchdog. [Python RPC 계약](../app/hardware/README.md). LED_BUILTIN active-low는 가이드 예시를 따른 초안이며 보드 pin/polarity 확인 필요. 버튼/occupied는 확보 센서 미정이므로 false인 simulator 값이다. 실제 pin을 임의 지정하지 않았다.

호스트 arduino-router는 별도 서비스다. 설치/제약은 [대회 IoT 가이드](../qc-executorch-guide/IoT/README.md).
