# x86-64 Linux environment for stage-A QNN export (runs under Rosetta emulation on Apple Silicon Macs).
# The QNN Python binding (PyQnnManagerAdaptor) is x86-64 only, so export cannot run on the Mac or the board (ARM64).
#   docker build --platform linux/amd64 -t refill-ml-export ml
#   ml/docker-run.sh python -m ml.export.export_qnn --model yolo --soc_model SM8650 --build_folder /tmp --compile_only
# ExecuTorch downloads the QAIRT SDK on the first export -> cached in a named volume (refill-qnn-cache).
# Once we get the organizers' board checkout, reinstall with that ExecuTorch to get the QCS8275 target (ml/export/README.md).
FROM --platform=linux/amd64 python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends unzip libgl1 libglib2.0-0 libatomic1 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.14.1 torchvision==0.29.1 \
 && pip install --no-cache-dir executorch==1.5.1 transformers==5.20.0 ultralytics==8.4.178 \
        opencv-python-headless pillow scikit-learn py-cpuinfo msgpack pydot \
 && pip uninstall -y opencv-python || true

# Removing opencv-python deletes the shared cv2 folder, so reinstall the headless build
RUN pip install --no-cache-dir --force-reinstall --no-deps opencv-python-headless && pip install --no-cache-dir pydot && python -c "import cv2, pydot"

WORKDIR /work
