# 모델 파일

모델·tokenizer·native binary는 Git에 넣지 않는다. `models/local/`, `models/board/`, `models/experiments/`를 용도별로 사용하거나 명시적 외부 경로를 지정한다. 경로만 설정해도 backend가 자동 선택되지는 않는다.

| 사용처 | 실제 설정·파일 |
| --- | --- |
| Vision | `VISION_MODEL_BACKEND=external`, `VISION_ADAPTER=services.vision.backend:create_backend`, `VISION_MODEL_PATH`는 bundle 디렉터리 (`bundle.json`, `.pte`, head) |
| 보드 Vision native worker | `VISION_WORKER_BIN`, 서비스 시작 시 YOLO/DINO preload. 빌드·배포는 [Vision 안내](../services/vision/README.md) |
| 보드 Gemma4 | `QWEN_MODEL_BACKEND=executorch`, `QWEN_MODEL=gemma4`. 파일 경로는 `scripts/board_llm.sh config`로 확인 |
| 개발 Mac LLM | HTTP 연결. 로컬 모델 파일을 읽지 않음 |
| 선택적 Qwen CLI | `QWEN_MODEL_BACKEND=qwen_cli`, runner/model/tokenizer/seq_len 설정. 보드 기본 Gemma 경로와 별개 |
| STT | `STT_MODEL_BACKEND=external`, Whisper HTTP adapter와 `STT_WHISPER_URL`. 모델은 외부 whisper.cpp 서버 소유 |

`STT_MODEL_PATH` 설정은 현재 코드에 없다. 실제 파일 요구사항·경로 해석은 각 backend가 정의한다. Vision bundle 상대 경로는 레포 루트 기준이다.

모델 로딩·전후처리는 해당 서비스 backend에 둔다. Controller는 API를 호출하고 카메라·마이크를 단독 소유한다. 파일 누락·로드 실패는 명시적 오류로 처리하고 fixture로 자동 대체하지 않는다.

[보드 실행](../docs/BOARD_RUNBOOK.md), [LLM](../services/qwen/README.md), [Vision](../services/vision/README.md), [STT](../services/stt/README.md), [학습·export](../ml/README.md).
