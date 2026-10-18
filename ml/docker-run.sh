#!/bin/zsh
# Runs the x86-64 QNN export/simulator container (Apple Silicon Mac: Rosetta emulation). Mounts the repo root at /work.
#   docker build --platform linux/amd64 -t refill-ml-export ml
#   ml/docker-run.sh python -m ml.export.export_qnn --model yolo --soc_model SM8650 --build_folder /tmp --compile_only
# On the first run ExecuTorch downloads the QAIRT SDK (~3GB) and libc++ (~5GB) and caches them in a named volume
# (QNN_CACHE_VOLUME, default refill-qnn-cache).
# The downloader sets the library path only inside its own process, so libQnnHtp.so cannot find libc++.so.1 -> pin it here.
# To use the organizers' SDK: QNN_SDK_ROOT_HOST=/path/to/qairt ml/docker-run.sh ...  (mounted at /qairt)
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
