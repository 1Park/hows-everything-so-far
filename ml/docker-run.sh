#!/bin/zsh
# x86-64 QNN export/시뮬레이터 컨테이너 실행 (Apple Silicon Mac: Rosetta 에뮬레이션). 레포 루트를 /work 로 마운트.
#   docker build --platform linux/amd64 -t refill-ml-export ml
#   ml/docker-run.sh python -m ml.export.export_qnn --model yolo --soc_model SM8650 --build_folder /tmp --compile_only
# 첫 실행 때 ExecuTorch가 QAIRT SDK(~3GB)와 libc++(~5GB)를 받아 named volume 에 캐시한다 (QNN_CACHE_VOLUME, 기본 refill-qnn-cache).
# 다운로더는 라이브러리 경로를 자기 프로세스 안에서만 잡아서 libQnnHtp.so 가 libc++.so.1 을 못 찾음 → 여기서 고정.
# 주최 측 SDK를 쓰려면: QNN_SDK_ROOT_HOST=/path/to/qairt ml/docker-run.sh ...  (/qairt 로 마운트)
cd "$(dirname "$0")/.."
CACHE=/root/.cache/executorch/qnn
SDK=${QNN_SDK_ROOT_HOST:+/qairt}
SDK=${SDK:-$CACHE/sdk-2.37.0.250724}
LIBCXX=$CACHE/libcxx-14.0.0/clang+llvm-14.0.0-x86_64-linux-gnu-ubuntu-18.04/lib/x86_64-unknown-linux-gnu
exec docker run --rm --platform linux/amd64 \
  -v "$PWD":/work -v "${QNN_CACHE_VOLUME:-refill-qnn-cache}":/root/.cache \
  ${QNN_SDK_ROOT_HOST:+-v "$QNN_SDK_ROOT_HOST":/qairt} \
  -e QNN_SDK_ROOT="$SDK" \
  -e LD_LIBRARY_PATH="$SDK/lib/x86_64-linux-clang:$LIBCXX" \
  -e PYTHONPATH=/work \
  refill-ml-export "$@"
