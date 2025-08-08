import os
from tkinter import Tk, filedialog, simpledialog, messagebox
from PyPDF2 import PdfReader, PdfWriter, PdfMerger

def unlock_pdf_to_memory(path, password):
    try:
        reader = PdfReader(path)
        if reader.is_encrypted:
            reader.decrypt(password)
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        from io import BytesIO
        mem_file = BytesIO()
        writer.write(mem_file)
        mem_file.seek(0)
        return mem_file
    except Exception as e:
        print(f"❌ {os.path.basename(path)} 오류: {e}")
        return None

def main():
    root = Tk()
    root.withdraw()

    # 1. 폴더 선택
    folder = filedialog.askdirectory(title="📂 PDF가 있는 폴더를 선택하세요")
    if not folder:
        print("❗ 폴더 선택이 취소되었습니다.")
        return

    # 2. 암호 입력
    password = simpledialog.askstring("🔐 비밀번호 입력", "PDF 파일의 암호를 입력하세요:", show="*")
    if not password:
        print("❗ 암호 입력이 취소되었습니다.")
        return

    # 3. PDF 파일 목록
    pdf_files = [f for f in os.listdir(folder) if f.lower().endswith(".pdf")]
    if not pdf_files:
        messagebox.showinfo("❗ 없음", "선택한 폴더에 PDF 파일이 없습니다.")
        return

    # 4. 병합 준비
    merger = PdfMerger()
    count = 0
    for pdf in pdf_files:
        full_path = os.path.join(folder, pdf)
        mem_file = unlock_pdf_to_memory(full_path, password)
        if mem_file:
            merger.append(mem_file)
            count += 1

    if count == 0:
        messagebox.showerror("실패", "암호 해제에 성공한 PDF가 없습니다.")
        return

    # 5. 최종 파일명 입력
    output_name = simpledialog.askstring("📄 저장할 이름", "최종 병합된 PDF 파일명을 입력하세요 (확장자 제외):")
    if not output_name:
        messagebox.showinfo("취소", "파일 저장이 취소되었습니다.")
        return

    output_path = os.path.join(folder, f"{output_name}.pdf")
    merger.write(output_path)
    merger.close()

    messagebox.showinfo("✅ 완료", f"{count}개의 PDF를 병합하여 저장했습니다:\n\n{output_path}")

if __name__ == "__main__":
    main()
