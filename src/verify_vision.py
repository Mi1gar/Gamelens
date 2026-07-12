from src.core.vision import ScreenCapture
import time
import os

def test_capture():
    print("Initializing ScreenCapture...")
    vision = ScreenCapture()
    
    # Firewatch Strategy: Multi-Zone
    # Region 1: Center (Dialogue Choices / Narration)
    # Region 2: Bottom (Subtitles)
    
    # 1. Center: Left=40%, Top=30%, Width=20%, Height=30% (Approx for choices)
    #    (768, 324, 384, 324)
    # 2. Bottom: Left=20%, Top=80%, Width=60%, Height=15%
    #    (384, 864, 1152, 162)
    
    # Note: For stitching, widths should ideally match or be handled. 
    # Let's use same width for both to avoid padding artifacts (Width=1152)
    
    region_center = (384, 300, 1152, 400) # Wide center
    region_bottom = (384, 864, 1152, 162) # Wide bottom
    
    print(f"Capturing Multi-Zone: Center + Bottom")
    
    img = vision.capture_multi_region([region_center, region_bottom])
    print(f"Capture successful. Stitched Shape: {img.shape}")
    
    output_file = "firewatch_multizone.png"
    vision.save_snapshot(img, output_file)
    print(f"Snapshot saved to {os.path.abspath(output_file)}")

if __name__ == "__main__":
    test_capture()
