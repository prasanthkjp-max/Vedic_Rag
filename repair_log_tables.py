import sqlite3
import struct
import os
import sys

# Import config dynamically
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import DB_RAG_PATH, get_llm_client, EMBEDDING_MODEL
DB_PATH = DB_RAG_PATH

def get_embedding(text):
    try:
        client = get_llm_client()
        resp = client.with_options(timeout=15).embeddings.create(
            model=EMBEDDING_MODEL, input=text
        )
        return resp.data[0].embedding if resp.data else []
    except Exception as e:
        print(f"Error: {e}")
        return None

def serialize_embedding(vector):
    return struct.pack(f"{len(vector)}f", *vector)

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
        
    # Page 34 (0-indexed page_num = 33)
    p34_text = "Brihat Parasara Hora Sastra (Girish) Page 34: Table of Proportional Diurnal Logarithms (Dasa Systems Table of Hours and Degrees)"
    # Page 35 (0-indexed page_num = 34)
    p35_text = "Brihat Parasara Hora Sastra (Girish) Page 35: Logarithmic Table of Proportional Diurnal Logarithms (Dasa Systems Table of Hours and Degrees - Continued)"
    
    print("Generating embedding for Girish Page 34 Logarithm Table...")
    v34 = get_embedding(p34_text)
    if v34:
        blob = serialize_embedding(v34)
        cursor.execute("UPDATE pages SET embedding = ? WHERE book_id = 2 AND page_num = 33", (blob,))
        print("Updated Page 34 embedding successfully!")
        
    print("Generating embedding for Girish Page 35 Logarithm Table...")
    v35 = get_embedding(p35_text)
    if v35:
        blob = serialize_embedding(v35)
        cursor.execute("UPDATE pages SET embedding = ? WHERE book_id = 2 AND page_num = 34", (blob,))
        print("Updated Page 35 embedding successfully!")
        
    conn.commit()
    
    # Verify remaining unvectorized pages
    cursor.execute("SELECT count(*) FROM pages WHERE embedding = zeroblob(3072)")
    zeros = cursor.fetchone()[0]
    
    print(f"\nVerification: Remaining unvectorized pages in database: {zeros}")
    conn.close()

if __name__ == "__main__":
    main()
