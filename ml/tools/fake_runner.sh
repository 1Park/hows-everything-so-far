#!/bin/sh
# For tests: wraps fake_runner.py so services.vision.runners.CliRunner can call it like a binary.
# The board uses the real qnn_executor_runner. ML_PYTHON picks a python with executorch installed (default ml/.venv).
DIR="$(cd "$(dirname "$0")/../.." && pwd)"
exec "${ML_PYTHON:-$DIR/ml/.venv/bin/python}" "$DIR/ml/tools/fake_runner.py" "$@"
