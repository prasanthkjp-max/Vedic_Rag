import sqlite3
import struct

DB_PATH = "/home/prasanth/Vedic_Rag/vedic_astrology_rag.db"

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("SELECT id, book_id, page_num, embedding FROM pages")
rows = cursor.fetchall()

total = len(rows)
zero_count = 0
active_count = 0

for row in rows:
    p_id, book_id, page_num, emb_blob = row
    if emb_blob:
        num_floats = len(emb_blob) // 4
        vector = list(struct.unpack(f"{num_floats}f", emb_blob))
        
        # Check if vector is all zeros
        is_zero = all(v == 0.0 for v in vector)
        if is_zero:
            zero_count += 1
        else:
            active_count += 1
    else:
        zero_count += 1

print(f"Total Pages in Database: {total}")
print(f"Successfully Vectorized Pages: {active_count} ({active_count/total*100:.1f}%)")
print(f"Pages with Placeholder Zero Vectors: {zero_count} ({zero_count/total*100:.1f}%)")

conn.close()
