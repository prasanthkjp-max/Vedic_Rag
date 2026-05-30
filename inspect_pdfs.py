import os
import pypdf

books_dir = "/home/prasanth/.openclaw/workspace/vedic_astrology_books"

print(f"Scanning directory: {books_dir}")
if not os.path.exists(books_dir):
    print("Directory does not exist!")
    exit(1)

total_pages = 0
books = [f for f in os.listdir(books_dir) if f.endswith(".pdf")]
books.sort()

for book in books:
    path = os.path.join(books_dir, book)
    try:
        reader = pypdf.PdfReader(path)
        pages = len(reader.pages)
        total_pages += pages
        print(f"- {book}: {pages} pages, size: {os.path.getsize(path) / (1024*1024):.2f} MB")
    except Exception as e:
        print(f"- {book}: Error reading file: {e}")

print(f"\nTotal pages across all books: {total_pages}")
