# Qwen3-0.6B-4bit 리필 요청 해석 평가

실행: 2026-10-15 PDT / 2026-10-16 UTC. 사용자 지정 `http://won-macmini:8000`에 직접 요청했다. 보드 실행이나 로봇 동작은 하지 않았다.

## 결론

**현재 서버·프롬프트·non-thinking 설정은 빠르지만, 한국어 리필 요청을 자동 확정할 수준의 정확도는 보이지 않았다.** 이전에 제안한 ‘Qwen 한 번으로 정정·부정·문맥 해석’은 이 모델 배포에서 실증되지 않았다. 출력은 확인용 초안으로만 쓰고 버튼 선택/최종 확인을 유지해야 한다.

이는 모든 Qwen 모델의 성능 결론이 아니다. 서버 템플릿·실제 가중치·양자화·서빙 설정을 독립적으로 검사하지 않았고, `/v1/models`와 응답의 모델 이름으로 배포 식별만 확인했다. 현재 배포의 관측 결과다.

## 방법

- 모델 ID: `mlx-community/Qwen3-0.6B-4bit`.
- 구조화 요청 112회: v1 32문장×temperature 0/0.6, v2 48문장×temperature 0.
- 추가 진단 6회: UTF-8/Unicode escape 전달, 한국어·영어 단일 작업 비교. 별도 연결 확인 1회.
- 모든 구조화 호출은 `stream=false`, `max_completion_tokens=192`, `chat_template_kwargs.enable_thinking=false`. 지정 옵션의 서버 내부 적용은 별도 검증하지 않았다.
- v1: 영어 규칙 프롬프트. 열거 후보를 pipe로 제시한 schema 예제를 모델이 그대로 복사하는 실패가 있었다. 프롬프트 설계의 약점도 포함한 결과다.
- v2: 한국어 규칙·구체적인 JSON 예제 6개로 수정. v1의 실패를 본 뒤 수정했으므로 기존 32문장은 개발셋이다. 새 16문장을 별도 holdout으로 추가했고 해당 응답을 본 뒤 재튜닝하지 않았다. 모두 사람이 작성한 작은 합성 테스트이며 독립 현장 평가가 아니다.
- 각 요청은 별도 대화이고 `current_request`를 명시적으로 주입했다. 실제 여러 턴의 앱 통합 시험은 아니다.
- 검증은 intent/item/portion의 정확한 일치. cancel·clarify·noop은 item/portion=null이어야 한다. 단일 항목·normal/small 정책에 따른 정답이다.
- 파서 원문 그대로의 strict 점수와, 응답 전체를 감싼 단일 Markdown code fence만 제거한 normalized 점수를 분리했다. 틀린 필드값·문자열 null·메뉴·의도는 보정하지 않았다.

## 측정 결과

| 프롬프트 / 온도 | 건수 | strict 완전 일치 | fence 제거 후 완전 일치 | fence 제거 후 schema 유효 | 응답시간 중앙값 / p95 |
|---|---:|---:|---:|---:|---|
| v1 / 0 | 32 | 0/32 | 2/32 (6.3%) | 5/32 | 0.626 / 1.072초 |
| v1 / 0.6 | 32 | 0/32 | 3/32 (9.4%) | 6/32 | 0.602 / 0.850초 |
| v2 / 0 | 48 | 0/48 | 14/48 (29.2%) | 38/48 | 0.728 / 0.937초 |

v2 개발셋은 8/32 (25.0%), 새 holdout은 6/16 (37.5%). 표의 전체 v2 성적을 독립 holdout 성적으로 표현하면 안 된다. 작은 표본·각 설정 1회 실행이므로 온도 간 우열이나 반복 안정성을 확정하지 않는다.

strict 0점은 모든 구조화 응답에 코드 블록이 붙어서 직접 JSON 파싱이 실패한 결과다. **의미를 전혀 이해하지 못했다는 뜻은 아니다.** 다만 fence만 제거해도 성능이 충분해지지는 않았다.

v2 기존 32문장의 범주별 normalized 완전 일치:

| 범주 | 정답 |
|---|---:|
| 단순 주문 | 2/4 |
| 부정 후 대안 | 0/4 |
| 취소·거절 | 0/5 |
| 기존 요청의 문맥·정정 | 0/5 |
| 모호함·지원 밖 요청 | 3/7 |
| 인사·정보 질문 | 2/3 |
| 영어 주문 | 1/2 |
| 지시 변경 공격 | 0/2 |

취소 0/5에는 cancel 대신 clarify/noop으로 보류한 사례가 포함된다. 모두 주문으로 실행했다는 뜻은 아니다. 반면 fence 제거 및 schema 검증 후에도 **주문하면 안 되는 27건 중 5건이 유효한 refill로 나왔다**. 메뉴 정보 질문, 지원하지 않는 복수/대량 요청, 지시 변경 공격을 포함한다. 정답이 refill인 상황에서 다른 음식을 고른 오류는 이 5건과 별개다.

원본 결과의 `false_refill=0`은 strict parser에서 전부 탈락했기 때문이다. 운영에서 fence를 제거한다면 `qwen_analysis.json`의 `false_refill_after_normalization`을 읽어야 한다. 파싱 거부와 의미적 안전성을 혼동하지 않는다.

