import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

def test_api():
    query = "Farmer Schemes"
    lang = "en"
    api_key = os.getenv("MYSCHEME_API_KEY")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Referer": "https://www.myscheme.gov.in/",
        "x-api-key": api_key
    }
    
    # 1. Test Search
    search_api_url = f"https://api.myscheme.gov.in/search/v6/schemes?lang={lang}&q=[]&keyword={query}&sort=&from=0&size=5"
    print(f"Testing Search API: {search_api_url}")
    try:
        resp = requests.get(search_api_url, headers=headers, timeout=10)
        print(f"Status: {resp.status_code}")
        if resp.status_code == 200:
            data = resp.json()
            # print(json.dumps(data, indent=2))
            hits = data.get("data", {}).get("hits", {}).get("items", [])
            print(f"Found {len(hits)} hits.")
            if hits:
                for hit in hits:
                    print(f"- {hit.get('schemeName')} slug: {hit.get('slug')}")
                    
                # 2. Test Details for the first hit
                slug = hits[0].get('slug')
                details_url = f"https://api.myscheme.gov.in/schemes/v6/public/schemes?slug={slug}&lang={lang}"
                print(f"\nTesting Details API for slug '{slug}': {details_url}")
                det_resp = requests.get(details_url, headers=headers, timeout=10)
                print(f"Status: {det_resp.status_code}")
                if det_resp.status_code == 200:
                    det_data = det_resp.json()
                    # print(json.dumps(det_data, indent=2))
                    print("Successfully fetched details.")
                else:
                    print(f"Details failed: {det_resp.text}")
        else:
            print(f"Search failed: {resp.text}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_api()
