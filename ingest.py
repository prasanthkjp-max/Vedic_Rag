import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OMP_THREAD_LIMIT"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
import sys
import sqlite3
import json
import struct
import fitz  # PyMuPDF
from PIL import Image
import pytesseract
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import logging
from io import BytesIO

from config import (
    BOOKS_DIR,
    DB_PATH,
    EMBEDDING_MODEL,
    EMBEDDING_DIM,
    EMBED_TIMEOUT,
    OLLAMA_API_KEY,
    OLLAMA_EMBED_URL as OLLAMA_URL,
    connect_db,
    ensure_fts,
)

logger = logging.getLogger("vedic.ingest")

NUM_THREADS = 4  # Matches the 4 CPU cores

def init_db():
    conn = connect_db(DB_PATH)
    cursor = conn.cursor()
    
    # Create books table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS books (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        filename TEXT UNIQUE,
        title TEXT,
        total_pages INTEGER
    )
    """)
    
    # Create pages table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS pages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        book_id INTEGER,
        page_num INTEGER,
        raw_text TEXT,
        embedding BLOB,
        FOREIGN KEY (book_id) REFERENCES books (id),
        UNIQUE(book_id, page_num)
    )
    """)

    conn.commit()
    # Build the FTS5 full-text index + sync triggers now that `pages` exists,
    # so freshly ingested rows are searchable immediately.
    ensure_fts(conn)
    conn.close()

def get_ollama_embedding(text):
    """
    Get 768-dim vector embedding from local Ollama nomic-embed-text
    """
    data = {
        "model": EMBEDDING_MODEL,
        "prompt": text
    }
    headers = {"Content-Type": "application/json"}
    if OLLAMA_API_KEY:
        headers["Authorization"] = f"Bearer {OLLAMA_API_KEY}"
    req = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(data).encode("utf-8"),
        headers=headers
    )

    # Retry logic
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=EMBED_TIMEOUT) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                embedding = res_data.get("embedding", [])
                # A wrong-dimension vector would be stored, then silently
                # dropped by the search index forever — treat it as a failure.
                if embedding and len(embedding) == EMBEDDING_DIM:
                    return embedding
                logger.warning("Embedding has wrong dimension (%d != %d)", len(embedding), EMBEDDING_DIM)
        except Exception as e:
            if attempt == 2:
                logger.warning("Error calling Ollama embedding API: %s", e)
        if attempt < 2:
            time.sleep(1)

    # Signal failure so the page is left unindexed and retried next run, rather
    # than persisting a useless zero vector that the resume check would skip
    # forever.
    return None

def serialize_embedding(vector):
    """Convert a list of floats to a binary BLOB"""
    return struct.pack(f"{len(vector)}f", *vector)

def process_page(book_id, pdf_path, page_num):
    """
    Worker function to render, OCR, and embed a single page
    """
    conn = None
    doc = None
    try:
        # Connect to DB locally in thread to avoid threading issues
        conn = connect_db(DB_PATH)
        cursor = conn.cursor()

        # Check if page is already indexed (Resume Support)
        cursor.execute("SELECT id FROM pages WHERE book_id = ? AND page_num = ?", (book_id, page_num))
        if cursor.fetchone() is not None:
            return page_num, "SKIPPED", 0

        # 1. Render page to high-res image
        doc = fitz.open(pdf_path)
        page = doc.load_page(page_num)
        zoom = 200 / 72  # 200 DPI (Balanced speed and Sanskrit accuracy)
        mat = fitz.Matrix(zoom, zoom)
        pix = page.get_pixmap(matrix=mat)
        img = Image.open(BytesIO(pix.tobytes("png")))

        # 2. Run Tesseract OCR (Sanskrit + English)
        config = "--oem 3 --psm 3"
        raw_text = pytesseract.image_to_string(img, lang="san+eng", config=config)

        if not raw_text.strip():
            # If OCR returned empty, fall back to the embedded text layer
            raw_text = page.get_text()

        # 3. Generate Vector Embedding
        # If the page is empty, embed a simple placeholder to prevent errors
        embed_prompt = raw_text.strip() if raw_text.strip() else f"Book page {page_num}"
        embedding = get_ollama_embedding(embed_prompt)

        # If embedding failed, leave the page unindexed so it is retried on the
        # next run instead of being permanently stored as a zero vector.
        if embedding is None:
            return page_num, "ERROR: embedding failed (will retry next run)", 0

        # 4. Save to Database
        blob = serialize_embedding(embedding)
        cursor.execute("""
        INSERT INTO pages (book_id, page_num, raw_text, embedding)
        VALUES (?, ?, ?, ?)
        """, (book_id, page_num, raw_text, blob))

        conn.commit()

        return page_num, "OK", len(raw_text)
    except Exception as e:
        return page_num, f"ERROR: {e}", 0
    finally:
        # Always release the WAL connection and PDF handle, even on error paths
        # — leaked connections from worker threads can keep the DB busy.
        if doc is not None:
            doc.close()
        if conn is not None:
            conn.close()

