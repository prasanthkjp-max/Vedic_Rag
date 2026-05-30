import fitz
import time
import pytesseract
from PIL import Image
from io import BytesIO

pdf_path = "/home/prasanth/.openclaw/workspace/vedic_astrology_books/Brihat Parasara Hora Sastra 1 -- Maharshi Parasara -- ( WeLib.org ).pdf"
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
