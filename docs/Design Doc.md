## Refill Assist — Spec (Draft)

> 과거 기획 초안이다. 최신 모델 선택·컵 데모·다중 객체 검출·실행 구조는 [ARCHITECTURE.md](ARCHITECTURE.md)를 우선한다.

ExecuTorch Hackathon · IoT Track (Arduino VENTUNO Q) Status: rough draft · 2026-10-15 Working title: Tabletop Refill Assist (on-device dish type \+ fill-level classification)

### 1\. One-liner

서빙 로봇이 테이블에 멈춘 뒤, 접시 잔량·반찬 종류를 온디바이스로 분류하고 LED로 상태를 띄운 다음, 음성(또는 버튼)으로 확인받으면 접시를 주방으로 가져가는 흐름을 mock으로 보여준다.

On-device refill assist: classify side-dish type and fill level, signal via LED, confirm by voice/button, then mock-return the plate to the kitchen.

### 2\. Problem

서빙/리필 로봇이 클라우드 비전·상시 연결에 의존하면 매장 프라이버시·지연·단절에 취약하다.

"거의 다 먹음"을 사람이 매번 부르지 않아도 되게 하려면 잔량 \+ 종류 인식이 테이블 사이드에서 끝나야 한다.

과신(low conf인데 집어 감)은 스필·컴플레인 리스크 → 물어보고 움직일지 결정권은 사람.

### 3\. Goals / Non-goals

#### Goals (Must)

| ID | Goal |
| ----- | ----- |
| G1 | 테이블 접시 & 컵 이미지(또는 카메라 프레임) → dish\_type \+ fill\_level \+ confidence on-device 추론 |
| G2 | 추론 결과를 LED 색/패턴으로 MCU에 표시 (Bridge) |
| G3 | fill이 low/empty 이고 conf 충분할 때만 리필 제안 |
| G4 | 확인(Yes) 시 mock load → kitchen return 시퀀스 실행 및 로그 |
| G5 | 동일 입력으로 재시작 후에도 같은 판정·LED·시퀀스 재현 가능 |
| G6 | ExecuTorch \+ (가능하면) QNN HTP 경로 사용; Linux 추론 → MCU 반응 루프 닫기 |

#### Non-goals (Out of scope)

실제 자율 주행 / 테이블 순회 네비게이션

6DOF 그리퍼·접시 이적 기구학·힘제어

전체 메뉴판·미세 음식 세그멘테이션·그램 단위 계량

풀 대화형 LLM 주문 시스템

클라우드 추론·원격 모니터링 대시보드

다인 테이블 동시 다중 접시 스케줄링 (데모는 1 ROI 또는 1 primary dish)

### 4\. User story (데모 페르소나)

손님이 반찬을 거의 다 먹었다.

서빙봇이 테이블에 정차했다고 가정한다 (데모는 고정 카메라/고정 컷).

시스템이 접시를 보고 kimchi / low / 0.91을 낸다.

LED가 종류색으로 펄스, 안내: "거의 다 드셨네요. 가져다드릴까요?"

손님이 "네" (또는 Yes 버튼).

봇이 접시를 싣고 주방으로 간다고 가정 (LED/모터 mock \+ 상태 로그).

잔량 충분하거나 conf 낮으면 제안하지 않는다.

### 5\. System architecture

\[Camera / still image\] │ ▼ ┌───────────────────────┐ │ Linux (QCS8275) │ │ \- capture / load │ │ \- preprocess │ │ \- ExecuTorch .pte │ ── QNN HTP ──► Hexagon NPU │ \- policy (thresholds)│ │ \- TTS/prompt text │ │ \- yes/no listener │ └───────────┬───────────┘ │ Arduino Bridge (MessagePack-RPC) ▼ ┌───────────────────────┐ │ MCU (STM32H5) │ │ \- set\_led(color, pat)│ │ \- mock\_actuate(...) │ servo / motor driver / buzzer │ \- optional button │ └───────────────────────┘

​

원칙

인식·정책·프롬프트는 Linux.

시간 민감 GPIO·LED·mock 모터는 MCU.

Bridge 핸들러는 짧게; nested RPC 금지.

### 6\. Hardware assumptions

| Piece | Plan | Notes |
| ----- | ----- | ----- |
| Board | Arduino VENTUNO Q | IoT track device |
| Compute | Dragonwing IQ8 / QCS8275, Ubuntu | ExecuTorch runtime |
| NPU | Hexagon via QNN HTP | claim only after profile |
| MCU | STM32H5 \+ Arduino Bridge | LED \+ mock actuators |
| Vision input | USB/CSI cam or curated stills | stills \= reliability fallback |
| LED | RGB LED or Modulino LED | type color \+ fill pattern |
| Confirm input | Mic keyword or button or terminal y/n | button always as backup |
| Arm/drive | Mock only | optional 1–2 servos for motion theater |
| Audio out | Board speaker / headphone / console print | TTS optional |

