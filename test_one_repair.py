import sqlite3
import struct
import time

from config import get_llm_client, EMBEDDING_MODEL

DB_PATH = "/home/prasanth/Vedic_Rag/vedic_astrology_rag.db"

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
