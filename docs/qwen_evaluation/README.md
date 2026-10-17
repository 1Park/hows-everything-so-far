# 평가 자료 인덱스

## 현재 음료 앱 평가

실행: 로컬 integration 모드에서 `python scripts/evaluate_qwen.py --proxy`. temperature=0, 원본/raw·제품 프롬프트·모델 ID·dataset hash를 timestamp **신규 JSON**으로 저장한다. 기존 Markdown 아카이브는 그대로 보존한다.

- [최종 음료 평가17/20](drinks-20261017T061614204547Z.json): Controller와 같은 프롬프트, 우리 proxy→실제 Mac MLX, HTTP 중앙값0.679초. 개발 평가셋이며 일반화/보드 성능 주장이 아니다.
- [첫 실제 평가15/20](drinks-20261017T060722867674Z.json), [초기 transport 계약 실패](drinks-20261017T060535441028Z.json)도 보존.
- 상세 실패·범위는 [검증 보고서](../VALIDATION.md).

아래 내용은 과거 자료를 Markdown으로 이전했을 당시의 아카이브 설명이다.

이번 이전은 사용자 요청에 따라 **새로 추가하는 자료를 전부 Markdown**으로 저장했다. 기존 대회 가이드는 건드리지 않았다. `.py.md`와 `.json.md`는 원본을 단일 4-backtick 코드 블록에 보존한 아카이브이며, 확장자만 바꾼 실행 파일이 아니다.

## 읽는 순서

- [현재 아키텍처](../ARCHITECTURE.md)
- [영어 전용 평가](QWEN_ENGLISH_EVALUATION.md) — 영어 프롬프트의 과거 평가
- [STT 유사발음 치환 평가](QWEN_STT_EVALUATION.md)
- [과거 한국어/혼합 평가](QWEN_EVALUATION.md) — 비교·실험 이력용, 제품 언어 기준 아님

## 평가 범위와 보존 원칙

평가 메뉴 `kimchi/bean_sprouts/rice`와 분량 `normal/small`은 당시 텍스트 평가 계약이다. 현재 water / coke / coffee 컵 데모나 비전 라벨의 검증 결과가 아니다. 원본 프롬프트·결과는 보존하고 음료용 변경과 재실행은 별도 파일로 관리한다. **향후 평가는 temperature 0**을 사용한다.

## 실행 환경과 결과 요약

- Windows Python 클라이언트 → Mac 서버 `http://won-macmini:8000/v1/chat/completions`, 모델 ID `mlx-community/Qwen3-0.6B-4bit`. 모델 ID는 API에서 확인했지만 서버 실제 가중치·template·옵션 적용·하드웨어는 독립 감사하지 않았다.
- `system` 공통 규칙·예제와 `user` JSON `{current_request, utterance}`를 전달했다. 전체 대화 이력은 전달하지 않았다. `enable_thinking=false`, `stream=false`, `max_completion_tokens=192`를 요청했다.
- 영어 48상황: temperature 0에서 21/48, 0.6에서 22/48. 온도 0에서 non-refill 27건 중 유효한 refill 오출력은 10건이다.
- STT 합성 치환 24쌍: clean 18/24, noisy 11/24. clean 정답 18개 중 11개 유지, 유효 출력 동일 14쌍에는 둘 다 오답인 3쌍이 포함된다. `rice→rise` 복구는 문맥에 따라 달랐고 `Not→Knot`, `Cancel→Council`는 주문·취소 해석 오류를 일으켰다.
- 정확도는 Markdown fence만 제거한 뒤 intent/item/portion을 모두 비교했다. 필드값은 수정하지 않았고 fence 때문에 raw JSON strict 파싱은 실패했다.
- STT 셋은 실제 음성 인식 결과가 아닌 유사발음 텍스트 치환이다. 18개 원문 상황을 24쌍으로 확장했고, 보정 지시를 추가하지 않은 동일 프롬프트로 비교했다. 영어 전체 평가와 정확도를 직접 비교하지 않는다.
- HTTP 전체 응답 시간 중앙값은 약 0.6–0.7초다. 보드 latency·TTFT·token throughput·cold start·RAM은 미측정이다. MLX와 보드 ExecuTorch는 runtime·quantization이 다를 수 있다.

