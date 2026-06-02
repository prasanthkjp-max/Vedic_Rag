import sqlite3
import struct
import json
import urllib.request
import time
import sys

DB_PATH = "/home/prasanth/Vedic_Rag/vedic_astrology_rag.db"
EMBEDDING_MODEL = "nomic-embed-text"
OLLAMA_URL = "http://localhost:11434/api/embeddings"

def get_ollama_embedding(text):
    """Generate embedding with a long timeout (30s) and retry mechanism"""
    data = {
        "model": EMBEDDING_MODEL,
        "prompt": text
    }
    req = urllib.request.Request(
        OLLAMA_URL, 
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    
    for attempt in range(5):
        try:
            # High 30-second timeout to handle CPU queuing safely
            with urllib.request.urlopen(req, timeout=30) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                embedding = res_data.get("embedding", [])
                if embedding and len(embedding) == 768:
                    return embedding
        except Exception as e:
            time.sleep(1.5) # Wait before retry
            
    return None

def serialize_embedding(vector):
    return struct.pack(f"{len(vector)}f", *vector)

def is_vector_zero(emb_blob):
    if not emb_blob:
        return True
    num_floats = len(emb_blob) // 4
    vector = list(struct.unpack(f"{num_floats}f", emb_blob))
    return all(v == 0.0 for v in vector)

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Fetch all pages
    print("Scanning database for zero-vector placeholders...")
    cursor.execute("SELECT p.id, b.title, p.page_num, p.raw_text, p.embedding FROM pages p JOIN books b ON p.book_id = b.id")
    rows = cursor.fetchall()
    
    zero_pages = []
    for row in rows:
        p_id, book_title, page_num, raw_text, emb_blob = row
        if is_vector_zero(emb_blob):
            zero_pages.append({
                "id": p_id,
                "book_title": book_title,
                "page_num": page_num,
                "text": raw_text
            })
            
    total_zeros = len(zero_pages)
    print(f"Found {total_zeros} pages requiring vector repair.")
    
    if total_zeros == 0:
        print("All pages are already fully vectorized! No repairs needed.")
        conn.close()
        return
        
    print("\nStarting self-healing sequential embedding repair...")
    start_time = time.time()
    repaired_count = 0
    failed_count = 0
    
    for idx, page in enumerate(zero_pages):
        text_to_embed = page["text"].strip() if page["text"].strip() else f"Book page {page['page_num']}"
        
        # Call API sequentially
        vector = get_ollama_embedding(text_to_embed)
        
        if vector:
            blob = serialize_embedding(vector)
            cursor.execute("UPDATE pages SET embedding = ? WHERE id = ?", (blob, page["id"]))
            repaired_count += 1
            
            # Commit on every page for real-time progress on Web UI
            conn.commit()
            elapsed = time.time() - start_time
            avg_speed = elapsed / repaired_count
            est_rem = avg_speed * (total_zeros - idx - 1)
            print(f"[{idx+1}/{total_zeros}] Repaired {repaired_count} pages. Speed: {avg_speed:.2f}s/page. Est remaining: {est_rem/60:.1f} mins.", flush=True)
        else:
            failed_count += 1
            print(f"[{idx+1}/{total_zeros}] FAILED to generate vector for: {page['book_title']}, Page {page['page_num']+1}")
            
    conn.commit()
    conn.close()
    
    total_time = time.time() - start_time
    print(f"\n==================================================")
    print(f"Vector Repair Complete!")
    print(f"Total time elapsed: {total_time/60:.2f} minutes")
    print(f"Successfully repaired and saved: {repaired_count} pages")
    if failed_count > 0:
        print(f"Failed to repair: {failed_count} pages")
    print(f"==================================================")

if __name__ == "__main__":
    main()
