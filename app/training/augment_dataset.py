import os
import random
import glob
from PIL import Image

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
    # Your directories
    img_train_dir = r"C:\Users\PC\SmileyDetect\dataset\images\train"
    lbl_train_dir = r"C:\Users\PC\SmileyDetect\dataset\labels\train"
    
    os.makedirs(lbl_train_dir, exist_ok=True)
    
    # Gather all images currently in the train folder
    all_images = glob.glob(os.path.join(img_train_dir, "*.JPG")) + glob.glob(os.path.join(img_train_dir, "*.jpg"))
    
    if not all_images:
        print(f"Error: No images found in {img_train_dir}!")
        exit(1)
        
    pos_files = []
    neg_files = []
    
    # Separate positives and negatives based on filename
    for img_path in all_images:
        filename = os.path.basename(img_path)
        # If filename starts with 'n' or 'N', treat as negative
        if filename.lower().startswith('n'):
            neg_files.append(img_path)
        else:
            pos_files.append(img_path)
            
    print(f"Found {len(pos_files)} positive and {len(neg_files)} negative source images.")

    # STEP 1: Generate base labels for your original raw crops so YOLO can read them
    print("Generating labels for original raw crops...")
    for img_path in all_images:
        filename = os.path.basename(img_path)
        base_name, _ = os.path.splitext(filename)
        lbl_path = os.path.join(lbl_train_dir, f"{base_name}.txt")
        
        if filename.lower().startswith('n'):
            # Negative image -> empty label file
            open(lbl_path, "w").close()
        else:
            # Positive tight crop -> full frame bounding box
            with open(lbl_path, "w") as f:
                f.write("0 0.5 0.5 1.0 1.0\n")
                
    # STEP 2: Generate augmented variations (scale, rotate, random placement)
    num_pos_aug = 100  # Number of augmented positive images to create
    num_neg_aug = 100  # Number of augmented negative images to create
    
    print(f"Generating {num_pos_aug} augmented positive samples...")
    for i in range(num_pos_aug):
        if not pos_files: break
        src_file = random.choice(pos_files)
        bg, xc, yc, w, h = augment_and_place(src_file)
        if bg is None: continue
        
        name = f"aug_pos_{i:03d}"
        bg.save(os.path.join(img_train_dir, f"{name}.jpg"))
        with open(os.path.join(lbl_train_dir, f"{name}.txt"), "w") as f:
            f.write(f"0 {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}\n")
            
    print(f"Generating {num_neg_aug} augmented negative samples...")
    for i in range(num_neg_aug):
        if not neg_files: break
        src_file = random.choice(neg_files)
        bg, xc, yc, w, h = augment_and_place(src_file)
        if bg is None: continue
        
        name = f"aug_neg_{i:03d}"
        bg.save(os.path.join(img_train_dir, f"{name}.jpg"))
        open(os.path.join(lbl_train_dir, f"{name}.txt"), "w").close()
        
    print("Success! All original crops are labeled, and augmented samples have been added.")