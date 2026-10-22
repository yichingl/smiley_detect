import os
import argparse
from ultralytics import YOLO

def main():

    """ Perform transfer learning on pretrained yolo model. """
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="dataset.yaml", help="Path to dataset config YAML")
    parser.add_argument("--epochs", type=int, default=20, help="Number of training epochs")
    parser.add_argument("--imgsz", type=int, default=640, help="Image size")
    args = parser.parse_args()

    # Define your target output directory explicitly
    output_dir = r"C:\Users\PC\SmileyDetect\saved_models"
    os.makedirs(output_dir, exist_ok=True)

    print("Initializing YOLO pretrained base model (yolov8n.pt)...")
    model = YOLO("yolov8n.pt")

    print(f"Starting transfer learning / fine-tuning for {args.epochs} epochs...")
    
    # Train the model. 
    # 'project' points to your saved_models folder.
    # 'name' defines the subfolder name where weights/best.pt will be generated.
    results = model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        project=output_dir,
        name="smiley_run",
        save=True,
        conf=0.25
    )

    print("Training complete!")
    print(f"Best model weights successfully saved to: {output_dir}\\smiley_run\\weights\\best.pt")

if __name__ == "__main__":
    main()