import fitz
from PIL import Image
import pytesseract
from io import BytesIO

pdf_path = "/home/prasanth/.openclaw/workspace/vedic_astrology_books/Brihat Parasara Hora Sastra 1 -- Maharshi Parasara -- ( WeLib.org ).pdf"
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
