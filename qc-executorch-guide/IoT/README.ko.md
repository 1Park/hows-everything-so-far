<a id="iot-guide-arduino-ventuno-q"></a>
# IoT 가이드: Arduino VENTUNO Q

Arduino VENTUNO Q에서 엣지 AI 애플리케이션을 만듭니다. Arduino Bridge로 Linux와 마이크로컨트롤러를 연결하고, ExecuTorch와 Qualcomm QNN으로 add 모델, DINOv2 비전 모델, Qwen 0.6B 텍스트 생성 예제를 실행합니다.

[전체 트랙](../README.md) · [관련 아티팩트](artifacts/README.ko.md)

<a id="attendee-journey"></a>
## 참가자 진행 순서

> [!IMPORTANT]
> **IoT 트랙에서는 ExecuTorch 모델을 설치해 사용할 수 있습니다. 참가자가 ExecuTorch를 처음부터 내려받아 빌드하거나 제공된 모델을 직접 변환할 필요는 없습니다.** 트랙 운영팀의 안내에 따라 VENTUNO Q용 번들과 호환 런타임을 설치하세요. 필요한 파일은 [아티팩트 목록](artifacts/README.ko.md)에 정리되어 있습니다. 모델 번들과 설치 링크는 아직 이 저장소에 포함되어 있지 않습니다.

