#!/bin/sh
# 테스트용: services.vision.runners.CliRunner 가 바이너리처럼 호출할 수 있게 fake_runner.py 를 감싼다.
# 보드에서는 진짜 qnn_executor_runner 를 쓴다. ML_PYTHON 으로 executorch 가 설치된 python 지정 (기본 ml/.venv).
DIR="$(cd "$(dirname "$0")/../.." && pwd)"
exec "${ML_PYTHON:-$DIR/ml/.venv/bin/python}" "$DIR/ml/tools/fake_runner.py" "$@"
