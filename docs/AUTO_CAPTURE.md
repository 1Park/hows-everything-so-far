# 자동/수동 캡처

실행 위치: Controller Python 프로세스(`app/capture.py`). 기존 단일 `VideoSource`와 Vision HTTP/fixture API를 사용한다. DINO/YOLO 상주 worker·가중치·검출/crop·전후처리는 변경하지 않는다.

## 사용

UI의 **Demo tools & diagnostics → Capture mode → Automatic**을 선택한다. 카메라는 계속 live로 보이고 종류 안정성 진행 시간을 표시한다. 처음 선택할 때 브라우저 스피커도 활성화한다. 이후 페이지를 새로고침하면 브라우저 정책상 Enable sound를 다시 눌러야 할 수 있다.

1. 기본 0.5초 간격(초당 2회)으로 최신 원본 이미지를 Vision에 전달한다. 동시에 여러 추론을 요청하지 않으며 느린 호출은 기다린다.
2. **객체 수와 종류별 개수**가 3초간 같아야 한다. 예: water 1 / coffee 2 / unknown 1. object_id·검출 순서·박스 좌표·잔량은 종류 안정성 기준이 아니다. 물체 추적/위치 고정 판정은 구현하지 않는다.
3. 객체가 없거나 개수/종류/source가 바뀌거나 호출/카메라 오류가 발생하면 안정성 구간을 다시 시작한다. 정상 간격의 3배(최소 1초)보다 큰 관측 공백도 구간을 리셋한다.
4. 3초 구간에서 **둘 이상 bbox가 겹치는 영역의 합집합 면적**이 가장 작은 이미지를 선택한다. 면적은 원본 대비 normalized 면적이며 세 박스가 겹쳐도 같은 영역을 중복 계산하지 않는다. 동률이면 최신 이미지를 선택한다.
5. 선택 이미지와 그 이미지의 정확한 VisionResult를 함께 freeze한다. 추가 Vision 호출 없이 기존 Controller 정책→안내→보드 녹음→STT→LLM→요청 접수 흐름으로 이어진다. Confirm 사용 여부는 `REQUIRE_CONFIRMATION` 설정을 따른다. 충분한 잔량/낮은 신뢰도/unknown만 있는 장면은 기존 정책대로 skip한다.

**Manual**은 기존 Start demo / Inspect again 버튼으로 즉시 캡처한다. 자동 모드에서 Start 위치의 **Restart auto capture**는 안정성 구간을 새로 시작하며 즉시 freeze하지 않는다. 자동 모드에서도 이미지 업로드로 시작하려면 Manual로 전환한다. 주기적 스캔은 항상 카메라/서버 영상 입력과 normal 시나리오를 사용한다.

## 재시작·취소·중복

- 고객 응대·LLM 처리·카드·mock 시퀀스 중에는 스캔을 중단한다. 진행 중 mode 변경은 기존 요청/카드를 취소하거나 새로 승인하지 않는다.
- 기본은 완료·거절·취소·skip·오류 후 **10초 대기 → 자동 재시작 → 새 3초 안정성 판정**이다. 대기 중에는 영상만 live로 표시하고 Vision 검사는 쉬며, 같은 종류·개수 구성도 재시작 후 다시 검사한다. 첫 시작과 응대 진행 중에는 타이머가 동작하지 않는다.
- Restart auto capture 옆에서 남은 시간을 확인한다. Demo tools의 자동 재시작 체크박스로 끄거나 대기 시간을 1–300초로 바꿀 수 있다. 대기 중 시간 변경은 변경 시점부터 다시 센다. 수동 재시작은 즉시 대기를 해제하고, Manual 전환은 타이머를 취소한다.
- 타이머를 끄면 같은 구성은 재안내하지 않는다. 객체 구성 변경/빈 장면 관측 후 다시 안정되거나 Restart auto capture로 시작한다.
- Manual 전환·취소·수동 시작 후 도착한 옛 Vision 결과는 mode epoch와 Controller token으로 폐기한다.
- UI 모드는 Controller 프로세스에서 관리하므로 새 탭/새로고침에도 유지된다. 서버 재시작 시 환경 설정 기본값을 다시 적용한다.

## 비용

정확한 겹침 면적은 x sweep + y segment tree로 **O(n log n) 시간 / O(n) 메모리**, 계약상 n≤50. 모든 사진을 저장하지 않고 현재 최적 JPEG+VisionResult 한 쌍만 보관한다(이미지 한 장은 기존 max_image_bytes 제한 적용).

2026-10-17 로컬 Windows/Python 3.13 CPU, 각 2,000회 반복 평균: 박스 3개 **0.022ms**, 50개 **1.062ms**. Vision 추론·JPEG capture·HTTP는 제외한 면적 계산만의 측정이며 보드 실측이 아니다. 주최 측 Vision 상주 성능은 별도 기록을 따른다.

## 설정·계약

```dotenv
CAPTURE_MODE=manual
AUTO_CAPTURE_INTERVAL_SECONDS=0.5
AUTO_CAPTURE_STABLE_SECONDS=3
AUTO_CAPTURE_RESTART_ENABLED=true
AUTO_CAPTURE_RESTART_SECONDS=10
OBSERVE_INTERVAL_SECONDS=0
```

기본은 기존 수동 모드이며 UI에서 자동 모드로 바꾼다. 처음부터 자동이면 CAPTURE_MODE=auto. 기존 OBSERVE_INTERVAL_SECONDS>0 설정은 자동 모드 활성화/샘플 간격으로 호환하되 **3초 안정성 판정도 적용**한다. 새 설정에는 AUTO_CAPTURE_*를 권장한다.

- `GET /api/capture` → CaptureStatus
- `POST /api/capture`, JSON `{"mode":"auto"}` 또는 `{"mode":"manual"}` → CaptureStatus. auto→auto는 명시적 재시작.
- `POST /api/capture/restart-timer`, JSON `{"enabled":true,"seconds":10}` → CaptureStatus. 설정과 카운트다운은 Controller가 관리하며 새로고침·여러 탭에서도 공유한다. 서버 재시작 시 env 기본값을 적용한다.
- `/api/state` 및 기존 WS state에 `capture` 포함.
- 별도 WS 이벤트: `{"type":"capture","instance_id":"…","capture":{…}}`. capture.revision으로 늦은 응답을 무시한다. 진행도는 Controller sequence를 올리지 않아서 안내 종료 ACK/Confirm을 무효화하지 않는다.
- 상태: manual / scanning / stabilizing / paused / waiting / cooldown / error. `restart_remaining_seconds`는 대기 중에만 값이 있다. source=fixture는 실제 추론이 아니다.

## 로컬 검증

`tests/test_auto_capture.py`: 면적 독립 grid oracle·3중 겹침, 3초 전 시작 금지·종류/개수/공백/빈 장면 reset, 최적 이미지와 결과의 동일성·재추론 없음, 응대 중 pause·중복 방지, mode/수동 시작/취소와 늦은 결과 경쟁, 오류 복구·HTTP 입력 검증.

실제 Chrome `scripts/browser_auto_capture.cjs`: 기본 3초 자동 시작·새로고침 유지·선택 snapshot/bbox 정합·진행 중 mode 변경 시 세션 보존·재시작 구간 reset·1440/390px 화면. 이 브라우저 검증은 fixture Vision을 사용했으며 실제 보드 카메라 정확도/지연/실물 음성 검증과 구분한다.

[2026-10-17 보드 배포·실제 Vision 샘플링 기록](auto-capture-deployment-20261017.md).
