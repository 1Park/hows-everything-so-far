# HardwareIO

Controller 내부에서 사용하는 물리 입출력 모듈이다. 별도 HTTP 서버가 아니다.

- Mock 구현: 보드 없이 LED·시퀀스를 로그로 표현하고 가짜 센서·버튼 입력 제공
- Bridge 구현: Arduino Bridge를 통해 MCU의 등록된 메서드 호출

동일한 인터페이스로 LED 갱신·버튼/센서 입력·mock 적재/복귀·취소를 처리한다. 구체적인 메서드 계약은 MCU sketch와 함께 정한다. MCU 코드는 `firmware/`에 둔다.

고객 확인·취소·중복 명령 검증은 Controller가 담당한다. 화면·스피커 재생은 `app/ui/`의 역할이다.
