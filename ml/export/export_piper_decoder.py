"""Piper TTS 디코더(HiFi-GAN)를 길이 고정 ExecuTorch QNN(fp16) .pte로 export — 보드 ExecuTorch venv에서 실행.

Piper voice .onnx 는 앞부분(발음·길이 예측·flow, 입력마다 출력 길이가 바뀜)과 디코더(Conv/ConvTranspose만)로
나눈다 (services/tts/backend.split_voice). 디코더만 latent 길이 N 프레임으로 고정해 NPU용으로 export하고,
서비스는 문장마다 n ≤ N 인 가장 작은 .pte를 골라 0으로 채워 돌린 뒤 n*256 샘플로 자른다.

  source ~/git/executorch/.venv/bin/activate   # + pip install onnx2torch piper-tts
  export PYTHONPATH=$HOME/git:$PWD FLATC_EXECUTABLE=... QNN_SDK_ROOT=~/qnn_sdk_root   (BOARD_RUNBOOK)
  python -m ml.export.export_piper_decoder --voice models/board/tts/en_US-hfc_female-medium.onnx \
      --frames 384 --soc_model QCS8275 --build_folder ~/git/executorch/build-x86 --compile_only
  → models/board/tts/en_US-hfc_female-medium.dec_f384.pte  (11 MB, 2분 35초, NPU 미지원 연산 0)

2026-10-18 보드: 데모 한 줄의 latent는 150~335 프레임 → 384 하나로 처리. 128·256 프레임 export는 QNN
"VTCM Allocation" 단계에서 15분 넘게 멈춰 중단했다 (384는 같은 단계 2.3초).
"""

import numpy as np
import onnx
import torch
from executorch.backends.qualcomm.export_utils import QnnConfig, build_executorch_binary, setup_common_args_and_variables
from onnx2torch import convert

from services.tts.backend import split_voice

SAMPLES = ["Your water is running low.", "Would you like a refill?", "Is that coke or coffee?",
           "Just call me if you need anything."]


def sample_latents(voice_path, front_path, frames):
    """앞부분 그래프로 실제 문장 latent를 만들어 export 입력 예시로 쓴다 (fp16이라 보정용 아님)."""
    import onnxruntime as ort
    from piper import PiperVoice

    voice = PiperVoice.load(str(voice_path))
    front = ort.InferenceSession(str(front_path), providers=["CPUExecutionProvider"])
    scales = np.array([0.8, 0.88, 0.9], np.float32)
    data = []
    for text in SAMPLES:
        for phonemes in voice.phonemize(text):
            x = np.array([voice.phonemes_to_ids(phonemes)], np.int64)
            (z,) = front.run(None, {"input": x, "input_lengths": np.array([x.shape[1]], np.int64), "scales": scales})
            pad = np.zeros((1, z.shape[1], frames), np.float32)
            n = min(z.shape[2], frames)
            pad[:, :, :n] = z[:, :, :n]
            data.append((torch.from_numpy(pad),))
    return data


def main():
    ap = setup_common_args_and_variables()
    ap.add_argument("--voice", required=True, help="Piper voice .onnx (같은 폴더에 .onnx.json)")
    ap.add_argument("--frames", type=int, required=True, help="고정 latent 길이 (1프레임 = 256 샘플)")
    args = ap.parse_args()
    front, dec = split_voice(args.voice)
    m = onnx.load(str(dec))
    dims = m.graph.input[0].type.tensor_type.shape.dim
    dims[0].dim_value, dims[2].dim_value = 1, args.frames
    for out in m.graph.output:
        for d in out.type.tensor_type.shape.dim:
            d.ClearField("dim_param")
    model = convert(m).eval()
    stem = str(dec).removesuffix(".dec.onnx")
    build_executorch_binary(model=model, qnn_config=QnnConfig.load_config(args), file_name=f"{stem}.dec_f{args.frames}",
                            dataset=sample_latents(args.voice, front, args.frames), quant_dtype=None)


if __name__ == "__main__":
    main()
