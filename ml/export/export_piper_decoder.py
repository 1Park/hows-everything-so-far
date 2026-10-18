"""Export the Piper TTS decoder (HiFi-GAN) to a fixed-length ExecuTorch QNN (fp16) .pte — run in the board ExecuTorch venv.

The Piper voice .onnx is split into a front part (phonemes, duration prediction, flow; output length varies
per input) and the decoder (Conv/ConvTranspose only) (services/tts/backend.split_voice). Only the decoder is
exported for the NPU, with the latent length fixed at N frames. Per sentence the service picks the smallest
.pte with n <= N, zero-pads, runs it, and trims the output to n*256 samples.

  source ~/git/executorch/.venv/bin/activate   # + pip install onnx2torch piper-tts
  export PYTHONPATH=$HOME/git:$PWD FLATC_EXECUTABLE=... QNN_SDK_ROOT=~/qnn_sdk_root   (BOARD_RUNBOOK)
  python -m ml.export.export_piper_decoder --voice models/board/tts/en_US-hfc_female-medium.onnx \
      --frames 384 --soc_model QCS8275 --build_folder ~/git/executorch/build-x86 --compile_only
  → models/board/tts/en_US-hfc_female-medium.dec_f384.pte  (11 MB, 2 min 35 s, 0 ops unsupported on NPU)

2026-10-18 board: a demo line's latent is 150-335 frames -> a single 384 covers it. The 128/256-frame exports hung at the QNN
"VTCM Allocation" step for over 15 min and were aborted (384 takes 2.3 s at the same step).
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
    """Build real sentence latents with the front graph to use as export sample inputs (fp16, so not for calibration)."""
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
    ap.add_argument("--voice", required=True, help="Piper voice .onnx (.onnx.json in the same folder)")
    ap.add_argument("--frames", type=int, required=True, help="fixed latent length (1 frame = 256 samples)")
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
