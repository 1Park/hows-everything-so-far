# A단계 QNN export용 x86-64 Linux 환경 (Apple Silicon Mac에서는 Rosetta 에뮬레이션으로 실행).
# QNN Python 바인딩(PyQnnManagerAdaptor)이 x86-64 전용이라 Mac/보드(ARM64)에서는 export 불가.
#   docker build --platform linux/amd64 -t refill-ml-export ml
#   ml/docker-run.sh python -m ml.export.export_qnn --model yolo --soc_model SM8650 --build_folder /tmp --compile_only
# QAIRT SDK는 첫 export 때 ExecuTorch가 자동 다운로드 → named volume(refill-qnn-cache)에 캐시.
# 주최 측 보드 checkout을 받으면 그 ExecuTorch로 교체 설치해야 QCS8275 타깃이 생긴다 (ml/export/README.md).
FROM --platform=linux/amd64 python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends unzip libgl1 libglib2.0-0 libatomic1 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.14.1 torchvision==0.29.1 \
 && pip install --no-cache-dir executorch==1.5.1 transformers==5.20.0 ultralytics==8.4.178 \
        opencv-python-headless pillow scikit-learn py-cpuinfo msgpack pydot \
 && pip uninstall -y opencv-python || true

# opencv-python 제거 시 공유 cv2 폴더가 지워지므로 headless 재설치
RUN pip install --no-cache-dir --force-reinstall --no-deps opencv-python-headless && pip install --no-cache-dir pydot && python -c "import cv2, pydot"

WORKDIR /work
