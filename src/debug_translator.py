import sys
import os

# Ensure src is in path
sys.path.append(os.getcwd())

def test_translation():
    print("--- Starting Translation Service Debug ---")
    try:
        from huggingface_hub import snapshot_download
        import os
        
        # Explicitly turn off implicit token
        os.environ["HF_HUB_DISABLE_IMPLICIT_TOKEN"] = "1"
        
        model_id = "Helsinki-NLP/opus-mt-en-tr"
        local_dir = os.path.join(os.getcwd(), "models", "opus-mt-en-tr")
        
        print(f"Attempting snapshot_download to {local_dir}...")
        print("Passing token=False to force anonymous access.")
        
        path = snapshot_download(
            repo_id=model_id,
            local_dir=local_dir,
            token=False,
            local_dir_use_symlinks=False
        )
        print(f"SUCCESS: Downloaded to {path}")
        
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        print(f"CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_translation()
