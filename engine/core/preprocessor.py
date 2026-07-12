import cv2
import numpy as np

class ImagePreprocessor:
    @staticmethod
    def process_for_ocr(img: np.ndarray, profile: str = "generic") -> np.ndarray:
        """
        Preprocesses an image to make text stand out for OCR.
        Strategies:
        1. Grayscale
        2. Thresholding (Keep bright stuff, kill dark stuff)
        """
        # Convert to HSV to separate brightness (Value) from Color
        # Input is already BGR
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        
        if profile == "firewatch_colored":
             # Firewatch: Bright text (Orange/White) on dark background.
             # Value channel threshold is usually enough.
            v = hsv[:, :, 2]
            _, binary = cv2.threshold(v, 150, 255, cv2.THRESH_BINARY)
            kernel = np.ones((2,2), np.uint8)
            processed = cv2.dilate(binary, kernel, iterations=1)
            return processed
            
        elif profile == "metro_orange":
            # Metro 2033: Strict Orange Subtitles.
            # Using simple brightness picks up game lights/fire. 
            # We MUST filter by Color (Hue/Sat).
            
            # 1. Color Masking (Region of Interest)
            # Relaxed range significantly to catch edges
            lower_orange = np.array([5, 120, 80]) 
            upper_orange = np.array([30, 255, 255])
            color_mask = cv2.inRange(hsv, lower_orange, upper_orange)
            
            # Mask Density Check
            # Reduced to 15% as per user feedback (Metro env is noisy)
            if cv2.countNonZero(color_mask) / color_mask.size > 0.15:
                 return np.zeros_like(color_mask)

            # 2. Extract Value Channel (Brightness)
            v = hsv[:, :, 2]
            
            # 3. Apply Color Mask to Value
            masked_v = cv2.bitwise_and(v, v, mask=color_mask)
            
            # 4. Otsu Thresholding
            _, binary = cv2.threshold(masked_v, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            # 5. SHAPE FILTERING (Connected Components) - The "Missing Layer"
            # Remove noise blobs based on geometry before Upscaling
            filtered_binary = ImagePreprocessor.filter_text_components(binary)
            
            # 6. Upscale (Linear is smoother than Cubic for binary)
            # We scale up 2.5x to give OCR more details.
            scaled = cv2.resize(filtered_binary, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_LINEAR)
            
            # 7. Moderate Dilation
            # Dilation connects broken characters
            kernel = np.ones((2,2), np.uint8)
            processed = cv2.dilate(scaled, kernel, iterations=1)
            
            return processed
            
        elif profile == "subtitle":
            # Proven preprocessing from live_test_optimized.py.
            # CLAHE (2.0) + Otsu — tested on 211 RDR2 frames, 0.993 OCR score.
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            h = gray.shape[0]
            # Upscale small text regions for better OCR
            if h < 55:
                gray = cv2.resize(
                    gray, None, fx=3, fy=3,
                    interpolation=cv2.INTER_LINEAR,
                )
            enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
            _, binary = cv2.threshold(
                enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU,
            )
            # Ensure text=white(255), bg=black(0) for line splitting
            # Invert if top rows are mostly white (text is dark on light bg)
            if cv2.mean(binary[:5, :])[0] > 128:
                binary = cv2.bitwise_not(binary)
            return binary

        else:
            # Generic fallback (kept for backward compatibility)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
            return binary

    @staticmethod
    def filter_text_components(binary_img: np.ndarray) -> np.ndarray:
        """
        Analyzes connected components and removes blobs that don't look like text.
        """
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary_img, connectivity=8)
        
        # New mask to draw valid components on
        filtered_mask = np.zeros_like(binary_img)
        
        # Image dims
        h_img, w_img = binary_img.shape
        
        for i in range(1, num_labels): # Skip background (0)
            x = stats[i, cv2.CC_STAT_LEFT]
            y = stats[i, cv2.CC_STAT_TOP]
            w = stats[i, cv2.CC_STAT_WIDTH]
            h = stats[i, cv2.CC_STAT_HEIGHT]
            area = stats[i, cv2.CC_STAT_AREA]
            
            # Heuristics for Subtitle Characters (in a ~120px strip)
            
            # 1. Border Check
            # Text shouldn't be touching the very top of the crop region.
            # Environmental noise often bleeds in from the top (guns, hands).
            # We allow bottom touch because subtitles might be very low.
            if y < 2:
                continue

            # 2. Area Check
            # Too small = noise speck (e.g. < 10 pixels)
            # Too big = huge structure/panel. 
            # Since this is BEFORE dilation, we are looking at single letters.
            # A distinct letter 'M' is rarely > 1500 pixels.
            if area < 10 or area > 1500:
                continue
                
            # 3. Height Check
            # Subtitle text usually has a consistent height range.
            # Single line text is ~20-40px. 
            if h < 8 or h > 60: # Reduced from 80
                continue
                
            # 4. Aspect Ratio Check
            # Text characters usually aren't extremely wide or extremely tall strips.
            aspect_ratio = w / h
            if aspect_ratio > 10: # Very long horizontal line
                continue
                
            # If passed, keep it
            # We can use the label mask to copy exactly those pixels
            filtered_mask[labels == i] = 255
            
        return filtered_mask

    @staticmethod
    def isolate_ranges(img: np.ndarray) -> np.ndarray:
        # Advanced: If we want ONLY orange text
        # orange_lower = np.array([10, 100, 100]) ...
        pass
