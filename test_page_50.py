import os
import sys
import fitz
from PIL import Image
import pytesseract
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

# Render at 300 DPI
zoom = 300 / 72
mat = fitz.Matrix(zoom, zoom)
pix = page.get_pixmap(matrix=mat)
img = Image.open(BytesIO(pix.tobytes("png")))

# Run pytesseract OCR
config = "--oem 3 --psm 3"
text = pytesseract.image_to_string(img, lang="san+eng", config=config)

print("=== SANSKRIT+ENGLISH OCR RESULT ON PAGE 50 ===")
print(text[:1200])
print("==============================================")
doc.close()
