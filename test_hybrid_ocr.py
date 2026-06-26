import os
import sys
import fitz  # PyMuPDF
from PIL import Image
import pytesseract

# Import config dynamically
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from config import BASE_DIR, BOOKS_DIR, get_llm_client, DEFAULT_LLM_MODEL

def render_page_to_image(pdf_path, page_num, dpi=300):
    doc = fitz.open(pdf_path)
    page = doc.load_page(page_num)
    
    # Set high resolution (300 DPI) by applying a scale matrix
    zoom = dpi / 72  # 72 is default PDF DPI
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    
    # Convert to PIL Image
    img_data = pix.tobytes("png")
    from io import BytesIO
    img = Image.open(BytesIO(img_data))
    doc.close()
    return img

def query_llm(prompt, model=DEFAULT_LLM_MODEL):
    try:
        client = get_llm_client()
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content or ""
    except Exception as e:
        return f"Error querying OpenRouter: {e}"

def clean_ocr_text(raw_text):
    prompt = f"""You are an expert Sanskrit and Vedic Astrology scholar.
Your task is to reconstruct, correct, and format raw OCR text extracted from an old scanned book (containing mixed Sanskrit Devanagari text, transliterated Sanskrit, and English translations).
The OCR text has errors due to smudges, page folds, and high contrast.

Please fix spelling, restore the correct Devanagari Sanskrit verses (Shlokas), correct any mixed English characters, and format it beautifully.
Preserve all the original text meaning, names, explanations, and structure. Do not summarize or lose details.

RAW OCR TEXT TO CLEAN:
-----------------------------------------
{raw_text}
-----------------------------------------

Provide only the clean, reconstructed, and beautifully formatted Sanskrit (with proper shloka format) and English text.
Do not write introduction or outro remarks. Start directly with the cleaned text.
"""
    return query_llm(prompt)

if __name__ == "__main__":
    book_filename = "Brihat Parasara Hora Sastra 1 -- Maharshi Parasara -- ( WeLib.org ).pdf"
    pdf_path = os.path.join(BOOKS_DIR, book_filename)
    
    if not os.path.exists(pdf_path):
        print(f"Error: PDF not found at {pdf_path}")
        print(f"Please place {book_filename} in the books directory: {BOOKS_DIR}")
        sys.exit(1)
        
    print("Step 1: Rendering page 14 (15th page) as high-res 300 DPI image...")
    # Page 14 is 15th page
    img = render_page_to_image(pdf_path, 14, dpi=300)
    
    # Save temp image for inspection
    temp_img_path = os.path.join(BASE_DIR, "temp_page_14.png")
    img.save(temp_img_path)
    print(f"Saved temp page image to {temp_img_path}")
    
    print("\nStep 2: Performing pytesseract OCR (languages: san + eng)...")
    config = "--oem 3 --psm 3"
    raw_ocr = pytesseract.image_to_string(img, lang="san+eng", config=config)
    
    print("\n--- RAW OCR TEXT START ---")
    print(raw_ocr[:1000])
    print("--- RAW OCR TEXT END (Truncated if >1000 chars) ---\n")
    
    print("Step 3: Cleaning raw OCR text using AI model...")
    cleaned_ocr = clean_ocr_text(raw_ocr)
    
    print("\n--- AI-CLEANED OCR TEXT START ---")
    print(cleaned_ocr)
    print("--- AI-CLEANED OCR TEXT END ---\n")
    
    # Save both for comparison
    comparison_path = os.path.join(BASE_DIR, "sample_comparison.txt")
    with open(comparison_path, "w", encoding="utf-8") as f:
        f.write("=== RAW OCR ===\n")
        f.write(raw_ocr)
        f.write("\n\n=== AI CLEANED ===\n")
        f.write(cleaned_ocr)
    print(f"Saved comparison to {comparison_path}")