## 대표 실패 — v2 실제 응답에서 fence만 제거

| 입력 / 맥락 | 기대 | 실제 |
|---|---|---|
| 콩나물은 됐어요. 밥 조금 주세요 | refill / rice / small | refill / bean_sprouts / normal |
| 현재 김치 소량 → 콩나물로 바꿀게요 | refill / bean_sprouts / small | refill / kimchi / small |
| 현재 김치 보통 → 아니, 조금만 | refill / kimchi / small | clarify / null / null |
| 리필 가능한 반찬이 뭔가요? | noop / null / null | refill / kimchi / normal |
| 김치랑 콩나물 둘 다 주세요 | clarify / null / null | refill / kimchi / normal |

## 인코딩·단순 작업 진단

- 동일한 한국어 문장을 UTF-8 직접 전송과 JSON Unicode escape로 각각 전송했을 때, 두 응답 모두 원래 한국어 문장을 보존했다(마침표 추가). 이번 Python 경로의 한글 전송 손상이 낮은 점수의 주원인이라는 증거는 없다.
- 아주 짧은 음식 선택 프롬프트에서도 ‘김치 말고 콩나물 주세요’에 **김치**를 출력했다. 대응 영어 요청에는 `bean_sprouts`를 출력했다.
- 한국어 Yes/No 분류 진단에서는 지정한 라벨 대신 고객 문장을 반복했다. 영어 진단에는 `NO.`를 출력했다. 1건씩이므로 언어 전체 성능 차이의 통계적 증거는 아니다.
- 사용자의 `Hello! ð`는 UTF-8 이모지가 잘못 디코딩될 때 나타나는 형태와 일치하지만, 사용자가 받은 원본 바이트·응답 헤더를 확인하지 않아 확정하지 않았다. 평가 클라이언트는 요청을 UTF-8 bytes로 보내고 응답도 명시적으로 UTF-8 decode했다.
- 첫 연결 확인은 PowerShell→Python stdin 경로를 사용했으므로 한국어 정확도 평가에서 제외했다. 정식 평가·진단은 UTF-8 소스 파일에서 실행했다.

## 속도 해석과 미측정

시간은 Windows 클라이언트에서 측정한 HTTP 요청→전체 응답 수신 wall time이다. 네트워크·토큰화·prompt 처리·생성을 포함하며 모델 단독 latency가 아니다. 순차 요청·반복 프롬프트라 서버 prefix cache의 영향이 있을 수 있다. 서버 하드웨어/캐시 설정·동시 부하는 미확인이다.

- 112개 구조화 요청에서 HTTP 오류 0건, finish_reason은 모두 stop.
- TTFT, streaming token/s, 실제 peak RAM, cold-load, 장시간 동작, thinking=true, constrained JSON decoding은 측정하지 않았다.
- Mac의 MLX 4bit 결과를 VENTUNO Q의 ExecuTorch/QNN 번들 성능으로 옮겨 적으면 안 된다. 양자화·tokenizer·template·backend가 달라질 수 있다.

## 프로젝트 판단

1. 현재 설정으로 한국어 자유 발화를 바로 실행 권한으로 연결하지 않는다.
2. JSON fence 제거는 형식 문제만 해결한다. 문맥·부정 오류를 해결하지 않는다.
3. 서버의 chat template·tokenizer·실제 모델과 옵션 적용을 먼저 확인할 가치가 있다. 서버 설정을 이번 평가에서 변경하지 않았다.
4. 다음 비교는 같은 테스트에서 thinking on/off 또는 다른 크기의 모델을 하나씩 바꾸어 수행한다. 모델 추가 설치·서버 변경은 이번 작업에 포함하지 않았다.
5. 여러 Qwen 호출이나 LangChain 추가가 이번 오류를 해결한다는 증거는 없다. 단순한 입력·명시적 요청 카드·물리 확인을 유지한다.

## 재현

저장된 결과를 먼저 읽는 것은 서버 요청을 발생시키지 않는다. 아래 첫 두 명령은 총 112회의 새 추론 요청을 수행한다.

```powershell
python evaluation/refill_qwen_eval.py --output evaluation/qwen_refill_results.json
python evaluation/refill_qwen_eval.py --prompt v2 --temperatures 0 --holdout --output evaluation/qwen_refill_v2_results.json
python evaluation/analyze_qwen.py
python evaluation/qwen_diagnostics.py
```

재실행 시 같은 파일을 덮어쓴다. 기존 결과를 보존하려면 evaluator의 `--output`에 새 파일명을 주고 분석 입력도 맞춘다. 원본 JSON에는 요청 문장·기대값·raw 응답·시간·usage·프롬프트와 hash가 보존되어 있다. 실제 고객 데이터는 사용하지 않았다.

파일:
- [평가 클라이언트·사례·프롬프트](refill_qwen_eval.py.md)
- [v1 원본 응답](qwen_refill_results.json.md)
- [v2 원본 응답](qwen_refill_v2_results.json.md)
- [형식 보정 후 분석](qwen_analysis.json.md)
- [인코딩·단순 작업 진단](qwen_diagnostics.json.md)
