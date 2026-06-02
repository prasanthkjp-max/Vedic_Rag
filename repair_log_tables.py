import sqlite3
import struct
import json
import urllib.request

DB_PATH = "/home/prasanth/Vedic_Rag/vedic_astrology_rag.db"
EMBEDDING_MODEL = "nomic-embed-text"
OLLAMA_URL = "http://localhost:11434/api/embeddings"

def get_ollama_embedding(text):
    data = {
        "model": EMBEDDING_MODEL,
        "prompt": text
    }
    req = urllib.request.Request(
        OLLAMA_URL, 
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            return res_data.get("embedding", [])
    except Exception as e:
        print(f"Error: {e}")
        return None

def serialize_embedding(vector):
    return struct.pack(f"{len(vector)}f", *vector)

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Page 34 (0-indexed page_num = 33)
    p34_text = "Brihat Parasara Hora Sastra (Girish) Page 34: Table of Proportional Diurnal Logarithms (Dasa Systems Table of Hours and Degrees)"
    # Page 35 (0-indexed page_num = 34)
    p35_text = "Brihat Parasara Hora Sastra (Girish) Page 35: Logarithmic Table of Proportional Diurnal Logarithms (Dasa Systems Table of Hours and Degrees - Continued)"
    
    print("Generating embedding for Girish Page 34 Logarithm Table...")
    v34 = get_ollama_embedding(p34_text)
    if v34:
        blob = serialize_embedding(v34)
        cursor.execute("UPDATE pages SET embedding = ? WHERE book_id = 2 AND page_num = 33", (blob,))
        print("Updated Page 34 embedding successfully!")
        
    print("Generating embedding for Girish Page 35 Logarithm Table...")
    v35 = get_ollama_embedding(p35_text)
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
