import sqlite3
import struct
import json
import urllib.request
import time

DB_PATH = "/home/prasanth/vedic_rag/vedic_astrology_rag.db"
EMBEDDING_MODEL = "nomic-embed-text"
OLLAMA_URL = "http://localhost:11434/api/embeddings"

def is_vector_zero(emb_blob):
    if not emb_blob:
        return True
    num_floats = len(emb_blob) // 4
    vector = list(struct.unpack(f"{num_floats}f", emb_blob))
    return all(v == 0.0 for v in vector)

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get one zero vector page
    cursor.execute("SELECT id, raw_text, embedding FROM pages")
    rows = cursor.fetchall()
    
    zero_page = None
    for row in rows:
        p_id, raw_text, emb_blob = row
        if is_vector_zero(emb_blob):
            zero_page = {"id": p_id, "text": raw_text}
            break
            
    if not zero_page:
        print("No zero vector pages found!")
        conn.close()
        return
        
    print(f"Testing page ID: {zero_page['id']}")
    print(f"Raw text snippet (first 100 chars): {repr(zero_page['text'][:100])}")
    
    prompt = zero_page['text'].strip() if zero_page['text'].strip() else "test page"
    data = {
        "model": EMBEDDING_MODEL,
        "prompt": prompt
    }
    
    req = urllib.request.Request(
        OLLAMA_URL, 
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    
    print("Sending request to Ollama...")
    start_time = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            vector = res_data.get("embedding", [])
            print(f"SUCCESS! Received vector of length: {len(vector)}")
            print(f"First 5 elements: {vector[:5]}")
    except Exception as e:
        print(f"FAILED: {e}")
    print(f"Time taken: {time.time() - start_time:.2f} seconds")
    
    conn.close()

if __name__ == "__main__":
    main()
