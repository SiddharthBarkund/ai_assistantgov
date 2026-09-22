import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

def debug_state_extraction():
    query = "skilled youth"
    lang = "en"
    api_key = os.getenv("MYSCHEME_API_KEY")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.myscheme.gov.in/",
        "Origin": "https://www.myscheme.gov.in",
        "x-api-key": api_key,
        "Accept": "application/json, text/plain, */*",
    }
    
    url = f"https://api.myscheme.gov.in/search/v6/schemes?lang={lang}&q=[]&keyword={query}&sort=&from=0&size=2"
    
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        hits = data.get("data", {}).get("hits", {}).get("items", [])
        if hits:
            item = hits[0]
            fields = item.get("fields", {})
            # Print everything in fields slowly
            for k, v in fields.items():
                print(f"{k}: {v}")
    else:
        print(f"Error {resp.status_code}")

if __name__ == "__main__":
    debug_state_extraction()
