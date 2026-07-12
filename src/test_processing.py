import cv2
import os
from src.core.preprocessor import ImagePreprocessor

def test_preprocessing():
    # Path from the user's upload (Image 2 - Choices)
    input_path = "C:/Users/M_ilg/.gemini/antigravity/brain/70bd21d3-8d86-4fcc-b9e8-b83651da2549/uploaded_media_1769431490703.png"
    
    if not os.path.exists(input_path):
        print(f"Error: Image not found at {input_path}")
        return

    print(f"Loading image: {input_path}")
    img = cv2.imread(input_path)
    
    print("Applying Preprocessor...")
    processed_img = ImagePreprocessor.process_for_ocr(img)
    
    output_path = "processed_example.png"
    cv2.imwrite(output_path, processed_img)
    print(f"Processed image saved to: {os.path.abspath(output_path)}")
    print("Check this image to see if text is clearly isolated (White on Black).")

if __name__ == "__main__":
    test_preprocessing()
