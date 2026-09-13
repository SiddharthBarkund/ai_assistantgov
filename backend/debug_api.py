import os
import requests
import json

def debug_search_api():
    query = "farmer"
    lang = "en"
    api_key = os.getenv("MYSCHEME_API_KEY")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.myscheme.gov.in/",
        "Origin": "https://www.myscheme.gov.in",
        "x-api-key": api_key,
        "Accept": "application/json, text/plain, */*",
    }
    
    url = f"https://api.myscheme.gov.in/search/v6/schemes?lang={lang}&q=[]&keyword={query}&sort=&from=0&size=5"
    
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        data = resp.json()
        hits = data.get("data", {}).get("hits", {}).get("items", [])
        if hits:
            item = hits[0]
            print("Fields keys:", item.get("fields", {}).keys())
            fields = item.get("fields", {})
            print("Scheme name (from fields):", fields.get("schemeName"))
            print("Slug (from fields):", fields.get("slug"))
            print("Ministry (from fields):", fields.get("nodalMinistryName", {}).get("label"))
        else:
            print("No hits found.")

if __name__ == "__main__":
    debug_search_api()
