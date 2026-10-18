# Head training

- `make_crops.py`: uses YOLO detection to generate the same pad crops as inference.
- `make_head.py`: trains a scaler + linear head on features from the DINO `.pte` that will be deployed. Logistic regression (sklearn or numpy) or `--model lda` (sklearn, the board v6/v7 head), optionally with `--augment N` train-time copies per crop. `--data` takes several `<class>/` roots, e.g. `data/crops` plus labeled board-camera crops.
- `gen_synthetic.py`: synthetic images for pipeline validation. Not real accuracy data.

Raw images and crops go in `data/`; heads and outputs go in `models/`. Use the same preprocessing and features as the `.pte` that will be deployed, and keep the training and evaluation splits separate. For run options see each module's `--help`; for the overall flow see the [ML guide](../README.md).
