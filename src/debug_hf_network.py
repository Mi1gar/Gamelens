import requests
import os

url = "https://huggingface.co/Helsinki-NLP/opus-mt-en-tr/resolve/main/config.json"
print(f"Testing access to: {url}")
try:
    s = requests.Session()
    s.trust_env = False 
    s.auth = None
    s.headers.pop('Authorization', None)
    
    resp = s.get(url)
    
    print("--- REQUEST DEBUG ---")
    print(f"Request Headers: {resp.request.headers}")
    
    import os
    print("--- ENV DEBUG ---")
    for k, v in os.environ.items():
        if "TOKEN" in k.upper() or "AUTH" in k.upper() or "HUGGING" in k.upper():
            print(f"{k}: {v[:5]}...")
            
    print(f"Status Code: {resp.status_code}")
    print(f"Final URL: {resp.url}")
    print(f"Redirect History: {resp.history}")
    
    if resp.status_code == 200:
        print("SUCCESS")
    else:
        print(f"FAIL: {resp.text[:100]}")
except Exception as e:
    print(f"EXCEPTION: {e}")
