import os
import fitz

books_dir = "/home/prasanth/.openclaw/workspace/vedic_astrology_books"
books = [f for f in os.listdir(books_dir) if f.endswith(".pdf")]
books.sort()

print("Checking books for embedded text...")
for book in books:
    path = os.path.join(books_dir, book)
    try:
        doc = fitz.open(path)
        # Check first 5 pages and middle 5 pages
        num_pages = len(doc)
        sample_pages = list(range(min(5, num_pages))) + list(range(max(0, num_pages//2 - 2), min(num_pages, num_pages//2 + 3)))
        sample_pages = sorted(list(set(sample_pages)))
        
        extracted_chars = 0
        for p_num in sample_pages:
            page = doc.load_page(p_num)
            text = page.get_text()
            extracted_chars += len(text.strip())
            
        avg_chars = extracted_chars / len(sample_pages) if sample_pages else 0
        is_scanned = avg_chars < 50
        print(f"- {book}: Avg embedded chars per sample page: {avg_chars:.1f} ({'SCANNED' if is_scanned else 'HAS EMBEDDED TEXT'})")
    except Exception as e:
        print(f"- {book}: Error: {e}")
