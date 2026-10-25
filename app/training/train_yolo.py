import argparse
import datetime
import os
from pathlib import Path

from ultralytics import YOLO


def main():
    """Perform transfer learning on a pretrained YOLO model."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="dataset.yaml", help="Path to dataset config YAML")
    parser.add_argument("--epochs", type=int, default=20, help="Number of training epochs")
    parser.add_argument("--imgsz", type=int, default=640, help="Image size")
    parser.add_argument(
        "--name",
        default=None,
        help="Optional model name. Defaults to a datetime-stamped value like smiley_run_20261025_170622"
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[2]
    output_dir = project_root / "saved_models"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    model_name = args.name or f"smiley_run_{timestamp}"

    print("Initializing YOLO pretrained base model (yolov8n.pt)...")
    model = YOLO("yolov8n.pt")

    print(f"Starting transfer learning / fine-tuning for {args.epochs} epochs...")

    model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        project=str(output_dir),
        name=model_name,
        save=True,
        conf=0.25
    )

    print("Training complete!")
    print(f"Best model weights successfully saved to: {output_dir / model_name / 'weights' / 'best.pt'}")


if __name__ == "__main__":
    main()