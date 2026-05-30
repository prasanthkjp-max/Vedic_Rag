import fitz

pdf_path = "/home/prasanth/.openclaw/workspace/vedic_astrology_books/Brihat Parasara Hora Sastra 1 -- Maharshi Parasara -- ( WeLib.org ).pdf"
doc = fitz.open(pdf_path)
page = doc.load_page(14)
embedded_text = page.get_text()

print("=== PRE-EXISTING EMBEDDED TEXT LAYER ON PAGE 14 ===")
print(embedded_text[:1200])
print("====================================================")
