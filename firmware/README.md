# MCU firmware

VENTUNO Q의 STM32H5F5에서 실행할 Arduino sketch를 둔다. Python 앱·모델 서버와 별도로 빌드·업로드한다. sketch와 빌드 설정은 보드 환경을 확인하며 추가한다.

- Arduino Bridge 메서드 등록과 GPIO handler
- LED 상태·버튼·확보한 센서 입력
- nonblocking·취소 가능한 mock 적재/복귀 시퀀스

GPIO handler는 `provide_safe`를 사용하고 짧게 처리한다. handler 내부 nested RPC·RPC logging을 피한다. Python 호출부는 `app/hardware/`와 메서드 계약을 맞춘다. 카메라·DINO·Qwen은 MCU에서 실행하지 않는다.

설치·예제는 [IoT 가이드](../qc-executorch-guide/IoT/README.md)를 참고한다. 호스트 `arduino-router`와 MCU 펌웨어는 앱 시작·종료 도구와 별도로 관리한다.
