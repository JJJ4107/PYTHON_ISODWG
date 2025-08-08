from pdf2image import convert_from_path
from PyPDF2 import PdfWriter, PdfReader
import pytesseract
from PIL import Image, ImageFilter
import tkinter as tk
from tkinter import filedialog
import os
import io

# 고정된 Tesseract 옵션 설정 (LSTM + 단일 컬럼 텍스트 인식)
custom_config = r'--oem 1 --psm 6'

def run_ocr_with_preprocessing():
    root = tk.Tk()
    root.withdraw()

    pdf_path = filedialog.askopenfilename(
        title="OCR 처리할 PDF 파일을 선택하세요",
        filetypes=[("PDF files", "*.pdf")]
    )
    if not pdf_path:
        print("❌ PDF 파일이 선택되지 않았습니다.")
        return

    base, ext = os.path.splitext(pdf_path)
    output_path = base + "_OCR.pdf"

    try:
        print(f"➡️ PDF → 이미지 변환 중: {pdf_path}")
        images = convert_from_path(
            pdf_path,
            dpi=400,  # 📌 고해상도 변환
            poppler_path=r"C:\poppler-24.08.0\Library\bin"
        )

        writer = PdfWriter()

        for i, img in enumerate(images, 1):
            print(f"📄 페이지 {i}/{len(images)} OCR 중...")

            # 📌 전처리: 흑백 변환 + 샤프닝
            img = img.convert("L").filter(ImageFilter.SHARPEN)

            # OCR 수행
            pdf_bytes = pytesseract.image_to_pdf_or_hocr(
                img, extension='pdf', lang='eng', config=custom_config
            )
            reader = PdfReader(io.BytesIO(pdf_bytes))
            writer.add_page(reader.pages[0])

        with open(output_path, "wb") as f:
            writer.write(f)

        print(f"✅ OCR 완료: {output_path}")

    except Exception as e:
        print("❌ OCR 처리 중 오류 발생:", e)

if __name__ == "__main__":
    run_ocr_with_preprocessing()
