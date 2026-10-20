import os
import argparse
import pickle
from PIL import Image
import numpy as np
from sklearn.linear_model import LogisticRegression

def load_dataset(pos_dir: str, neg_dir: str):
    data = []
    labels = []

    # Load positive images (label = 1)
    for fname in os.listdir(pos_dir):
        if fname.lower().endswith(('.png', '.jpg', '.jpeg')): # TODO - put this allowed files in global
            img = Image.open(os.path.join(pos_dir, fname)).convert('L').resize((64, 64))
            data.append(np.array(img).flatten())
            labels.append(1)
            
    # Load negative images (label = 0)
    for fname in os.listdir(neg_dir):
        if fname.lower().endswith(('.png', '.jpg', '.jpeg')):
            img = Image.open(os.path.join(neg_dir, fname)).convert('L').resize((64, 64))
            data.append(np.array(img).flatten())
            labels.append(0)
            
    return np.array(data), np.array(labels)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--positive-dir", required=True)
    parser.add_argument("--negative-dir", required=True)
    parser.add_argument("--output-path", required=True)
    args = parser.parse_args()

    print("Loading training dataset...")
    X, y = load_dataset(args.positive_dir, args.negative_dir)
    
    print(f"Training model on {len(X)} samples...")
    model = LogisticRegression()
    model.fit(X, y)
    
    os.makedirs(os.path.dirname(args.output_path), exist_ok=True)
    with open(args.output_path, "wb") as f:
        pickle.dump(model, f)
        
    print(f"Model successfully saved to {args.output_path}")

if __name__ == "__main__":
    main()