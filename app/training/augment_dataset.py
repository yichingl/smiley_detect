import os
import random
import glob
from PIL import Image

def augment_and_place(image_path, bg_size=1000):
    """Loads a tight crop, scales, optionally mirrors horizontally, and places it randomly on a canvas."""
    img = Image.open(image_path).convert("L")
    
    # 1. Random Scaling (0.5x smaller to 1.5x larger)
    scale_factor = random.uniform(0.5, 1.5)
    new_w = int(img.width * scale_factor)
    new_h = int(img.height * scale_factor)
    img = img.resize((new_w, new_h), Image.Resampling.BILINEAR)
    
    # 2. Random Horizontal Mirroring (50% chance to flip left-to-right)
    if random.random() > 0.5:
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
        
    # (Note: Rotation is kept at 0 degrees for upright-only faces)
    
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
    img_train_dir = r"C:\Users\PC\SmileyDetect\dataset\images\train"
    lbl_train_dir = r"C:\Users\PC\SmileyDetect\dataset\labels\train"
    
    os.makedirs(lbl_train_dir, exist_ok=True)
    
    all_images = glob.glob(os.path.join(img_train_dir, "*.JPG")) + glob.glob(os.path.join(img_train_dir, "*.jpg"))
    
    if not all_images:
        print(f"Error: No images found in {img_train_dir}!")
        exit(1)
        
    pos_files = []
    neg_files = []
    
    for img_path in all_images:
        filename = os.path.basename(img_path)
        if filename.lower().startswith('n'):
            neg_files.append(img_path)
        else:
            pos_files.append(img_path)
            
    print(f"Found {len(pos_files)} positive and {len(neg_files)} negative source images.")
    
    # STEP 1: Generate base labels for your original raw crops
    print("Generating labels for original raw crops...")
    for img_path in all_images:
        filename = os.path.basename(img_path)
        base_name, _ = os.path.splitext(filename)
        lbl_path = os.path.join(lbl_train_dir, f"{base_name}.txt")
        
        if filename.lower().startswith('n'):
            open(lbl_path, "w").close()
        else:
            with open(lbl_path, "w") as f:
                f.write("0 0.5 0.5 1.0 1.0\n")
                
    # STEP 2: Generate augmented variations (scale, mirror, random placement)
    num_pos_aug = 200
    num_neg_aug = 200
    
    print(f"Generating {num_pos_aug} augmented positive samples (with mirroring)...")
    for i in range(num_pos_aug):
        if not pos_files: break
        src_file = random.choice(pos_files)
        bg, xc, yc, w, h = augment_and_place(src_file)
        if bg is None: continue
        
        name = f"aug_pos_{i:03d}"
        bg.save(os.path.join(img_train_dir, f"{name}.jpg"))
        with open(os.path.join(lbl_train_dir, f"{name}.txt"), "w") as f:
            f.write(f"0 {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}\n")
            
    print(f"Generating {num_neg_aug} augmented negative samples (with mirroring)...")
    for i in range(num_neg_aug):
        if not neg_files: break
        src_file = random.choice(neg_files)
        bg, xc, yc, w, h = augment_and_place(src_file)
        if bg is None: continue
        
        name = f"aug_neg_{i:03d}"
        bg.save(os.path.join(img_train_dir, f"{name}.jpg"))
        open(os.path.join(lbl_train_dir, f"{name}.txt"), "w").close()
        
    print("Success! Mirroring and scaling augmentation complete.")