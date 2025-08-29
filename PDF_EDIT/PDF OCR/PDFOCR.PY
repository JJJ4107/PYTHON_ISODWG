from pdf2image import convert_from_path
from PyPDF2 import PdfWriter, PdfReader
import pytesseract
from PIL import Image, ImageFilter
import tkinter as tk
from tkinter import filedialog
import os
import io

# Fixed Tesseract configuration (LSTM + assume a single uniform block of text)
custom_config = r'--oem 1 --psm 6'

def run_ocr_with_preprocessing():
    root = tk.Tk()
    root.withdraw()

    pdf_path = filedialog.askopenfilename(
        title="Select a PDF file to perform OCR",
        filetypes=[("PDF files", "*.pdf")]
    )
    if not pdf_path:
        print("❌ No PDF file was selected.")
        return

    base, ext = os.path.splitext(pdf_path)
    output_path = base + "_OCR.pdf"

    try:
        print(f"➡️ Converting PDF to images: {pdf_path}")
        images = convert_from_path(
            pdf_path,
            dpi=400,  # 📌 High-resolution conversion
            poppler_path=r"C:\poppler-24.08.0\Library\bin"
        )

        writer = PdfWriter()

        for i, img in enumerate(images, 1):
            print(f"📄 Performing OCR on page {i}/{len(images)}...")

            # 📌 Preprocessing: grayscale + sharpening
            img = img.convert("L").filter(ImageFilter.SHARPEN)

            # Perform OCR
            pdf_bytes = pytesseract.image_to_pdf_or_hocr(
                img, extension='pdf', lang='eng', config=custom_config
            )
            reader = PdfReader(io.BytesIO(pdf_bytes))
            writer.add_page(reader.pages[0])

        with open(output_path, "wb") as f:
            writer.write(f)

        print(f"✅ OCR completed: {output_path}")

    except Exception as e:
        print("❌ Error occurred during OCR processing:", e)

if __name__ == "__main__":
    run_ocr_with_preprocessing()
