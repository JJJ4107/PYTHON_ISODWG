import fitz  # PyMuPDF
import sys
import os
import subprocess

# --------- 명령줄 인자 확인 ----------
if len(sys.argv) != 3:
    print("사용법: PDFFINDER.EXE [찾을텍스트] [PDF파일경로]")
    sys.exit()

TEXT = sys.argv[1]
PDF_PATH = sys.argv[2]

if not os.path.exists(PDF_PATH):
    print(f"❌ PDF 파일을 찾을 수 없습니다: {PDF_PATH}")
    sys.exit()

# PDF 열기 및 하이라이트 적용
doc = fitz.open(PDF_PATH)
found = False

def highlight_text(page, text, color=(1, 1, 0)):
    text_instances = page.search_for(text)
    for inst in text_instances:
        highlight = page.add_highlight_annot(inst)
        highlight.set_colors(stroke=color, fill=color)
        highlight.set_opacity(0.4)
        highlight.update()
    return len(text_instances)

for page_num, page in enumerate(doc, start=1):
    count = highlight_text(page, TEXT)
    if count > 0:
        print(f"✅ {page_num} 페이지에서 '{TEXT}' 발견 및 하이라이트됨 ({count}회)")
        found = True

# 임시 파일로 저장 (자동삭제 목적)
if found:
    import tempfile
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    doc.save(temp_file.name)
    doc.close()

    # 기본 PDF 뷰어로 열기
    print("📄 화면에 표시 중...")
    subprocess.Popen(['start', '', temp_file.name], shell=True)
else:
    print(f"❗ '{TEXT}' 를 PDF에서 찾지 못했습니다.")
    doc.close()
