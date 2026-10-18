# 검증

현재 테스트·코드가 기준이다. 고정된 통과 개수·실행 중 PID·배포 상태는 이 문서에서 관리하지 않는다. 테스트는 fixture/가짜 backend로 동작을 검증하며 실제 모델 정확도·NPU 지연·물리 장치를 대신하지 않는다.

## Python

```sh
python -m pytest -q
python -m ruff check app common services scripts tests
```

정책·스키마·HTTP·취소/확인 경쟁·모델 worker 수명·자동 캡처·supervisor 종료/재시작을 검사한다. Unix-domain socket이 없는 플랫폼에서는 Router wire 테스트를 skip한다. 카메라 파일 테스트는 선택 OpenCV 의존성이 필요하다.

## 브라우저

```sh
npm ci
npx playwright install chromium
python scripts/dev.py --mode offline
# 별도 터미널
npm run test:browser
npm run test:ui-regressions
REFILL_URL=http://127.0.0.1:8080 node scripts/browser_auto_capture.cjs
```

보드 음성 흐름은 별도 설정으로 검사한다:

```sh
AUDIO_INPUT=fixture CAPTURE_MODE=auto CONTROLLER_PORT=8090   python scripts/dev.py --mode offline
REFILL_URL=http://127.0.0.1:8090 npm run test:board-voice
```

환경변수 예시는 POSIX shell 기준이며 PowerShell에서는 `$env:이름='값'`으로 설정한다. `REFILL_URL`로 앱 주소, `CHROME_PATH`로 설치된 Chrome을 지정할 수 있다. 결과는 `tmp/browser-qa/`에 쓴다. 기본 브라우저 검사는 가상 마이크를 사용한다.

## 실제 모델·보드

- `python scripts/smoke.py`: 실행 중 Controller의 요청·수정·Confirm·취소·STT·skip 흐름.
- `python scripts/evaluate_gemma.py --help`: 원본20/합성 왜곡20을 현재 제품 프롬프트로 평가. 새 결과에 prompt input/output/시간을 저장한다.
- `python scripts/benchmark_vision_residency.py --help`: 동일 bundle·이미지로 CLI/상주 지연과 출력 동등성 비교.
- 현장에서는 실제 이미지/음성, 장치 단절, 태블릿 청취, Bridge/MCU watchdog을 별도로 확인한다.

과거 기록은 [Gemma](gemma_evaluation/README.md), [Qwen](qwen_evaluation/README.md), [Vision](vision_evaluation/README.md), [STT](stt_evaluation/README.md)에 보존한다. 이전 스키마·프롬프트·bundle 결과를 현재 코드의 성능으로 해석하지 않는다.