1. **보드를 준비합니다.** 제공된 Linux ARM64 러너와 QCS8275용 모델을 사용해 [설정 및 호환성](#setup-and-compatibility)을 확인합니다.
2. **하드웨어 연결을 확인합니다.** 추론을 연결하기 전에 [LED 예제](#toggle-an-led-from-linux)를 실행해 Linux에서 MCU를 제어할 수 있는지 확인합니다.
3. **모델을 실행합니다.** 설치된 [add 모델](#part-2-run-the-add-model)로 기본 동작을 확인한 다음, 프로젝트에 맞춰 [DINOv2 비전](#part-3-run-and-evaluate-dinov2) 또는 [Qwen 텍스트 생성](#part-4-run-qwen-06b)을 선택합니다. 두 모델을 모두 사용할 필요는 없습니다.
4. **입력부터 동작까지 연결합니다.** [애플리케이션 만들기](#part-5-build-your-application)에 따라 입력, 추론 결과, LED 상태 변경처럼 범위가 제한된 MCU 반응을 보여줍니다.
5. **보드에서 시연을 연습합니다.** 예상 출력과 센서 입력부터 동작까지의 지연 시간을 확인하고, 앱을 다시 시작한 뒤에도 재현되는지 점검합니다. 시연에 사용할 입력과 예상 반응을 정해 둡니다.

목표는 Linux 추론 결과가 MCU 동작으로 이어지는 과정을 반복해서 재현하는 것입니다. 런타임 빌드와 사용자 정의 모델 변환은 선택 부록입니다.

<a id="contents"></a>
## 목차

- [IoT 가이드: Arduino VENTUNO Q](#iot-guide-arduino-ventuno-q)
  - [참가자 진행 순서](#attendee-journey)
  - [목차](#contents)
  - [장치 및 런타임 구성](#device-and-runtime-architecture)
  - [설정 및 호환성](#setup-and-compatibility)
  - [1부: Linux와 MCU 통신](#part-1-linux-and-mcu-communication)
    - [Arduino Bridge와 Router](#arduino-bridge-and-the-router)
    - [Linux에서 LED 전환](#toggle-an-led-from-linux)
    - [MessagePack-RPC 프로토콜 직접 사용](#use-the-messagepack-rpc-protocol-directly)
    - [양방향 RPC 피어](#bidirectional-rpc-peers)
    - [QNN 및 FastRPC와의 관계](#how-this-relates-to-qnn-and-fastrpc)
  - [2부: add 모델 실행](#part-2-run-the-add-model)
  - [3부: DINOv2 실행 및 평가](#part-3-run-and-evaluate-dinov2)
  - [4부: Qwen 0.6B 실행](#part-4-run-qwen-06b)
  - [5부: 애플리케이션 만들기](#part-5-build-your-application)
  - [정확도 및 NPU 성능 확인](#verify-accuracy-and-npu-performance)
  - [문제 해결](#troubleshooting)
  - [부록 A: 런타임을 소스에서 빌드](#appendix-a-build-the-runtime-from-source)
    - [체크아웃 및 SDK 준비](#prepare-the-checkout-and-sdk)
    - [코어 빌드](#build-the-core)
    - [Qualcomm 예제 빌드](#build-the-qualcomm-examples)
  - [부록 B: 명령어 빠른 참조](#appendix-b-command-quick-reference)
  - [추가 자료](#additional-resources)
  - [부록 C: 선택 사항인 사용자 정의 모델 변환](#appendix-c-optional-custom-model-export)
    - [add 모델 변환](#export-the-add-model)
    - [DINOv2 변환](#export-dinov2)

<a id="device-and-runtime-architecture"></a>
## 장치 및 런타임 구성

[Arduino VENTUNO Q](https://docs.arduino.cc/hardware/ventuno-q)는 Ubuntu Linux를 실행하는 **Qualcomm Dragonwing IQ8 / QCS8275** 프로세서와 Arduino Zephyr 코어를 실행하는 **STM32H5F5** 마이크로컨트롤러를 결합한 보드입니다. Linux는 애플리케이션 로직과 ExecuTorch 런타임을 실행하고, MCU는 센서, GPIO, 시간 제약이 있는 제어를 담당합니다. QNN은 QCS8275에 내장된 Hexagon NPU로 지원되는 모델 연산을 위임합니다.

~~~text
센서 / 액추에이터 ↔ STM32H5F5 ↔ Arduino Bridge / Router ↔ Linux 애플리케이션
                                                            │
                                                      ExecuTorch 런타임
                                                            │
                                                         QNN HTP
                                                            │ FastRPC
                                                        Hexagon NPU
~~~

ExecuTorch는 PyTorch 모델을 캡처하고 지원되는 연산을 하드웨어 백엔드 형식으로 변환해 .pte 프로그램으로 저장합니다. 애플리케이션은 호환 런타임으로 이 프로그램을 불러옵니다. QNN의 HTP 백엔드는 Hexagon 가속을 제공하고, QAIRT는 QNN 개발 도구와 런타임 라이브러리를 제공합니다. 전처리, 토큰화, 백엔드에 위임되지 않은 연산은 Linux CPU에서 실행될 수 있습니다.

<a id="setup-and-compatibility"></a>
## 설정 및 호환성

1. [Arduino VENTUNO Q 설정 안내](https://docs.arduino.cc/tutorials/ventuno-q/sbc-mode-setup/)에 따라 보드의 최초 설정을 완료합니다. Python/스케치 예제에는 Arduino App Lab을 사용하고, 네이티브 러너 명령은 보드의 터미널에서 실행합니다.
2. 지원되는 보드 이미지에 트랙에서 제공한 모델/런타임 번들을 설치합니다. 이미지 버전, <code>uname -m</code> 결과, 번들에 포함된 ExecuTorch 및 QAIRT/QNN 버전을 기록합니다.
3. <code>qnn_executor_runner</code>와 LLM 예제용 <code>qnn_llama_runner</code>가 보드의 QNN 라이브러리와 호환되는 Linux ARM64 빌드인지 확인합니다. 파일이 없다면 트랙 운영팀에 호환 런타임을 요청합니다.
4. <code>add.pte</code>와 선택한 DINOv2 또는 Qwen 번들을 설치합니다. 번들에는 샘플 입력/기준 출력 또는 일치하는 토크나이저가 포함되어야 합니다. [아티팩트 목록](artifacts/README.ko.md)을 참고하세요.

**준비된 이미지의 경로.** 아래 예제는 제공 문서의 디렉터리 구조를 사용하며, 문서에 하드코딩된 <code>/home/debian</code> 대신 <code>$HOME</code>을 사용합니다. 변수를 보드의 실제 경로로 설정하세요. 이 작업은 체크아웃이나 러너를 설치하지 않습니다.

~~~bash
export EXECUTORCH_ROOT="$HOME/executorch"
export MODEL_OUTPUT="$HOME/model_output"
export QNN_RUNNER="$EXECUTORCH_ROOT/cmake-out/examples/qualcomm/executor_runner/qnn_executor_runner"
export QNN_LLAMA_RUNNER="$EXECUTORCH_ROOT/cmake-out/examples/qualcomm/executor_runner/qnn_llama_runner"
mkdir -p "$MODEL_OUTPUT"

uname -m
test -x "$QNN_RUNNER"
ldd "$QNN_RUNNER"
"$QNN_RUNNER" --help
~~~

경로나 라이브러리가 누락된 경우 다음 단계로 넘어가기 전에 해결하세요. Qwen 러너는 <code>cmake-out/examples/qualcomm/oss_scripts/llama/</code> 아래에 있을 수도 있습니다. 실제 빌드 결과에 맞춰 <code>QNN_LLAMA_RUNNER</code>를 설정하세요.

원문은 DSP 라이브러리 디렉터리로 <code>/usr/lib</code>을 설정합니다.

~~~bash
export ADSP_LIBRARY_PATH=/usr/lib
~~~

다른 경로를 사용하도록 이미지 문서에 명시되어 있으면 그 경로를 사용하세요. <code>ADSP_LIBRARY_PATH</code>는 Hexagon 라이브러리를 찾는 데 쓰입니다. Linux 호스트 라이브러리도 이미지의 로더 설정이나 <code>LD_LIBRARY_PATH</code>를 통해 찾아져야 합니다. HTP 스텁, DSP 스켈레톤, FastRPC 지원 라이브러리, QNN 런타임이 보드 이미지 및 모델 변환 환경과 호환되는지 확인하세요.

<a id="part-1-linux-and-mcu-communication"></a>
## 1부: Linux와 MCU 통신

<a id="arduino-bridge-and-the-router"></a>
### Arduino Bridge와 Router

원격 프로시저 호출(Remote Procedure Call, RPC)을 사용하면 한 프로세서가 다른 프로세서의 함수를 요청할 수 있습니다. 이를 위해 전송 방식과 메시지 형식, 요청과 응답을 연결하는 방법이 필요합니다.

Arduino Bridge는 애플리케이션 API를 제공합니다. Linux의 <code>arduino-router</code> 서비스는 Linux 프로세스와 MCU 등 연결된 피어 사이에서 MessagePack-RPC 호출을 전달합니다. 피어는 메서드 이름을 등록하고, Router는 해당 메서드를 제공하는 피어로 호출을 전달합니다. [Arduino Bridge 안내](https://docs.arduino.cc/tutorials/ventuno-q/bridge/)와 [Router 구현](https://github.com/arduino/arduino-router)을 참고하세요.

보드 터미널에서 서비스를 확인합니다.

~~~bash
systemctl status arduino-router
systemctl cat arduino-router
journalctl -u arduino-router -f
~~~

제공된 설정은 Bridge 전송용으로 Linux의 <code>/dev/ttyHS1</code>과 MCU의 <code>Serial1</code>을 예약합니다. 애플리케이션 코드에서 Bridge UART를 직접 열지 마세요. 실제 포트 연결은 설치된 서비스와 보드 코어에서 확인하세요. 최신 코어는 <code>Serial1</code> 대신 별도의 Bridge UART를 선택할 수 있습니다.

| API | 동작 |
| --- | --- |
| MCU <code>Bridge.begin()</code> | Bridge 전송을 초기화합니다. |
| Python <code>Bridge.call(method, args...)</code> | 원격 메서드를 호출하고 응답을 기다립니다. |
| MCU <code>Bridge.call(method, args...)</code> | <code>RpcCall</code>을 반환합니다. <code>.result(value)</code>가 응답을 기다린 뒤 결과를 가져옵니다. |
| <code>Bridge.notify(method, args...)</code> | 응답을 기다리지 않는 알림을 보냅니다. |
| MCU <code>Bridge.provide(name, fn)</code> | RPC 스레드에 콜백을 등록합니다. 콜백은 짧고 스레드 안전하게 유지하세요. |
| MCU <code>Bridge.provide_safe(name, fn)</code> | 하드웨어 API를 사용할 수 있도록 콜백을 메인 루프 문맥에서 실행하도록 예약합니다. |

MCU 호출 방식은 [Arduino_RouterBridge](https://github.com/arduino-libraries/Arduino_RouterBridge)에 설명되어 있습니다. RPC 핸들러 안에서 중첩 <code>Bridge.call()</code>이나 <code>Monitor.print()</code>처럼 RPC를 사용하는 로그 출력을 호출하지 마세요. 핸들러에서 다른 통신 응답을 기다리면 연결이 교착 상태에 빠질 수 있습니다. 안전 콜백이 실행되도록 <code>loop()</code>가 계속 빠르게 응답하게 유지하세요.

<a id="toggle-an-led-from-linux"></a>
### Linux에서 LED 전환

Arduino App Lab에서 앱을 만들고 스케치에 다음 코드를 넣습니다. GPIO를 다루므로 <code>provide_safe</code>로 <code>set_led_state</code>를 등록합니다. 이 예제는 원문의 내장 LED가 액티브 로우(active-low)라는 전제를 따릅니다. 보드 리비전에 맞는 LED 핀과 극성을 확인하세요.

~~~cpp
#include <Arduino_RouterBridge.h>

void set_led_state(bool state) {
  digitalWrite(LED_BUILTIN, state ? LOW : HIGH);
}

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, HIGH);
  if (!Bridge.begin()) {
    while (true) {}
  }
  Bridge.provide_safe("set_led_state", set_led_state);
}

void loop() {}
~~~

App Lab 도우미를 사용할 수 있는 앱의 Linux <code>main.py</code>에 다음 코드를 넣습니다.

~~~python
import time
from arduino.app_utils import App, Bridge

led_state = False

def loop():
    global led_state
    time.sleep(1)
    led_state = not led_state
    Bridge.call("set_led_state", led_state)

App.run(user_loop=loop)
~~~

앱을 실행해 LED가 초당 한 번씩 바뀌는지 확인합니다. 이 테스트는 모델 추론과 별도로 Linux에서 MCU까지 통신이 되는지 점검합니다.

<a id="use-the-messagepack-rpc-protocol-directly"></a>
### MessagePack-RPC 프로토콜 직접 사용

제공된 설정에서 Router의 Unix 소켓 경로는 <code>/var/run/arduino-router.sock</code>입니다. Linux 프로세스는 App Lab의 Python 도우미를 쓰지 않고도 같은 MCU 핸들러를 호출할 수 있습니다.

~~~text
요청:      [0, message_id, method, arguments]
응답:      [1, message_id, error, result]
알림:      [2, method, arguments]

LED 요청:  [0, 1, "set_led_state", [true]]
LED 응답:  [1, 1, null, null]
~~~

메시지 ID는 응답과 요청을 연결합니다. Unix 스트림은 한 메시지를 여러 번의 읽기로 나눠 전달하거나, 여러 메시지를 한 번의 읽기에 합쳐 전달할 수 있습니다. 따라서 <code>recv()</code> 한 번으로 응답 하나를 모두 읽는다고 가정하지 말고 스트리밍 MessagePack 디코더를 사용하세요.

함께 제공되는 [msgpack_test.py](artifacts/msgpack_test.py)는 시간 제한, 응답 검증, 스트리밍 디코딩을 포함한 단일 호출 클라이언트입니다. 파일을 보드에 복사하고 MCU 스케치를 실행 상태로 둔 다음, 두 클라이언트가 충돌하지 않도록 App Lab의 Python LED 반복 루프를 중지하세요. 스크립트가 있는 디렉터리에서 실행합니다.

~~~bash
sudo apt install python3-msgpack
/usr/bin/python3 msgpack_test.py 1
/usr/bin/python3 msgpack_test.py 0
~~~

이 명령은 배포판 패키지가 설치된 시스템 Python을 사용합니다. 가상 환경에서 스크립트를 실행한다면 <code>python -m pip install msgpack</code>을 대신 사용하세요. 호출하는 사용자에게 Router 소켓 접근 권한이 있어야 합니다.

<a id="bidirectional-rpc-peers"></a>
### 양방향 RPC 피어

제공 문서는 <code>ArduinoBridge</code> 클래스가 있는 좀 더 완전한 <code>rpc_base.py</code> 피어를 설명하지만 일부 발췌만 포함하고 <code>_send()</code>, <code>_next_msgid()</code>, <code>close()</code> 같은 도우미는 생략합니다. 완전한 파일은 이 저장소에 포함되어 있지 않습니다. 애플리케이션 코드에는 공식 Bridge 라이브러리를 사용하세요.

이 설계는 프로토콜을 이해하는 데 유용합니다. 백그라운드 수신기가 지속형 <code>msgpack.Unpacker</code>에 데이터를 전달하고, 응답 메시지는 ID에 해당하는 대기 중 호출을 완료합니다. 수신한 요청은 등록된 핸들러를 찾아 결과 또는 오류를 전송합니다. 알림은 응답 없이 처리합니다. 피어는 Router의 <code>$/register</code> 메서드를 통해 핸들러 이름을 알립니다.

예를 들어 Linux가 <code>linux_mul</code> 핸들러를 제공하면서 MCU의 <code>mcu_add</code>를 호출할 수 있습니다. 두 핸들러는 각 피어에서 실제로 등록되어 있어야 합니다. 사용자 정의 피어에는 쓰기 동기화, 시간 제한이 있는 대기, 연결 해제 처리, 대기 중 호출 정리도 필요합니다. 문서의 발췌만으로는 완전한 RPC 라이브러리가 되지 않습니다.

<a id="how-this-relates-to-qnn-and-fastrpc"></a>
### QNN 및 FastRPC와의 관계

Arduino Bridge와 Qualcomm FastRPC는 모두 프로세서 간 통신에 쓰이지만 프로토콜과 전송 방식이 다릅니다. Bridge는 Linux와 MCU 사이의 애플리케이션 수준 호출을 전달합니다. QNN은 보드의 FastRPC 기반 구조를 이용해 Hexagon에서 위임된 작업을 실행합니다. MessagePack 소켓과 <code>$/register</code> 메서드는 NPU 인터페이스가 아닙니다.

추론을 위해 변환 과정에서 QNN으로 위임되는 <code>.pte</code>가 생성되고, ExecuTorch 런타임이 이를 불러와 위임 코드를 호출합니다. QNN 런타임이 Hexagon과의 통신을 처리합니다. FastRPC 클라이언트를 직접 작성할 필요는 없으며, LED 데모는 NPU 모델 실행의 필수 조건이 아닙니다.

<a id="part-2-run-the-add-model"></a>
## 2부: add 모델 실행

<code>MODEL_OUTPUT</code> 아래에 설치된 <code>add.pte</code>를 사용합니다. 이 작은 그래프로 대형 모델을 실행하기 전에 추론 파이프라인을 점검합니다. 보드에서 실행하세요.

~~~bash
test -s "$MODEL_OUTPUT/add.pte"
mkdir -p "$MODEL_OUTPUT/add-run/outputs"
cd "$MODEL_OUTPUT/add-run"
"$QNN_RUNNER" --model_path "$MODEL_OUTPUT/add.pte"
~~~

[업스트림 러너](https://github.com/pytorch/executorch/blob/v1.5.1/examples/qualcomm/executor_runner/qnn_executor_runner.cpp)는 <code>input_list.txt</code>를 열지 못하면 기본 입력을 사용합니다. 새 실행 디렉터리에서 실행하는 이 명령은 모델 로드 및 실행 여부만 간단히 확인합니다. 실행에 성공해도 수치 정확성, NPU 위임 여부 또는 속도 향상이 입증되는 것은 아닙니다. 아래 절차로 각각 확인하세요.

<a id="part-3-run-and-evaluate-dinov2"></a>
## 3부: DINOv2 실행 및 평가

전처리된 샘플 이미지, 비어 있지 않은 <code>input_list.txt</code>, 기준 출력, 레이블 매핑이 포함된 DINOv2 번들을 사용합니다. 러너는 작업 디렉터리를 기준으로 입력 경로를 해석합니다. 각 줄에는 한 샘플의 텐서 파일을 공백 하나로 구분해 적습니다. 파일명에 공백을 넣지 마세요. 새 이미지는 번들에 지정된 정확한 크기, 자료형, 레이아웃, 전처리 절차에 맞춰 준비합니다.

준비된 번들이 <code>$MODEL_OUTPUT/dino_v2</code>에 있다고 가정합니다.

~~~bash
cd "$MODEL_OUTPUT/dino_v2"
test -s dino_v2.pte
test -s input_list.txt
mkdir -p outputs
"$QNN_RUNNER" \
  --model_path ./dino_v2.pte \
  --input_list_path ./input_list.txt \
  --output_folder_path ./outputs
~~~

같은 이미지에 대한 PyTorch 출력과 비교한 뒤, 해당 레이블 매핑으로 top-1/top-5 정확도를 계산합니다. <code>.pte</code> 파일만으로는 전처리, 레이블, 정확도 평가를 할 수 없습니다. 결과와 함께 전처리 및 데이터셋 정보를 기록하세요.

<a id="part-4-run-qwen-06b"></a>
## 4부: Qwen 0.6B 실행

보드 런타임과 짝이 맞는 사전 변환된 Qwen3 0.6B 번들을 사용합니다. 실행 전에 번들 제공자에게 일치하는 모델, 토크나이저, 양자화 정보, 문맥 길이 제한, 런타임 버전을 확인하세요.

~~~bash
test -x "$QNN_LLAMA_RUNNER"
"$QNN_LLAMA_RUNNER" --help
test -s "$MODEL_OUTPUT/qwen_0p6B/qwen_0p6B_monza.pte"
test -s "$MODEL_OUTPUT/qwen_0p6B/tokenizer.bin"
cd "$MODEL_OUTPUT/qwen_0p6B"
"$QNN_LLAMA_RUNNER" \
  --model_path ./qwen_0p6B_monza.pte \
  --tokenizer_path ./tokenizer.bin \
  --prompt "Why is the sky blue?" \
  --decoder_model_version qwen3
~~~

[QNN LLM 러너](https://github.com/pytorch/executorch/blob/v1.5.1/examples/qualcomm/oss_scripts/llama/qnn_llama_runner.cpp)는 프롬프트 처리와 자기회귀 디코딩을 실행합니다. 토크나이저는 변환된 모델과 일치해야 합니다. 디코더 플래그를 바꿔도 다른 모델 구조가 Qwen3로 변환되지는 않습니다. LLM 변환에는 add 모델 변환기만으로는 처리할 수 없는 모델별 양자화와 캐시 관리가 필요합니다.

모델 실행은 여러 위임 구간과 CPU 작업을 포함할 수 있습니다. 생성 토큰마다 FastRPC를 정확히 한 번 호출한다고 가정하거나 애플리케이션 전체가 NPU에서 실행된다고 가정하지 마세요. 첫 토큰 생성 시간과 이후 토큰의 지속 생성 속도를 따로 측정하세요.

<a id="part-5-build-your-application"></a>
## 5부: 애플리케이션 만들기

- **센서 입력을 추론에 연결합니다.** MCU에서 센서를 읽고 Bridge를 통해 Linux에서 값을 요청한 뒤, Linux에서 전처리하고 모델을 실행한 다음 결과를 짧은 MCU 핸들러로 돌려보냅니다. 시간에 민감한 제어와 액추에이터 제한은 MCU에서 처리합니다.
- **모델을 조정합니다.** 목적에 가장 가까운 비전 또는 LLM 변환기부터 시작합니다. 앱에 통합하기 전에 연산자 지원 여부, 입력 크기, 대표성 있는 보정 데이터, 출력 정확도를 확인합니다.
- **CPU와 HTP를 비교합니다.** 같은 모델의 CPU 버전과 QNN 버전을 각각 변환한 뒤 동일한 입력과 전처리로 비교합니다. QNN <code>.pte</code>에서 CPU 기준 실행으로 전환할 수는 없습니다.
- **반복 가능한 데모를 만듭니다.** 가능하면 모델을 메모리에 유지하고 버퍼를 재사용합니다. 러너의 CLI를 수정하기 전에 기존 반복/프로파일링 플래그를 확인합니다. LLM 프롬프트 및 디코딩 처리는 LLM 러너에 맡깁니다.

<a id="verify-accuracy-and-npu-performance"></a>
## 정확도 및 NPU 성능 확인

제공 모델은 번들의 위임 보고서와 기준 출력을 사용합니다. 직접 모델을 변환한다면 <code>to_executorch()</code>를 호출하기 전에, 변환기에서 lowering을 마친 시점의 위임 정보를 확인합니다. 여기서 <code>edge_manager</code>는 반환된 <code>EdgeProgramManager</code>입니다.

~~~python
from executorch.devtools.backend_debug import get_delegation_info

info = get_delegation_info(edge_manager.exported_program().graph_module)
print(info.get_summary())
print(info.get_operator_delegation_dataframe())
~~~

그다음 보드에서 출력을 검증하고 프로파일링합니다. 실제 입력을 DINOv2 실행 디렉터리에 준비하고, 러너의 <code>--help</code>에서 아래 플래그를 지원하는지 확인한 뒤 실행합니다.

~~~bash
"$QNN_RUNNER" \
  --model_path ./dino_v2.pte \
  --input_list_path ./input_list.txt \
  --output_folder_path ./outputs \
  --warm_up 10 --iteration 100 --profile_level 0
~~~

러너 로그에서 입력별 평균 지연 시간을 사용하고, 최종 요약을 해석하기 전에 러너가 반복 횟수를 집계하는 방식을 확인하세요. 별도의 진단 실행은 <code>--warm_up 0 --iteration 1 --profile_level 1</code>로 하고, 변환 때의 ETRecord와 실행 때의 ETDump를 보존합니다. 런타임 이벤트와 위임 작업을 Inspector에서 연결하는 방법은 [ExecuTorch 런타임 프로파일링](https://docs.pytorch.org/executorch/1.5/runtime-profiling.html)을 참고하세요.

위임 연산과 CPU 연산, 워밍업 후 모델 지연 시간, 센서 입력부터 동작까지의 전체 지연 시간, 최대 메모리, 지속 실행 중 열 상태를 기록합니다. 전력 모드, 입력 집합, 다른 실행 작업을 동일하게 유지하세요. NPU 가속이나 정확도 결과를 주장하려면 하드웨어 프로파일링과 출력 검증이 필요합니다.

<a id="troubleshooting"></a>
## 문제 해결

| 증상 | 확인할 사항 |
| --- | --- |
| Bridge 호출이 멈추거나 LED가 반응하지 않음 | <code>systemctl status arduino-router</code>와 <code>journalctl -u arduino-router -f</code>를 확인합니다. 스케치에 정확한 메서드 이름이 등록되었는지 확인하고, 중첩 RPC 호출을 피하며 MCU 루프가 계속 응답하도록 합니다. |
| Router 소켓이 없거나 접근할 수 없음 | <code>systemctl cat arduino-router</code>에서 소켓 경로를 확인하고 호출 사용자의 권한을 점검합니다. UART를 직접 열어 Router를 우회하지 마세요. |
| 통신이 계속 멈춰 있음 | 관련 앱을 중지한 뒤 <code>sudo systemctl restart arduino-router</code>를 실행합니다. 이어서 앱을 다시 시작해 피어가 재연결되고 메서드를 등록하도록 합니다. |
| <code>QCS8275</code>가 거부됨 | 보드용으로 지정된 체크아웃과 지원되는 QNN SDK를 사용합니다. 다른 칩셋 타깃을 지정해도 호환성 문제는 해결되지 않습니다. |
| Python 변환 모듈을 불러오지 못함 | 체크아웃의 환경을 활성화하고 필요한 패키지를 설치합니다. 문서에는 <code>numpy</code>, <code>ruamel.yaml</code>, <code>tabulate</code>, <code>pandas</code>도 언급되어 있습니다. <code>PyQnnManagerAdaptor</code>가 없으면 이 패키지만으로 해결되지 않으며 QNN AOT 빌드가 필요합니다. |
| FlatBuffers 도구가 없음 | 체크아웃에서 요구하는 버전을 설치합니다. 제공된 이미지에서는 <code>sudo apt install flatbuffers-compiler</code>를 사용합니다. |
| QNN/HTP를 초기화할 수 없음 | <code>ldd</code>에서 호스트 라이브러리 오류를 확인하고, 이미지의 DSP 라이브러리 디렉터리, FastRPC 사용 가능 여부, SDK/런타임 버전 일치 여부를 점검합니다. |
| DINOv2 변환은 되지만 정확도 결과가 없음 | <code>--compile_only</code>는 실행을 건너뜁니다. 체크아웃에서 문서의 <code>-c</code> 단축 옵션이 무엇을 뜻하는지 확인하고, 실제 입력을 준비해 보드의 Linux 평가 절차를 사용합니다. |
| 러너는 성공하지만 출력이 예상과 다름 | 기본 입력으로 대체되지 않도록 비어 있지 않은 입력 목록을 읽었는지 확인합니다. 텐서 자료형, 크기, 전처리, 레이블도 점검합니다. |
| Qwen을 불러오지 못하거나 잘못된 텍스트가 생성됨 | <code>.pte</code>, 토크나이저, 디코더 유형, 러너가 같은 호환 번들에 속하는지 확인합니다. |

파일 접근 문제를 진단하려면 실패한 변환 명령 앞에 <code>strace -f -e trace=openat,open,access,stat,statx -s 200 -o /tmp/export-trace.log</code>를 붙입니다. Router 디버그 로그가 필요하면 먼저 설치된 서비스를 확인한 뒤, 기존 실행 파일과 인자를 유지하는 systemd 오버라이드로 <code>--verbose</code>를 추가합니다. 이후 systemd를 다시 불러오고 서비스를 재시작합니다.

<a id="appendix-a-build-the-runtime-from-source"></a>
## 부록 A: 런타임을 소스에서 빌드

참가자는 이 부록을 건너뛰고 설치 가능한 트랙 모델과 런타임을 사용할 수 있습니다. 아래 명령은 제공 문서의 네이티브 Linux 빌드 구조를 옮긴 것입니다. 수정되지 않은 업스트림 릴리스에서 검증된 절차가 아니라 **보드가 지원하는 체크아웃 및 SDK를 전제로 합니다.**

<a id="prepare-the-checkout-and-sdk"></a>
### 체크아웃 및 SDK 준비

서브모듈을 포함해 보드 이미지에 사용된 정확한 소스 리비전을 확보합니다. 지원되는 Python 버전과 동작하는 C/C++ 도구 체인을 갖춘 상태에서 해당 체크아웃 안에서 실행합니다.

~~~bash
cd "$EXECUTORCH_ROOT"
git rev-parse HEAD
git submodule sync
git submodule update --init --recursive
python3 -m venv env_executorch
source env_executorch/bin/activate
python -m pip install --upgrade pip
python install_requirements.py
~~~

이미지에 CMake, Ninja, GCC/G++가 없다면 설치합니다. 체크아웃에서 지정한 의존성 버전을 사용하세요. <code>QNN_SDK_ROOT</code>는 헤더만이 아니라 필요한 파일이 모두 포함된 호환 SDK를 가리켜야 합니다.

~~~bash
export CC=/usr/bin/gcc
export CXX=/usr/bin/g++
export QNN_SDK_ROOT=/path/to/matching/qairt-sdk
export PYTHONPATH="$EXECUTORCH_ROOT/..${PYTHONPATH:+:$PYTHONPATH}"
test -d "$QNN_SDK_ROOT/include/QNN"
test -d "$QNN_SDK_ROOT/share/QNN/converter/jni"
~~~

원문은 <code>/usr/local</code> 아래에 시스템 레이아웃으로 SDK를 설치한다고 가정합니다. 호환되는 헤더, 변환기 파일, Linux 라이브러리가 모두 그 위치에 있을 때만 이 구성이 동작합니다. 필요한 경우 <code>LD_LIBRARY_PATH</code>를 실제 호스트 라이브러리 디렉터리로 설정하고, DSP 라이브러리는 보드 이미지 문서에 지정된 <code>ADSP_LIBRARY_PATH</code>를 계속 사용하세요.

**AOT 빌드의 제한:** <code>EXECUTORCH_BUILD_PYBIND=ON</code>만으로 ARM64 네이티브 QNN 모델 변환이 보장되지는 않습니다. 확인한 [업스트림 QNN CMake 설정](https://github.com/pytorch/executorch/blob/v1.5.1/backends/qualcomm/CMakeLists.txt)은 QNN Python 바인딩 빌드를 x86-64 환경으로 제한합니다.

<a id="build-the-core"></a>
### 코어 빌드

아래 빌드 옵션을 지원하는 보드 체크아웃에서 <code>EXECUTORCH_ROOT</code>를 기준으로 실행합니다.

~~~bash
cmake -S . -B cmake-out -G Ninja \
  -DCMAKE_INSTALL_PREFIX="$EXECUTORCH_ROOT/cmake-out/et-install" \
  -DCMAKE_BUILD_TYPE=Release \
  -DEXECUTORCH_BUILD_QNN=ON \
  -DEXECUTORCH_BUILD_DEVTOOLS=ON \
  -DEXECUTORCH_BUILD_EXTENSION_LLM=ON \
  -DEXECUTORCH_BUILD_EXTENSION_LLM_RUNNER=ON \
  -DEXECUTORCH_BUILD_EXTENSION_MODULE=ON \
  -DEXECUTORCH_BUILD_EXTENSION_DATA_LOADER=ON \
  -DEXECUTORCH_BUILD_EXTENSION_FLAT_TENSOR=ON \
  -DEXECUTORCH_BUILD_EXTENSION_NAMED_DATA_MAP=ON \
  -DEXECUTORCH_BUILD_EXTENSION_TENSOR=ON \
  -DEXECUTORCH_ENABLE_EVENT_TRACER=ON \
  -DEXECUTORCH_ENABLE_LOGGING=ON \
  -DEXECUTORCH_BUILD_KERNELS_QUANTIZED=ON \
  -DEXECUTORCH_BUILD_PYBIND=ON \
  -DQNN_SDK_ROOT="$QNN_SDK_ROOT" \
  -DPYTHON_EXECUTABLE="$(command -v python)"
cmake --build cmake-out --parallel 4
cmake --install cmake-out
~~~

설정이나 빌드 오류가 나면 중단하고 해결하세요. 보드 체크아웃에서 AOT와 런타임을 별도로 빌드해야 한다면 해당 체크아웃의 안내를 따르고, 2~4부에서 실제 경로를 사용합니다.

<a id="build-the-qualcomm-examples"></a>
### Qualcomm 예제 빌드

~~~bash
cmake -S examples/qualcomm -B cmake-out/examples/qualcomm \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_PREFIX_PATH="$EXECUTORCH_ROOT/cmake-out/et-install;$EXECUTORCH_ROOT/cmake-out;$EXECUTORCH_ROOT/cmake-out/third-party/gflags" \
  -DSUPPORT_REGEX_LOOKAHEAD=ON \
  -DBUILD_TESTING=OFF \
  -DEXECUTORCH_ENABLE_LOGGING=ON \
  -DEXECUTORCH_BUILD_KERNELS_QUANTIZED=ON \
  -DPYTHON_EXECUTABLE="$(command -v python)"
cmake --build cmake-out/examples/qualcomm --parallel 4
~~~

이 체크아웃이 두 러너를 어디에 생성하는지 확인하고 <code>QNN_RUNNER</code> 및 <code>QNN_LLAMA_RUNNER</code>를 갱신합니다. 2부로 돌아가기 전에 호환성 확인을 다시 하고, 변환 환경에서 QNN Python 바인딩을 불러올 수 있는지와 보드 러너의 동적 라이브러리가 해결되는지 확인하세요. C++ 바이너리만 빌드해도 QCS8275 타깃 지원이나 누락된 모델 번들이 제공되지는 않습니다.

<a id="appendix-b-command-quick-reference"></a>
## 부록 B: 명령어 빠른 참조

아래 명령은 위의 환경 변수와 사전 조건이 이미 설정되어 있다고 가정합니다.

| 작업 | 명령 또는 절 |
| --- | --- |
| Router 상태 확인 | <code>systemctl status arduino-router</code> |
| Router 로그 확인 | <code>journalctl -u arduino-router -f</code> |
| LED 켜기 / 끄기 | <code>/usr/bin/python3 msgpack_test.py 1</code> / <code>/usr/bin/python3 msgpack_test.py 0</code> |
| 변환 옵션 확인 | <code>python -m examples.qualcomm.scripts.export_example --help</code> |
| add 모델 기본 실행 | 새 실행 디렉터리에서 <code>"$QNN_RUNNER" --model_path "$MODEL_OUTPUT/add.pte"</code> |
| DINOv2 변환 | [부록 C](#appendix-c-optional-custom-model-export); <code>--compile_only</code>는 실행을 건너뜁니다. |
| 텍스트 생성 | [4부](#part-4-run-qwen-06b); 일치하는 Qwen 번들이 필요합니다. |
| 코어 및 러너 빌드 | [부록 A](#appendix-a-build-the-runtime-from-source) |

<a id="additional-resources"></a>
## 추가 자료

- [Arduino VENTUNO Q 하드웨어 및 사용자 설명서](https://docs.arduino.cc/hardware/ventuno-q)
- [VENTUNO Q Bridge 및 RPC](https://docs.arduino.cc/tutorials/ventuno-q/bridge/)
- [Arduino Router](https://github.com/arduino/arduino-router) 및 [Arduino_RouterBridge API](https://github.com/arduino-libraries/Arduino_RouterBridge)
- [ExecuTorch Qualcomm 백엔드](https://docs.pytorch.org/executorch/1.5/backends-qualcomm.html)
- [Qualcomm 모델 예제](https://github.com/pytorch/executorch/tree/v1.5.1/examples/qualcomm): 업스트림 명령을 사용하기 전에 보드 체크아웃과 다른 점을 확인하세요.
- [Qualcomm AI Hub](https://aihub.qualcomm.com/): 호스팅 장치의 결과는 실제 VENTUNO Q에서 측정한 결과를 대체하지 않습니다.

<a id="appendix-c-optional-custom-model-export"></a>
## 부록 C: 선택 사항인 사용자 정의 모델 변환

제공된 모델을 교체할 때만 이 절을 사용하세요. 먼저 보드가 지원하는 체크아웃과 변환 환경을 확보합니다. 참가자용 런타임 설치에는 변환 도구가 필요하지 않습니다.

변환 전에 체크아웃과 함께 제공된 Python 환경을 활성화합니다. 그 환경에서 타깃 매핑을 확인합니다.

~~~bash
python - <<'PY'
from executorch.backends.qualcomm.utils.utils import get_soc_to_chipset_map

targets = get_soc_to_chipset_map()
assert "QCS8275" in targets, "This checkout lacks the required QCS8275 target"
print("QCS8275 target:", targets["QCS8275"])
PY
~~~

이 검사는 타깃 매핑만 확인할 뿐 전체 하드웨어 호환성을 보장하지 않습니다. 변환하려면 정상 동작하는 QNN 바인딩과 보드 빌드에서 지원하는 SDK도 필요합니다. 별도의 개발 호스트에서 변환한다면 동일하게 지원되는 체크아웃/SDK 조합을 사용하고, 생성된 아티팩트를 보드로 옮깁니다.

<a id="export-the-add-model"></a>
### add 모델 변환

[설정 및 호환성](#setup-and-compatibility)에서 준비한 QCS8275용 변환 환경을 사용합니다. add 그래프는 큰 모델을 시도하기 전에 파이프라인을 점검하기 위한 작은 예제입니다.

~~~bash
cd "$EXECUTORCH_ROOT"
python -m examples.qualcomm.scripts.export_example --help
python -m examples.qualcomm.scripts.export_example \
  --model_name add \
  --generate_etrecord \
  --output_folder "$MODEL_OUTPUT/" \
  --soc QCS8275
~~~

예상 결과는 <code>MODEL_OUTPUT</code> 아래의 <code>add.pte</code>와 프로파일링 메타데이터입니다. 끝에 슬래시를 넣으면 ETRecord 파일명을 문자열 결합으로 만드는 변환기에서도 경로가 맞습니다. [업스트림 변환기](https://github.com/pytorch/executorch/blob/v1.5.1/examples/qualcomm/scripts/export_example.py)는 양자화 옵션을 지정하지 않으면 HTP를 선택하고 FP16을 사용합니다. 보드 체크아웃의 정밀도 요구 사항을 따르세요. 예제 입력을 이용한 보정은 이 장난감 그래프에는 충분하지만 실제 모델의 정확도 평가에는 충분하지 않습니다.

다른 위치에서 변환했다면 결과 파일을 보드로 옮긴 다음 보드에서 실행합니다.

생성된 모델 실행 방법은 [2부](#part-2-run-the-add-model)로 돌아가 확인하세요.

<a id="export-dinov2"></a>
### DINOv2 변환

DINOv2에는 비전 트랜스포머와 이미지 전처리가 포함됩니다. 제공 스크립트가 기대하는 클래스 디렉터리와 레이블 매핑을 갖춘 ImageNet 형식의 레이블 검증용 하위 집합을 준비합니다. 평가용 홀드아웃 데이터는 보정 데이터와 분리하세요. 데이터셋 파일과 모델 가중치는 이 저장소에 포함되어 있지 않습니다.

문서에서는 <code>dino_v2.py</code>가 <code>examples/qualcomm/scripts/</code> 아래에 있다고 가정합니다. 보드 체크아웃에 실제로 이 경로가 있을 때만 사용하고, 먼저 도움말을 확인하세요.

~~~bash
export IMAGENET_VAL="$HOME/datasets/imagenet-mini/val"
cd "$EXECUTORCH_ROOT"
python -m examples.qualcomm.scripts.dino_v2 --help
python -m examples.qualcomm.scripts.dino_v2 \
  --soc_model QCS8275 \
  --build_folder "$EXECUTORCH_ROOT/cmake-out" \
  --artifact "$MODEL_OUTPUT/dino_v2" \
  --dataset "$IMAGENET_VAL" \
  --compile_only
~~~

<code>--build_folder</code>에는 스크립트가 기대하는 빌드 디렉터리를 지정해야 합니다. 위 예제는 부록 A의 <code>cmake-out</code> 디렉터리를 사용합니다. 제공된 환경에서 별도의 트리로 사용하는 경우에만 <code>build-aot</code>를 지정하세요.

**<code>--compile_only</code>는 보드에서 평가하거나 정확도를 측정하지 않고 모델만 변환합니다.** 이 모드에서는 [공유 변환 유틸리티](https://github.com/pytorch/executorch/blob/v1.5.1/backends/qualcomm/export_utils.py)가 컴파일 후 종료됩니다. 확인한 [업스트림 DINOv2 예제](https://github.com/pytorch/executorch/blob/v1.5.1/examples/qualcomm/oss_scripts/dino_v2.py)는 <code>examples/qualcomm/oss_scripts/</code>에 있으며 공통 배포 도우미를 사용합니다. 이 사실만으로 문서에 적힌 보드 전용 경로가 일반 업스트림 체크아웃에서도 동작한다고 볼 수는 없습니다. 실행 모드를 시도하기 전에 Linux 배포 경로를 확인하세요.

VENTUNO Q에서 평가하려면 보드 전용 스크립트에 문서화된 Linux 평가 모드를 사용하거나, 보드 러너용 <code>.pte</code>, 전처리된 원시 텐서, 비어 있지 않은 <code>input_list.txt</code>를 준비합니다. 각 줄에는 한 샘플의 입력 파일을 공백 하나로 구분해 적고, 내보낸 모델의 크기, 자료형, 레이아웃을 맞춥니다. 경로는 러너의 작업 디렉터리 기준으로 작성하고 파일명에 공백을 넣지 마세요.

준비된 번들을 평가하려면 [3부](#part-3-run-and-evaluate-dinov2)로 돌아갑니다.

