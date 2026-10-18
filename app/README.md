# Controller

`server.py:create_app` FastAPI, 기본8080. `controller.py` 상태 머신·정책·확인/취소·late-result 무효화, `clients.py` Vision/STT fixture/HTTP 및 Qwen HTTP, `language.py` 영어 제품 프롬프트/strict parser, `media.py` 단일 영상 소유·transport.

실행은 루트에서 `python scripts/dev.py`. 환경·API·검증은 [루트](../README.md), [계약](../docs/CONTRACTS.md). UI와 모델 서버의 상태를 Controller만 변경한다. 모델/주행 구현은 포함하지 않는다.

`capture.py`는 수동/자동 캡처와 5초 종류 안정성·최소 bbox 겹침 프레임 선택을 담당한다. 기존 Vision API/상주 worker를 호출하며 모델 전처리에는 관여하지 않는다. [자동 캡처 동작·복잡도·검증](../docs/AUTO_CAPTURE.md).
