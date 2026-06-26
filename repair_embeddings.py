import sqlite3
import struct
import time
import sys
import os

# Resolve path and import config dynamically
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import DB_RAG_PATH, get_llm_client, EMBEDDING_MODEL, EMBEDDING_DIM
DB_PATH = DB_RAG_PATH

def get_embeddings_batch(texts):
    """Generate embeddings for a list of texts in a single batch call with retries."""
    for attempt in range(5):
        try:
            client = get_llm_client()
            resp = client.with_options(timeout=60).embeddings.create(
                model=EMBEDDING_MODEL, input=texts
            )
            # OpenRouter/OpenAI may not guarantee ordering; sort by index to align with inputs
            data = sorted(resp.data, key=lambda d: d.index)
            vectors = [d.embedding for d in data]
            if len(vectors) == len(texts) and all(len(v) == EMBEDDING_DIM for v in vectors):
                return vectors
            else:
                print(f"Warning: Batch returned incorrect number of vectors or dimensions.")
        except Exception as e:
            print(f"Attempt {attempt+1} failed to generate batch embeddings: {e}")
            time.sleep(1.5)  # Wait before retry

    return None

def serialize_embedding(vector):
    return struct.pack(f"{len(vector)}f", *vector)

def needs_repair(emb_blob):
    """Determine if a page's embedding is missing, corrupt, legacy/wrong dimension, or all zeros."""
    if not emb_blob:
        return True, "missing"
    
    num_floats = len(emb_blob) // 4
    if num_floats != EMBEDDING_DIM:
        return True, f"legacy dimension ({num_floats} vs {EMBEDDING_DIM})"
        
    try:
        vector = list(struct.unpack(f"{num_floats}f", emb_blob[:num_floats * 4]))
        if all(v == 0.0 for v in vector):
            return True, "placeholder zero vector"
    except Exception:
        return True, "corrupt blob"
        
    return False, ""

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
        
    # Fetch all pages
    print("Scanning database for pages requiring vector repair/re-embedding...")
    cursor.execute("SELECT p.id, b.title, p.page_num, p.raw_text, p.embedding FROM pages p JOIN books b ON p.book_id = b.id")
    rows = cursor.fetchall()
    
    repair_pages = []
    reason_counts = {}
    
    for row in rows:
        p_id, book_title, page_num, raw_text, emb_blob = row
        repair_needed, reason = needs_repair(emb_blob)
        if repair_needed:
            repair_pages.append({
                "id": p_id,
                "book_title": book_title,
                "page_num": page_num,
                "text": raw_text,
                "reason": reason
            })
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
            
    total_to_repair = len(repair_pages)
    print(f"Found {total_to_repair} pages requiring vector repair.")
    for reason, count in reason_counts.items():
        print(f" - {reason}: {count} pages")
        
    if total_to_repair == 0:
        print("All pages are already fully and correctly vectorized! No repairs needed.")
        conn.close()
        return
        
    BATCH_SIZE = 32
    print(f"\nStarting self-healing batched embedding repair (batch size: {BATCH_SIZE})...")
    start_time = time.time()
    repaired_count = 0
    failed_count = 0
    
    for i in range(0, total_to_repair, BATCH_SIZE):
        batch = repair_pages[i : i + BATCH_SIZE]
        texts = [p["text"].strip() if p["text"].strip() else f"Book page {p['page_num']}" for p in batch]
        
        print(f"[{i+1}-{min(i+BATCH_SIZE, total_to_repair)}/{total_to_repair}] Requesting embeddings batch...", end="", flush=True)
        vectors = get_embeddings_batch(texts)
        
        if vectors and len(vectors) == len(batch):
            for page, vector in zip(batch, vectors):
                blob = serialize_embedding(vector)
                cursor.execute("UPDATE pages SET embedding = ? WHERE id = ?", (blob, page["id"]))
                repaired_count += 1
            conn.commit()
            elapsed = time.time() - start_time
            avg_speed = elapsed / repaired_count
            est_rem = avg_speed * (total_to_repair - repaired_count)
            print(f" SUCCESS. Avg Speed: {avg_speed:.3f}s/page. Est remaining: {est_rem/60:.1f} mins.", flush=True)
        else:
            failed_count += len(batch)
            print(f" FAILED batch of {len(batch)} pages starting from ID {batch[0]['id']}")
            
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
