import os
import sys
import fitz

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
page = doc.load_page(14)
embedded_text = page.get_text()

print("=== PRE-EXISTING EMBEDDED TEXT LAYER ON PAGE 14 ===")
print(embedded_text[:1200])
print("====================================================")
doc.close()
