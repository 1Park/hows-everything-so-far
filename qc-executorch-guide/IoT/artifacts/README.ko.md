# IoT 아티팩트 안내

[IoT 가이드](../README.ko.md) · [전체 트랙](../../README.md)

## 설치용 참가자 번들

IoT 트랙에서는 ExecuTorch 모델을 설치해 사용할 수 있습니다. 참가자가 ExecuTorch를 처음부터 내려받아 빌드할 필요는 없습니다. 설치 링크와 모델/런타임 번들은 아직 여기에 포함되어 있지 않으므로 트랙 운영팀에서 VENTUNO Q용 번들을 받으세요.

참가자 번들에는 Linux ARM64 러너와 호환 QNN 라이브러리, <code>add.pte</code>, 그리고 선택한 DINOv2 또는 Qwen 모델이 필요합니다. DINOv2에는 샘플 텐서, <code>input_list.txt</code>, 레이블, 전처리 안내, 기준 출력이 필요합니다. Qwen에는 해당 모델과 짝이 맞는 토크나이저가 필요합니다. 보드에서 경로를 설정하려면 [설정 및 호환성 안내](../README.ko.md#setup-and-compatibility)를 따르세요. 아래에 적힌 소스 체크아웃, SDK, 내보내기 데이터셋은 사용자 정의 모델 변환이나 빌드에만 필요합니다.

## 저장소에 포함된 파일

| 파일 | 용도 |
| --- | --- |
| [msgpack_test.py](msgpack_test.py) | 가이드에 나온 MCU의 <code>set_led_state</code> 핸들러를 호출하는 Linux 단일 호출 클라이언트입니다. <code>msgpack</code>, Router 소켓 접근 권한, 실행 중인 스케치가 필요합니다. |
| [test_msgpack_test.py](test_msgpack_test.py) | 분할된 응답, RPC 오류, 잘못된 응답, 연결 해제를 확인하는 로컬 프로토콜 검사입니다. 보드가 없어도 실행할 수 있습니다. |

저장소 루트에서 <code>msgpack</code>이 설치된 환경으로 다음 명령을 실행합니다.

~~~bash
python -m unittest discover -s IoT/artifacts -p 'test_*.py'
~~~

## 별도로 필요한 파일

| 항목 | 필요한 작업 |
| --- | --- |
| 보드 이미지, QCS8275를 지원하는 ExecuTorch 체크아웃/커밋, 호환 QAIRT/QNN SDK 및 런타임 | 모델 변환과 실행에 필요합니다. 이 가이드에서 확인한 기본 업스트림 버전은 QCS8275를 나열하지 않습니다. |
| Linux ARM64용 <code>qnn_executor_runner</code> 및 <code>qnn_llama_runner</code> | 보드에서 변환된 모델을 실행할 때 필요합니다. 이미지에 포함되어 있거나 지원 체크아웃에서 빌드해야 합니다. |
| 보드 전용 <code>dino_v2.py</code>와 레이블이 있는 ImageNet 형식 하위 집합 | DINOv2 변환 및 평가에 필요합니다. 문서에 적힌 스크립트 경로는 확인한 업스트림 예제 경로와 다릅니다. |
| <code>qwen_0p6B_monza.pte</code>와 짝이 맞는 <code>tokenizer.bin</code> | Qwen3 0.6B 텍스트 생성에 필요합니다. 가이드 설명대로 <code>$MODEL_OUTPUT/qwen_0p6B/</code> 아래에 둡니다. |
| 별도로 제공되는 경우 완전한 <code>rpc_base.py</code> | 문서에서 설명하는 사용자 정의 양방향 피어에 선택적으로 필요합니다. 공식 Bridge 라이브러리를 사용하면 애플리케이션 개발에 이 파일이 필요하지 않습니다. |

참가자용 설치 번들에는 모델과 샘플 입력이 포함되어야 합니다. 선택적인 사용자 정의 변환은 대체 모델을 생성하고 ETRecord를 만듭니다. 프로파일링 결과는 검증 과정에서 생성됩니다. 모델 번들을 공유할 때는 재현성을 위해 모델/토크나이저 출처, ExecuTorch 커밋, SDK/런타임 버전, QCS8275 타깃, 입력 규격, 보정 정보를 함께 기록하세요.

