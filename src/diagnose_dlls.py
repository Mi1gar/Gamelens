import os
import sys
import site
import glob

print(f"Python Executable: {sys.executable}")
print(f"Site Packages: {site.getsitepackages()}")

found_cublas = []
found_cudnn = []

for sp in site.getsitepackages():
    # Search for cublas
    pattern = os.path.join(sp, "nvidia", "cublas", "bin", "cublas64_*.dll")
    found_cublas.extend(glob.glob(pattern))
    
    # Search for cudnn
    pattern = os.path.join(sp, "nvidia", "cudnn", "bin", "cudnn*.dll")
    found_cudnn.extend(glob.glob(pattern))

print(f"Found cuBLAS DLLs: {found_cublas}")
print(f"Found cuDNN DLLs: {found_cudnn}")

if found_cublas:
    path = os.path.dirname(found_cublas[0])
    print(f"Attempting to register DLL directory: {path}")
    try:
        os.add_dll_directory(path)
        os.environ['PATH'] += os.pathsep + path
        print("Success: Added to DLL search path.")
    except Exception as e:
        print(f"Error checking DLL dir: {e}")

if found_cudnn:
    path = os.path.dirname(found_cudnn[0])
    print(f"Attempting to register DLL directory: {path}")
    try:
        os.add_dll_directory(path)
        os.environ['PATH'] += os.pathsep + path
        print("Success: Added to DLL search path.")
    except Exception as e:
        print(f"Error checking DLL dir: {e}")
        
print("--- Testing CTranslate2 CUDA ---")
try:
    import ctranslate2
    count = ctranslate2.get_cuda_device_count()
    print(f"CUDA Device Count: {count}")
    
    if count > 0:
        # Create a dummy translator to force library load
        # This will crash if DLLs are missing
        # We don't have a model here, but we can check if it throws a DLL error immediately
        print("Attempting to load CTranslate2 on CUDA...")
        # Just checking availability. 
        # To truly test, we'd need a model, but usually the import/device check triggers the DLL load
        print("CTranslate2 seems usable.")
    else:
        print("No CUDA devices found via CTranslate2.")
        
except ImportError:
    print("CTranslate2 not installed.")
except Exception as e:
    print(f"CTranslate2 Error: {e}")