### 7\. Labels & outputs

#### 7.1 fill\_level (required)

| Label | Meaning | Refill candidate? |
| ----- | ----- | ----- |
| full | 거의 안 줄음 | No |
| mid | 절반 전후 | No (default) |
| low | 리필 제안 구간 | Yes |
| empty | 거의/완전 비움 | Yes |

#### 7.2 dish\_type (v1 set — adjustable)

| Label | LED base color (draft) |
| ----- | ----- |
| kimchi | Red |
| soup | Blue |
| rice | White |
| meat | Yellow |
| side\_other | Green |
| unknown | Purple slow blink |

v1 데모는 3종(kimchi, soup, rice) \+ unknown으로 줄여도 됨.

#### 7.3 Model output schema

{ "dish\_type": "kimchi", "fill\_level": "low", "confidence": 0.91, "roi": \[x, y, w, h\], "timestamp\_ms": 0 }

​

confidence: 타입·잔량 중 의사결정에 쓰는 점수 (min(type\_conf, fill\_conf) 또는 joint conf).

multi-dish는 v1에서 primary ROI 1개 (중앙/최대 접시).

#### 7.4 Policy thresholds (draft)

| Param | Draft | Behavior |
| ----- | ----- | ----- |
| CONF\_MIN | 0.70 | 미만 → no prompt, purple/skip |
| REFILL\_LEVELS | {low, empty} | 이외 → no prompt |
| LISTEN\_TIMEOUT\_S | 8 | 무응답 → skip |
| COOLDOWN\_S | 15 | 같은 테이블 재프롬프트 방지 |

### 8\. State machine

IDLE → CAPTURE → INFER → DECIDE ├─ (not refill candidate) → INDICATE\_OK → IDLE ├─ (low conf / unknown type) → INDICATE\_UNCERTAIN → IDLE └─ (refill candidate) → PROMPT → LISTEN ├─ YES → LOAD\_MOCK → RETURN\_MOCK → COMPLETE → IDLE ├─ NO → CANCEL → IDLE └─ TIMEOUT → CANCEL → IDLE ※ 전 상태에서 FAULT 가능 → safe LED \+ log → IDLE

​

#### State → LED (draft)

| State | LED |
| ----- | ----- |
| IDLE | Off or dim white |
| INFER | Soft white blink |
| INDICATE\_OK (full/mid) | Type color solid 1s → off |
| INDICATE\_UNCERTAIN | Purple slow blink 2s |
| PROMPT | Type color pulse |
| LISTEN | Type color fast pulse |
| LOAD\_MOCK | Cyan solid / motion pattern |
| RETURN\_MOCK | Cyan chase / moving pattern |
| COMPLETE | Green 2s |
| CANCEL | Amber 1s |
| FAULT | Red fast blink |

### 9\. Software modules

refill\_assist/ app/ main.py state\_machine.py policy.py prompt.py listen.py vision/ capture.py preprocess.py infer\_et.py labels.py mcu/ sketch/ led\_map.py assets/ samples/ prompts/ tools/ eval\_samples.py demo\_script.md models/

​

### 10\. Interfaces

#### 10.1 MCU Bridge methods (draft)

| Method | Direction | Args | Behavior |
| ----- | ----- | ----- | ----- |
| set\_led | Linux → MCU | mode or (r,g,b, pattern) | LED update |
| start\_sequence | Linux → MCU | name: load / return / abort | mock motion theater |
| get\_button | Linux → MCU | — | last yes/no/none |
| ping | Linux → MCU | — | health |

MCU sketch responsibilities:

Bridge.begin() \+ provide\_safe for GPIO-touching handlers.

Sequence \= timed servo/LED pattern; no blocking forever; abortible.

No nested Bridge.call inside handlers.

#### 10.2 Linux policy API (draft)

def decide(result: InferResult) \-\> Action: \# returns Skip | Prompt | Fault def on\_confirm(yes: bool) \-\> None: \# drives LOAD\_MOCK / CANCEL via Bridge

​

#### 10.3 Prompt copy (KO / EN)

| Event | KO | EN |
| ----- | ----- | ----- |
| Offer | "{dish} 거의 다 드셨네요. 가져다드릴까요?" | "You're running low on {dish}. Shall I bring more?" |
| Yes ack | "네, 주방으로 옮길게요." | "Got it. Returning to the kitchen." |
| No ack | "알겠어요." | "Okay." |
| Uncertain | "잘 모르겠어요. 패스할게요." | "Not sure — skipping." |

### 11\. Model plan

#### Phase A — smoke (day start)

Track bundle install: runners \+ add.pte

Bridge LED blink

DINOv2 bundle run or smallest available vision path

