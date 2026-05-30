import os
import sys
import json
import fitz  # PyMuPDF
from PIL import Image
import pytesseract
import urllib.request

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
    return img

def query_ollama(prompt, model="gemma4:31b-cloud"):
    url = "http://localhost:11434/api/generate"
    data = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }
    req = urllib.request.Request(
        url, 
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            return res_data.get("response", "")
    except Exception as e:
        return f"Error querying Ollama: {e}"

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
    return query_ollama(prompt)

if __name__ == "__main__":
    pdf_path = "/home/prasanth/.openclaw/workspace/vedic_astrology_books/Brihat Parasara Hora Sastra 1 -- Maharshi Parasara -- ( WeLib.org ).pdf"
    
    if not os.path.exists(pdf_path):
        print(f"Error: PDF not found at {pdf_path}")
        sys.exit(1)
        
    print("Step 1: Rendering page 14 (15th page) as high-res 300 DPI image...")
    # Page 14 is 15th page
    img = render_page_to_image(pdf_path, 14, dpi=300)
    
    # Save temp image for inspection
    temp_img_path = "/home/prasanth/vedic_rag/temp_page_14.png"
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
    with open("/home/prasanth/vedic_rag/sample_comparison.txt", "w", encoding="utf-8") as f:
        f.write("=== RAW OCR ===\n")
        f.write(raw_ocr)
        f.write("\n\n=== AI CLEANED ===\n")
        f.write(cleaned_ocr)
    print("Saved comparison to /home/prasanth/vedic_rag/sample_comparison.txt")
