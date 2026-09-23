import csv
import requests
import os
import glob
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

headers = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "resolution=merge-duplicates"
}

def upload_csv_files():
    csv_pattern = r"c:\Users\Siddharth\Downloads\indian_schemes_*.csv"
    csv_files = glob.glob(csv_pattern)
    
    if not csv_files:
        print("❌ No CSV files found.")
        return

    target_table = "indian_schemes"
    seen_ids = set()
    total_files = len(csv_files)
    
    print(f"🚀 Starting upload of {total_files} files...")

    for idx, file_path in enumerate(csv_files, 1):
        filename = os.path.basename(file_path)
        print(f"[{idx}/{total_files}] 📖 Reading {filename}...")
        
        records = []
        try:
            with open(file_path, mode='r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    sid = int(row["Scheme_ID"])
                    if sid in seen_ids: continue
                    seen_ids.add(sid)
                    records.append({
                        "scheme_id": sid,
                        "scheme_name": row["Scheme_Name"],
                        "category": row["Category"],
                        "state_type": row["Type"]
                    })
            
            if not records:
                print(f"   ⚠️ No new records.")
                continue

            print(f"   ⬆️ Uploading {len(records)} unique records...")
            chunk_size = 100 # Batching to be faster
            for i in range(0, len(records), chunk_size):
                chunk = records[i:i + chunk_size]
                resp = requests.post(
                    f"{SUPABASE_URL}/rest/v1/{target_table}",
                    headers=headers,
                    json=chunk,
                    timeout=30
                )
                if resp.status_code not in [200, 201, 204]:
                    print(f"   ❌ Error at {i}: {resp.text}")
                else:
                    print(f"   ✅ Chunk {i//chunk_size + 1} done.")
                        
        except Exception as e:
            print(f"❌ Critical error in {filename}: {e}")
            
    print(f"\n✨ FINISHED! Total unique schemes in database: {len(seen_ids)}")

if __name__ == "__main__":
    upload_csv_files()
