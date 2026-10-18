# ML configs

Commit the small config files needed to reproduce training, evaluation and export. The file format and loader will be decided during implementation.

- Model ID, weight version, head or layers to train
- Dataset location, label list, train/validation/test split and seed
- Preprocessing spec: input size, normalization, color, dtype/layout
- Training hyperparameters and quantization calibration settings
- QCS8275 target, ExecuTorch/SDK version, export options

Do not include data, SDKs or secrets. Inject personal absolute paths through local environment settings. The preprocessing, label and output specs needed for deployment are also included in the bundle metadata.