def ingest_book(book_filename):
    print(f"\n==================================================")
    print(f"Ingesting Book: {book_filename}")
    print(f"==================================================")
    
    pdf_path = os.path.join(BOOKS_DIR, book_filename)
    if not os.path.exists(pdf_path):
        logger.error("File not found: %s", pdf_path)
        return
        
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    doc.close()
    
    # 1. Register book in DB
    conn = connect_db(DB_PATH)
    cursor = conn.cursor()
    # Simple rule to format book title
    title = book_filename.replace(".pdf", "").replace("-- ( WeLib.org )", "").replace("pdfcoffee.com_", "").replace("-pdf-free", "").replace("_", " ").strip()
    
    try:
        cursor.execute("INSERT INTO books (filename, title, total_pages) VALUES (?, ?, ?)", 
                       (book_filename, title, total_pages))
        conn.commit()
        book_id = cursor.lastrowid
        print(f"Registered new book in DB with ID: {book_id}")
    except sqlite3.IntegrityError:
        cursor.execute("SELECT id FROM books WHERE filename = ?", (book_filename,))
        book_id = cursor.fetchone()[0]
        print(f"Book already registered in DB (ID: {book_id})")
        
    conn.close()
    
    # 2. Get pages already processed
    conn = connect_db(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT page_num FROM pages WHERE book_id = ?", (book_id,))
    processed_pages = set([row[0] for row in cursor.fetchall()])
    conn.close()
    
    pages_to_process = [p for p in range(total_pages) if p not in processed_pages]
    print(f"Total pages: {total_pages} | Already indexed: {len(processed_pages)} | To process: {len(pages_to_process)}")
    
    if not pages_to_process:
        print("All pages of this book are already indexed. Skipping.")
        return
        
    # 3. Parallel process pages
    start_time = time.time()
    completed = 0
    total_to_process = len(pages_to_process)
    
    # Run thread pool
    with ThreadPoolExecutor(max_workers=NUM_THREADS) as executor:
        futures = {executor.submit(process_page, book_id, pdf_path, p): p for p in pages_to_process}
        
        for future in as_completed(futures):
            p_num = futures[future]
            try:
                page_num, status, char_count = future.result()
                completed += 1
                if status == "OK":
                    print(f"[{completed}/{total_to_process}] Page {page_num+1}/{total_pages} - SUCCESS ({char_count} chars)")
                elif status == "SKIPPED":
                    print(f"[{completed}/{total_to_process}] Page {page_num+1}/{total_pages} - SKIPPED")
                else:
                    print(f"[{completed}/{total_to_process}] Page {page_num+1}/{total_pages} - FAILED: {status}")
            except Exception as exc:
                logger.warning("Page %d generated an exception: %s", p_num + 1, exc)
                
    elapsed = time.time() - start_time
    print(f"Finished Book Ingestion in {elapsed:.2f} seconds.")

def main():
    if not os.path.exists(BOOKS_DIR):
        logger.error("Books directory not found: %s", BOOKS_DIR)
        sys.exit(1)
        
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:  # DB_PATH may be a bare filename (cwd)
        os.makedirs(db_dir, exist_ok=True)
    init_db()
    
    books = [f for f in os.listdir(BOOKS_DIR) if f.endswith(".pdf")]
    books.sort()
    
    print(f"Found {len(books)} books in {BOOKS_DIR}")
    for book in books:
        ingest_book(book)
        
    print("\nAll books indexed successfully in SQLite DB!")

if __name__ == "__main__":
    main()
