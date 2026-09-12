import os
import pickle
import faiss
import numpy as np
import PyPDF2
from sentence_transformers import SentenceTransformer
import warnings
import fitz  # PyMuPDF

warnings.filterwarnings("ignore")

# Use relative path so it works on any computer
DATASET_PATH = os.path.join("..", "text_data")
INDEX_PATH = "myscheme_faiss_index.bin"
CHUNKS_PATH = "myscheme_chunks.pkl"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

def extract_text(file_path):
    text = ""
    try:
        if file_path.lower().endswith('.pdf'):
            try:
                # Try PyMuPDF first
                doc = fitz.open(file_path)
                for page in doc:
                    text += page.get_text() + "\n"
            except Exception:
                # Fallback to PyPDF2
                reader = PyPDF2.PdfReader(file_path)
                for page in reader.pages:
                    res = page.extract_text()
                    if res:
                        text += res + "\n"
        elif file_path.lower().endswith('.txt'):
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                text = f.read()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
    return text.strip()

def chunk_text(text, chunk_size=800, overlap=100):
        words = text.split()
        chunks = []
        if len(words) == 0:
            return chunks
        for i in range(0, len(words), chunk_size - overlap):
            chunk = " ".join(words[i:i + chunk_size])
            if len(chunk.strip()) > 50:
                chunks.append(chunk)
        return chunks

def build_index():
    print("Loading embedding model (this may take a moment)...")
    model = SentenceTransformer(EMBEDDING_MODEL)

    all_chunks = []
    
    files = []
    if os.path.exists(DATASET_PATH):
        files = [f for f in os.listdir(DATASET_PATH) if f.lower().endswith(('.pdf', '.txt'))]
        print(f"Found {len(files)} files in dataset directory.")
    else:
        print(f"Directory {DATASET_PATH} not found.")
        return

    # Process files
    for idx, filename in enumerate(files):
        print(f"Processing ({idx+1}/{len(files)}): {filename}")
        file_path = os.path.join(DATASET_PATH, filename)
        text = extract_text(file_path)
        if text:
            # Chunking
            chunks = chunk_text(text, chunk_size=500, overlap=100)
            for chunk in chunks:
                all_chunks.append({
                    "filename": filename,
                    "text": chunk
                })

    if not all_chunks:
        print("No valid text extracted from the dataset.")
        return

    print(f"Total extracted chunks: {len(all_chunks)}. Computing embeddings...")
    texts_to_embed = [item["text"] for item in all_chunks]
    
    embeddings = model.encode(texts_to_embed, show_progress_bar=True)
    embeddings = np.array(embeddings).astype("float32")

    print("Building FAISS index...")
    d = embeddings.shape[1]
    index = faiss.IndexFlatL2(d)
    index.add(embeddings)

    faiss.write_index(index, INDEX_PATH)
    with open(CHUNKS_PATH, 'wb') as f:
        pickle.dump(all_chunks, f)

    print(f"Success! FAISS Index saved to {INDEX_PATH}")
    print(f"Chunks saved to {CHUNKS_PATH}")

if __name__ == "__main__":
    build_index()