이 결과는 당시 구성의 기록이며 Qwen의 일반 성능이나 현재 사용자가 시험한 구성의 정확도를 단정하지 않는다. 보드 실행 검증과도 구분한다. 새 기기에서는 Tailscale 및 `won-macmini` 이름 해석을 확인한다. `localhost`는 해당 기기 자신을 가리키므로 공용 Mac endpoint의 대체 주소가 아니다.

## 정확한 프롬프트·코드 링크

- [영어 system prompt와 발화 48개](english_cases.py.md)
- [평가 요청 생성 코드](refill_qwen_eval.py.md) — system/user 둘 다 설정, user는 current_request와 utterance의 JSON 문자열
- [STT 원문·치환 셋 생성 코드](stt_cases.py.md)
- [일반 분석 코드](analyze_qwen.py.md)
- [쌍별 STT 분석 코드](analyze_stt.py.md)
- [인코딩·단순 작업 진단 코드](qwen_diagnostics.py.md)

## 원본 데이터·결과

- [영어 raw 응답](qwen_english_results.json.md), [영어 분석](qwen_english_analysis.json.md)
- [STT 데이터셋 manifest](stt_manifest.json.md), [STT raw 응답](qwen_stt_results.json.md), [STT 쌍별 분석](qwen_stt_analysis.json.md)
- [과거 v1 raw](qwen_refill_results.json.md), [과거 v2 raw](qwen_refill_v2_results.json.md), [과거 분석](qwen_analysis.json.md)
- [인코딩 진단 결과](qwen_diagnostics.json.md)

각 아카이브 머리말의 SHA-256은 **이전 전 원본 파일 바이트**의 hash다. Markdown 저장 및 복원 과정에서 줄바꿈이 정규화될 수 있으므로 복원된 파일의 바이트 hash가 같다는 의미는 아니다. 코드·JSON 내용은 보존했다.

## 실행 파일로 복원

레포 루트에서 아래 Python 코드를 실행한다. 이미 파일이 있으면 중단하며, 네트워크 요청이나 모델 실행은 하지 않는다. 새 `evaluation/` 폴더에 6개 Python 파일과 9개 JSON 파일을 복원한다. `.md` 보고서는 여기 그대로 둔다.

```python
from pathlib import Path

source = Path("docs/qwen_evaluation")
target = Path("evaluation")
archives = sorted(source.glob("*.py.md")) + sorted(source.glob("*.json.md"))
planned = []
for archive in archives:
    destination = target / archive.name.removesuffix(".md")
    if destination.exists():
        raise FileExistsError(destination)
    text = archive.read_text(encoding="utf-8")
    language = "python" if archive.name.endswith(".py.md") else "json"
    marker = "````" + language + "\n"
    payload = text.split(marker, 1)[1].rsplit("\n````", 1)[0] + "\n"
    planned.append((destination, payload))
target.mkdir(exist_ok=True)
for destination, payload in planned:
    destination.write_text(payload, encoding="utf-8")
print(f"Restored {len(planned)} files")
```

Python 표준 라이브러리만 사용하는 평가 클라이언트다. 서버의 모델 설치는 별개다. 복원 후 레포 루트에서 아래 명령으로 **새 결과 파일**을 만들 수 있다. 실행하면 각각 48회 HTTP 추론 요청이 발생한다.

```sh
python evaluation/refill_qwen_eval.py --prompt en --temperatures 0 --holdout --output evaluation/qwen_english_rerun.json
python evaluation/analyze_qwen.py --inputs qwen_english_rerun.json --output qwen_english_rerun_analysis.json
python evaluation/refill_qwen_eval.py --prompt en --temperatures 0 --stt --output evaluation/qwen_stt_rerun.json
```

주의: STT 실행은 출력명과 무관하게 `evaluation/stt_manifest.json`을 재생성한다. Markdown 원본은 변하지 않는다. `analyze_stt.py`는 현재 `qwen_stt_results.json`을 고정 입력으로 읽으므로 새 rerun을 분석하려면 작업 복사본의 입력/출력 경로를 먼저 변경한다. 기존 결과와 새 실행을 섞지 않는다.

보고서 내부 재현 명령은 **당시 실행 기록**으로 원래 파일명을 덮어쓸 수 있다. 향후 온도는 0을 사용하고, 재실행에는 위처럼 새 결과명을 지정한다. 온도 0.6·한국어는 과거 비교 이력만 보존했다.
