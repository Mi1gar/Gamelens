import argostranslate.package
import argostranslate.translate
import time
import os
import sys

# Register NVIDIA DLLs (Robust Search Method)
def register_nvidia_dlls():
    try:
        import site
        import glob
        
        # Search all site-package directories (User, System, Venv)
        site_dirs = site.getsitepackages()
        
        # Also check user base just in case
        try:
            site_dirs.append(site.getusersitepackages())
        except:
            pass
            
        dll_paths_to_add = set()
        
        for sp in site_dirs:
            # Look for cublas
            cublas_bins = glob.glob(os.path.join(sp, "nvidia", "cublas", "bin"))
            if cublas_bins:
                 dll_paths_to_add.add(cublas_bins[0])
                 
            # Look for cudnn
            cudnn_bins = glob.glob(os.path.join(sp, "nvidia", "cudnn", "bin"))
            if cudnn_bins:
                 dll_paths_to_add.add(cudnn_bins[0])

            # Look for cuda_runtime
            runtime_bins = glob.glob(os.path.join(sp, "nvidia", "cuda_runtime", "bin"))
            if runtime_bins:
                 dll_paths_to_add.add(runtime_bins[0])
        
        if not dll_paths_to_add:
            print("[Translator] Warning: Could not find nvidia/cublas/bin or cudnn/bin in site-packages.")
            
        for path in dll_paths_to_add:
            print(f"[Translator] Registering DLL Path: {path}")
            if os.path.exists(path):
                # Add to Python DLL search path (essential for Py3.8+)
                try:
                    os.add_dll_directory(path)
                except Exception as e:
                    print(f"[Translator] os.add_dll_directory failed for {path}: {e}")
                # Add to System PATH (essential for some C++ extensions)
                if path not in os.environ['PATH']:
                     os.environ['PATH'] = path + os.pathsep + os.environ['PATH']
                     
    except Exception as e:
        print(f"[Translator] DLL Reg Warning: {e}")

register_nvidia_dlls()

class TranslationService:
    def __init__(self, target_lang='tr'):
        self.target_lang = target_lang
        self._cache = {}
        
        # Check and Enable GPU (CUDA)
        import ctranslate2
        import argostranslate.settings
        
        try:
            if ctranslate2.get_cuda_device_count() > 0:
                print(f"[Translator] NVIDIA GPU Detected. Testing CUDA compatibility...")
                argostranslate.settings.device = "cuda"
                
                # Verify it actually works (catch DLL errors here)
                try:
                    argostranslate.translate.translate("test", "en", self.target_lang)
                    print(f"[Translator] CUDA verified. GPU Acceleration ENABLED.")
                except Exception as cuda_err:
                    print(f"[Translator] CUDA Test Failed: {cuda_err}")
                    print(f"[Translator] Missing 'cublas64_12.dll' or compatible driver.")
                    print(f"[Translator] Reverting to CPU mode for stability.")
                    argostranslate.settings.device = "cpu"
            else:
                print(f"[Translator] No GPU detected. Running on CPU.")
                argostranslate.settings.device = "cpu"
                
            # Optimize for Speed (Greedy Search)
            # Default is 5. reducing to 1 gives ~3x speedup with minimal quality loss for games.
            argostranslate.settings.beam_size = 1
            
            # Optimize for Throughput (Quantization)
            # Use INT8 quantization (approx 2x faster than FP32)
            if argostranslate.settings.device == "cuda":
                print(f"[Translator] Enabled INT8 Quantization for max speed.")
                argostranslate.settings.compute_type = "int8"
            
        except Exception as e:
            print(f"[Translator] GPU Init failed ({e}). Defaulting to CPU.")

        # Helper for quality improvement
        print("[Translator] Initializing Enhanced Argos Engine...")
        
        try:
            installed = argostranslate.package.get_installed_packages()
            
            # --- Game Detection & Logic Hook ---
            from .game_detector import GameDetector
            from .subtitle_loader import get_loader
            from .manual_translations import TranslationMemory
            
            print("[Translator] Attempting to detect game...")
            game_path = GameDetector.auto_detect()
            
            if game_path:
                print(f"[Translator] Game detected at: {game_path}")
                # Tell loader to scan this path
                get_loader().set_root_path(game_path)
            else:
                print("[Translator] Game not detected automatically.")
                print("[Translator] Please select the game's installation folder if manual loading is needed.")
                
            # Warm-up (also triggers manual translations loading which now pulls from loader)
            argostranslate.translate.translate("Hello", "en", self.target_lang)
            print("[Translator] Model and Custom Overrides loaded and ready.")
        except Exception as e:
            print(f"[Translator] Init failed: {e}")
        
    def translate(self, text: str) -> str:
        if not text:
            return ""
            
        if text in self._cache:
            return self._cache[text]
            
        # 1. Normalize Text (AI-Like Preprocessing)
        # Fixes slang: "gonna" -> "going to", "c'mon" -> "come on"
        # Fixes entities: "Hunter" -> "Hunter" (Capitalized)
        from .text_cleaner import TextNormalizer
        clean_text = TextNormalizer.normalize(text)
        
        
        # 1.5. Check Manual Overrides (Dictionary Cache + Fuzzy)
        # This provides 0ms latency and 100% accuracy for common phrases
        from .manual_translations import TranslationMemory
        
        # Using fuzzy matcher (0.85 similarity) to catch OCR typos
        manual_result = TranslationMemory.get_fuzzy(clean_text, cutoff=0.85)
        
        if manual_result:
            print(f"[Translator] [Hybrid] '{text[:15]}...' -> '{manual_result[:15]}...' (0.00ms)")
            self._cache[text] = manual_result
            return manual_result
            
        try:
            t0 = time.time()
            
            # 2. Translate Normalized Text
            result = argostranslate.translate.translate(clean_text, "en", self.target_lang)
            
            dt = time.time() - t0
            
            # Log for user confidence
            print(f"[Translator] '{clean_text[:15]}...' -> '{result[:15]}...' ({dt*1000:.2f}ms)")
            
            # 3. Log for Quality Control (CSV)
            try:
                log_dir = os.path.join(os.getcwd(), "logs")
                os.makedirs(log_dir, exist_ok=True)
                log_file = os.path.join(log_dir, "translations.csv")
                
                # Check if need header
                need_header = not os.path.exists(log_file)
                
                import csv
                import datetime
                
                with open(log_file, "a", encoding="utf-8-sig", newline="") as f:
                    writer = csv.writer(f)
                    if need_header:
                        writer.writerow(["Timestamp", "Original", "Normalized", "Translated", "LatencyMs"])
                    
                    writer.writerow([
                        datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        text,
                        clean_text,
                        result,
                        f"{dt*1000:.2f}"
                    ])
            except Exception as log_err:
                print(f"[Translator] Logging Failed: {log_err}")
            
            self._cache[text] = result
            return result
        except Exception as e:
            print(f"[Translator] Error: {e}")
            self._cache[text] = text
            return text
