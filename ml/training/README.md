# Head training

- `make_crops.py`: uses YOLO detection to generate the same pad crops as inference.
- `make_head.py`: trains a scaler + linear head on features from the DINO `.pte` that will be deployed. Uses a sklearn or numpy path.
- `gen_synthetic.py`: synthetic images for pipeline validation. Not real accuracy data.

Raw images and crops go in `data/`; heads and outputs go in `models/`. Use the same preprocessing and features as the `.pte` that will be deployed, and keep the training and evaluation splits separate. For run options see each module's `--help`; for the overall flow see the [ML guide](../README.md).
