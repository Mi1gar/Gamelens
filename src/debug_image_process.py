import cv2
import numpy as np
import os
import sys

# Ensure src is in path
sys.path.append(os.getcwd())
from src.core.preprocessor import ImagePreprocessor

def main():
    # User's uploaded image path
    image_path = "C:/Users/M_ilg/.gemini/antigravity/brain/1ee9638e-52de-4e42-bd21-997f9d62dd6c/uploaded_media_1769605969547.png"
    
    if not os.path.exists(image_path):
        print(f"Error: Image not found at {image_path}")
        return

    print(f"Loading image: {image_path}")
    full_img = cv2.imread(image_path)
    if full_img is None:
        print("Error: Failed to load image.")
        return

    # Simulate MetroAdapter capture region
    # EXPANDED REGION for multi-line support
    # We can do this because our "Shape Filter" is good at ignoring the gun/floor.
    # New Target: Y=750 to 1050 (Height 300)
    target_x, target_y, target_w, target_h = 300, 750, 1320, 300
    
    img_h, img_w = full_img.shape[:2]
    print(f"Image Size: {img_w}x{img_h}")

    # Safe Crop (Clamp to image bounds)
    x = max(0, min(target_x, img_w - 1))
    y = max(0, min(target_y, img_h - 1))
    w = min(target_w, img_w - x)
    h = min(target_h, img_h - y)
    
    if w <= 0 or h <= 0:
        print(f"Error: Invalid crop dimensions: {w}x{h}")
        return
    
    crop_img = full_img[y:y+h, x:x+w]
    
    print(f"Cropped region: {w}x{h}")
    cv2.imwrite("debug_cropped_input.png", crop_img) # Save intermediate

    # Process
    print("Running ImagePreprocessor...")
    processed = ImagePreprocessor.process_for_ocr(crop_img, profile="metro_orange")
    
    output_path = "debug_final_ocr_input.png"
    cv2.imwrite(output_path, processed)
    print(f"Saved processed output to: {os.path.abspath(output_path)}")

if __name__ == "__main__":
    main()
