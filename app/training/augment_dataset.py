import os
import random
import glob
from PIL import Image

# to run, call at root: python -m app.training.augment_dataset

def augment_and_place(image_path, bg_size=1000):
    """Loads a tight crop, scales, rotates, and places it randomly on a background canvas."""
    img = Image.open(image_path).convert("L")
    
    # 1. Random Scaling (0.5x smaller to 1.5x larger)
    scale_factor = random.uniform(0.5, 1.5)
    new_w = int(img.width * scale_factor)
    new_h = int(img.height * scale_factor)
    img = img.resize((new_w, new_h), Image.Resampling.BILINEAR)
    
    # 2. Random Rotation (-30 to 30 degrees, expanding canvas)
    angle = random.uniform(-30, 30)
    img = img.rotate(angle, expand=True, fillcolor=255)
    
    sw, sh = img.size
    if sw >= bg_size or sh >= bg_size:
        return None, None, None, None, None  # Skip if scaled crop is larger than canvas
        
    # 3. Create a blank white background canvas (1000x1000)
    bg = Image.new("L", (bg_size, bg_size), color=255)
    
    # 4. Pick random valid (x, y) coordinates for placement
    x_min = random.randint(0, bg_size - sw)
    y_min = random.randint(0, bg_size - sh)
    x_max = x_min + sw
    y_max = y_min + sh
    
    bg.paste(img, (x_min, y_min))
    
    # 5. Compute normalized YOLO coordinates [x_center, y_center, width, height]
    x_center = ((x_min + x_max) / 2) / bg_size
    y_center = ((y_min + y_max) / 2) / bg_size
    width = sw / bg_size
    height = sh / bg_size
    
    return bg, x_center, y_center, width, height

if __name__ == "__main__":
    # Define your source directories containing your original crops
    pos_src_dir = r"C:\Users\PC\SmileyDetect\training_files\positive"
    neg_src_dir = r"C:\Users\PC\SmileyDetect\training_files\negative"
    
    # YOLO dataset destination directories
    img_train_dir = r"C:\Users\PC\SmileyDetect\dataset\images\train"
    lbl_train_dir = r"C:\Users\PC\SmileyDetect\dataset\labels\train"
    
    os.makedirs(img_train_dir, exist_ok=True)
    os.makedirs(lbl_train_dir, exist_ok=True)
    
    # Gather source images
    pos_files = glob.glob(os.path.join(pos_src_dir, "*.JPG")) + glob.glob(os.path.join(pos_src_dir, "*.jpg"))
    neg_files = glob.glob(os.path.join(neg_src_dir, "*.JPG")) + glob.glob(os.path.join(neg_src_dir, "*.jpg"))
    
    if not pos_files:
        print(f"Error: No positive images found in {pos_src_dir} (Expected 1.JPG to 48.JPG)")
        exit(1)
    if not neg_files:
        print(f"Error: No negative images found in {neg_src_dir} (Expected n1.JPG to n35.JPG)")
        exit(1)
        
    # Set how many augmented variations you want to generate for each set
    num_pos_to_generate = 100  # Generates 100 positive training samples
    num_neg_to_generate = 100  # Generates 100 negative training samples
    
    print(f"Generating {num_pos_to_generate} augmented positive samples...")
    for i in range(num_pos_to_generate):
        src_file = random.choice(pos_files)
        bg, xc, yc, w, h = augment_and_place(src_file)
        if bg is None: continue
        
        filename = f"pos_aug_{i:03d}"
        img_path = os.path.join(img_train_dir, f"{filename}.jpg")
        lbl_path = os.path.join(lbl_train_dir, f"{filename}.txt")
        
        bg.save(img_path)
        # Write valid YOLO bounding box for positives
        with open(lbl_path, "w") as f:
            f.write(f"0 {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}\n")
            
    print(f"Generating {num_neg_to_generate} augmented negative samples...")
    for i in range(num_neg_to_generate):
        src_file = random.choice(neg_files)
        bg, xc, yc, w, h = augment_and_place(src_file)
        if bg is None: continue
        
        filename = f"neg_aug_{i:03d}"
        img_path = os.path.join(img_train_dir, f"{filename}.jpg")
        lbl_path = os.path.join(lbl_train_dir, f"{filename}.txt")
        
        bg.save(img_path)
        # Write an completely empty .txt file (0 bytes) for negatives[cite: 3]
        open(lbl_path, "w").close()
        
    print("Success! Both positive and negative sets have been augmented and saved to:")
    print(f" - Images: {img_train_dir}")
    print(f" - Labels: {lbl_train_dir}")