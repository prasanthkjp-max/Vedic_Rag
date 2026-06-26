import sqlite3
import struct
import time
import os
import sys

# Import config dynamically
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import DB_RAG_PATH, get_llm_client, EMBEDDING_MODEL, EMBEDDING_DIM
DB_PATH = DB_RAG_PATH

def needs_repair(emb_blob):
    """Determine if a page's embedding is missing, corrupt, legacy/wrong dimension, or all zeros."""
    if not emb_blob:
        return True
    
    num_floats = len(emb_blob) // 4
    if num_floats != EMBEDDING_DIM:
        return True
        
    try:
        vector = list(struct.unpack(f"{num_floats}f", emb_blob[:num_floats * 4]))
        if all(v == 0.0 for v in vector):
            return True
    except Exception:
        return True
        
    return False

def main():
    if not os.path.exists(DB_PATH):
        print(f"Error: Database file does not exist at {DB_PATH}")
        sys.exit(1)
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Check if table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pages'")
    if not cursor.fetchone():
        print(f"Error: Table 'pages' does not exist in database {DB_PATH}")
        print("Please run ingest.py first to initialize the database.")
        conn.close()
        sys.exit(1)
        
    # Get one zero/legacy vector page
    cursor.execute("SELECT id, raw_text, embedding FROM pages")
    rows = cursor.fetchall()
    
    repair_page = None
    for row in rows:
        p_id, raw_text, emb_blob = row
        if needs_repair(emb_blob):
            repair_page = {"id": p_id, "text": raw_text}
            break
            
    if not repair_page:
        print("No pages requiring repair/re-embedding found!")
        conn.close()
        return
        
    print(f"Testing page ID: {repair_page['id']}")
    print(f"Raw text snippet (first 100 chars): {repr(repair_page['text'][:100])}")
    
    prompt = repair_page['text'].strip() if repair_page['text'].strip() else "test page"

    print("Sending request to OpenRouter...")
    start_time = time.time()
    try:
        client = get_llm_client()
        resp = client.with_options(timeout=30).embeddings.create(
            model=EMBEDDING_MODEL, input=prompt
        )
        vector = resp.data[0].embedding if resp.data else []
        print(f"SUCCESS! Received vector of length: {len(vector)}")
        print(f"First 5 elements: {vector[:5]}")
    except Exception as e:
        print(f"FAILED: {e}")
    print(f"Time taken: {time.time() - start_time:.2f} seconds")
    
    conn.close()

if __name__ == "__main__":
    main()
