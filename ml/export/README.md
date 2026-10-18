# Export and deployment bundle

Holds code that exports trained checkpoints or provided models to `.pte` for the board, plus quantization, output validation and bundle creation tools.

Use the QCS8275 checkout, QAIRT/QNN SDK and export environment supported by the organizers. Do not substitute the latest official version or a different chipset target on your own. The Docker environment definition lives in the parent `ml/`.

Check the input shape, dtype, layout, preprocessing and output contract, then perform the required calibration, quantization, QNN lowering and export. Successfully generating a `.pte` and verifying real board execution and NPU delegation are separate steps.

Results are stored in versioned bundles under `models/`. Besides the model files, prepare the tokenizer, labels, sample inputs, reference outputs and metadata as needed. The board runtime server reads these bundles from a configured path. Export tools are not included in the production server.

## Files

- `export_qnn.py` — YOLO/DINOv2 → QNN HTP `.pte` (x86 Docker, `--quant 16a8w|fp16|8a8w`, `--dry-run` on Mac)
- `export_xnnpack.py` — DINOv2 CLS → XNNPACK CPU `.pte` + parity and speed
- `export_onnx.py` — DINOv2 CLS → ONNX (for reference, e.g. AI Hub)
- `make_bundle.py` — creates a bundle (`bundle.json` + files) for the Vision service