#### Phase B — product path (hack target)

Preferred (fast, stable)

Backbone: supplied DINOv2 (or embeddings from fixed crops)

Head: few-shot prototypes / linear classifier on dish\_type × fill\_level sample grid

Export path optional; if timebox hits, Python head on embeddings still OK for demo if ET backbone runs on device — document honestly

Fallback

fill\_level only via simple ROI heuristics \+ type forced by demo placard

Still keep ET somewhere in the loop so track story holds

#### Phase C — stretch

Custom .pte joint classifier, QNN HTP profile vs CPU

Keyword spotter on-device for 네/아니요

Multi-ROI top-1 dish selection

Explicit non-commitment: full Qwen dialog not required; hardcoded offer sentence preferred.

### 12\. Demo scenarios (acceptance)

| \# | Input | Expect |
| ----- | ----- | ----- |
| D1 | kimchi \+ low still | type/level correct-ish, red pulse, offer, Yes → load/return mock |
| D2 | rice \+ full still | no offer (or brief OK indicate) |
| D3 | ambiguous / dark crop | uncertain LED, no motion |
| D4 | D1 again after restart | same decision path reproducible |
| D5 | Offer then No | cancel, no return sequence |

90-second run of show

0:00 문제 한 줄 \+ 아키텍처 한 장

0:20 D1 live/still

0:45 Yes → mock return

1:00 D2 or D3 contrast

1:15 on-device / no cloud / conf gate 한 줄

1:30 stop

### 13\. Success criteria

#### Demo success

G1–G5 visible in one continuous run

At least one ExecuTorch model invocation on board path

LED differs meaningfully by state/type

Yes path and skip/uncertain path both shown

Team can rerun cold-start without babysitting

#### Nice-to-have

HTP vs CPU latency note

Sample-set top-1 accuracy table (even n=30)

Physical button confirm

One moving servo as theater

### 14\. Risks & mitigations

| Risk | Mitigation |
| ----- | ----- |
| Track model bundle late | Curated stills \+ offline-ready pipeline; LED/Bridge first |
| dish\_type accuracy poor | Shrink label set; unknown \+ conf gate; demo-only dishes |
| fill\_level subjective | Coarse 4-bin; labeled sample card on table |
| Mic flaky | Button \+ stdin always on |
| robot walks disbelief | Pitch as table stop assist; motion clearly mock |
| Nested Bridge deadlock | provide\_safe, short handlers, single Linux owner loop |
| Overclaim NPU | Profile before saying NPU-accelerated |

### 15\. Build order (suggested)

Spec freeze v0.1 (this doc) — label set \+ LED map

MCU: set\_led \+ start\_sequence

Linux: state machine dry-run with fake InferResult

Board: add.pte / DINOv2 smoke

Sample stills grid (type × level, ≥3 each)

Real infer → policy → LED

Confirm path (button first, voice later)

Demo script rehearsal ×3 cold start

### 16\. Open questions

최종 dish\_type 목록 (3종 vs 5종)

카메라 실기 vs still-only

음성: keyword / 버튼 only / 둘 다

팀 역할 분담 (vision / MCU / demo PM)

트랙 번들 수령 경로 (HackerSquad / Discord)

프로젝트 공개 이름·레포명

### 17\. References

Hackathon: ExecuTorch Hackathon (Open Source AI Week), Founders Inc. SF · IoT track

Device guide: aaishikasb/qc-executorch-guide → IoT/README.md

Hardware: Arduino VENTUNO Q, Bridge docs

### Changelog

| Date | Note |
| ----- | ----- |
| 2026-10-15 | v0.1 rough spec from team direction (refill classification \+ LED \+ confirm \+ mock kitchen return) |

—

### Todo

1. Qwen 0.6B 성능 평가 (사용자 답변을 판단해서 다음 행동 판단)  
2. Dinov2 성능 평가 (이미지 처리)  
3. 음성모델 들어갈 자리 있을지? 번들에 있는 Qwen3 모델이 음성인식이 안될듯  
   \>\> 마이크 없을 가능성이 높으니까 음성인식은 목업으로 해도 되고, 다른 기기에 음성인식 붙여서 결과만 사용해도 되고. 말하는거 자체는 하드코딩한거 읽게 해도 되고  
4. STT는 좋은모델, TTS는 목업 (일단 나머지 구현 되면 생각해보기)  
5. 아키텍처 구상  
   1. ros 쓸건지 \-\> rviz \+ foxglove 시각화툴쓰기좋음.   
   2. 그냥 컨테이너 띄워서 할건지

사용 가능 센서

* For modulinos, we will have a small selection of buttons, distance, pixels, buzzer, knob, thermo, vibro, and movement. We also have some USB cameras. All will be available to IoT Track participants on a first come, first served basis. No 3D printer on site, unfortunately.

