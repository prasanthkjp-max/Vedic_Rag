import os
import sys
import fitz
import time
import pytesseract
from PIL import Image
from io import BytesIO

# Import config dynamically
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import BOOKS_DIR

book_filename = "Brihat Parasara Hora Sastra 1 -- Maharshi Parasara -- ( WeLib.org ).pdf"
pdf_path = os.path.join(BOOKS_DIR, book_filename)

if not os.path.exists(pdf_path):
    print(f"Error: PDF not found at {pdf_path}")
    print(f"Please place {book_filename} in the books directory: {BOOKS_DIR}")
    sys.exit(1)

doc = fitz.open(pdf_path)
page = doc.load_page(50)

for dpi in [300, 150]:
    start_time = time.time()
    zoom = dpi / 72
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    img = Image.open(BytesIO(pix.tobytes("png")))
    
    config = "--oem 3 --psm 3"
    text = pytesseract.image_to_string(img, lang="san+eng", config=config)
    elapsed = time.time() - start_time
    
    print(f"\n=== DPI: {dpi} (Elapsed: {elapsed:.2f}s) ===")
    print("Sample lines:")
    lines = [line for line in text.split("\n") if "SAGITTARIUS" in line or "तुलः" in line or "पृष्ठोदयी" in line]
    for line in lines[:3]:
        print(f"  {line}")
doc.close()
