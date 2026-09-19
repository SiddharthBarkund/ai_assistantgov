"""
Upload existing dataset chunks to Supabase
==========================================
This script reads your local myscheme_chunks.pkl file,
generates embeddings, and uploads everything to Supabase
using direct REST API calls (no supabase SDK needed).

Run this ONCE after setting up Supabase tables.
"""

import os
import pickle
import requests
import json
import numpy as np
from dotenv import load_dotenv

load_dotenv()

# =============================================
# Configuration
# =============================================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
CHUNKS_PATH = "myscheme_chunks.pkl"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
BATCH_SIZE = 50  # Upload in batches to avoid timeouts


def main():
    # --- Check Supabase credentials ---
    if not SUPABASE_URL or not SUPABASE_KEY or SUPABASE_URL == "your-supabase-url-here":
        print("[ERROR] SUPABASE_URL and SUPABASE_KEY must be set in .env file!")
        print("  Add these lines to your .env file:")
        print("  SUPABASE_URL=https://your-project-id.supabase.co")
        print("  SUPABASE_KEY=your-anon-key-here")
        return

    # --- Import sentence transformers ---
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("[ERROR] sentence-transformers not installed!")
        print("  Run: pip install sentence-transformers")
        return

    # --- Test Supabase connection ---
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }

    print("[0/4] Testing Supabase connection...")
    test_resp = requests.get(
        f"{SUPABASE_URL}/rest/v1/scheme_chunks?select=id&limit=1",
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
        },
        timeout=10
    )
    if test_resp.status_code != 200:
        print(f"[ERROR] Cannot connect to Supabase! Status: {test_resp.status_code}")
        print(f"  Response: {test_resp.text}")
        print()
        print("  Make sure you have:")
        print("  1. Created the 'scheme_chunks' table in Supabase SQL Editor")
        print("  2. Correct SUPABASE_URL and SUPABASE_KEY in .env")
        return
    print("  [OK] Supabase connected!")

    # --- Load local chunks ---
    if not os.path.exists(CHUNKS_PATH):
        print(f"[ERROR] {CHUNKS_PATH} not found!")
        print("  Make sure you have the chunks file in the backend folder.")
        return

    print(f"[1/4] Loading chunks from {CHUNKS_PATH}...")
    with open(CHUNKS_PATH, "rb") as f:
        chunks = pickle.load(f)
    print(f"  Total chunks to upload: {len(chunks)}")

    # --- Load embedding model ---
    print(f"[2/4] Loading embedding model ({EMBEDDING_MODEL_NAME})...")
    model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    print("  Model loaded successfully!")

    # --- Generate embeddings ---
    print("[3/4] Generating embeddings for all chunks...")
    texts = [chunk["text"] for chunk in chunks]
    embeddings = model.encode(texts, show_progress_bar=True, batch_size=64)
    print(f"  Generated {len(embeddings)} embeddings (dimension: {embeddings.shape[1]})")

    # --- Upload to Supabase via REST API ---
    print(f"[4/4] Uploading to Supabase in batches of {BATCH_SIZE}...")

    total_uploaded = 0
    total_errors = 0
    total_batches = (len(chunks) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(chunks), BATCH_SIZE):
        batch_chunks = chunks[i:i + BATCH_SIZE]
        batch_embeddings = embeddings[i:i + BATCH_SIZE]

        rows = []
        for chunk, embedding in zip(batch_chunks, batch_embeddings):
            rows.append({
                "filename": chunk["filename"],
                "chunk_text": chunk["text"],
                "embedding": embedding.tolist()
            })

        try:
            resp = requests.post(
                f"{SUPABASE_URL}/rest/v1/scheme_chunks",
                headers=headers,
                json=rows,
                timeout=30
            )

            batch_num = (i // BATCH_SIZE) + 1

            if resp.status_code in [200, 201]:
                total_uploaded += len(rows)
                print(f"  Batch {batch_num}/{total_batches}: Uploaded {len(rows)} chunks [OK]")
            else:
                total_errors += len(rows)
                print(f"  Batch {batch_num}/{total_batches}: FAILED - {resp.status_code} - {resp.text[:200]}")

        except Exception as e:
            total_errors += len(rows)
            print(f"  Batch error: {e}")

    print()
    print("=" * 60)
    print("  UPLOAD COMPLETE!")
    print("=" * 60)
    print(f"  Total chunks uploaded: {total_uploaded}")
    if total_errors > 0:
        print(f"  Errors: {total_errors}")
    print()
    print("  You can now use Supabase for RAG search!")
    print("  Local files (myscheme_faiss_index.bin, myscheme_chunks.pkl)")
    print("  are no longer needed for running the project.")
    print()
    print("  NEXT STEP: Run this SQL in Supabase SQL Editor")
    print("  to create the search index for better performance:")
    print()
    print("  CREATE INDEX ON scheme_chunks")
    print("  USING ivfflat (embedding vector_cosine_ops)")
    print("  WITH (lists = 100);")
    print("=" * 60)


if __name__ == "__main__":
    main()
