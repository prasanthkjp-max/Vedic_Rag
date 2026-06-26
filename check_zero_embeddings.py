import sqlite3
import struct
import os
import sys

# Import config so we dynamically resolve DB path and target dimension.
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import DB_RAG_PATH, EMBEDDING_DIM
DB_PATH = DB_RAG_PATH

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

cursor.execute("SELECT id, book_id, page_num, embedding FROM pages")
rows = cursor.fetchall()

total = len(rows)
zero_count = 0
active_count = 0
mismatched_count = 0
mismatched_dims = set()

for row in rows:
    p_id, book_id, page_num, emb_blob = row
    if emb_blob:
        num_floats = len(emb_blob) // 4
        vector = list(struct.unpack(f"{num_floats}f", emb_blob))
        
        # Check if vector is all zeros
        is_zero = all(v == 0.0 for v in vector)
        if is_zero:
            zero_count += 1
        elif len(vector) != EMBEDDING_DIM:
            mismatched_count += 1
            mismatched_dims.add(len(vector))
        else:
            active_count += 1
    else:
        zero_count += 1

print(f"Database Path: {DB_PATH}")
print(f"Target Embedding Dimension: {EMBEDDING_DIM}")
print(f"Total Pages in Database: {total}")
if total > 0:
    print(f"Successfully Vectorized Pages: {active_count} ({active_count/total*100:.1f}%)")
    if mismatched_count > 0:
        print(f"Pages with Legacy Mismatched Dimensions {list(mismatched_dims)}: {mismatched_count} ({mismatched_count/total*100:.1f}%)")
    print(f"Pages with Placeholder/Zero/Null Vectors: {zero_count} ({zero_count/total*100:.1f}%)")
else:
    print("No pages found in the database. Run ingest.py first.")

conn.close()
