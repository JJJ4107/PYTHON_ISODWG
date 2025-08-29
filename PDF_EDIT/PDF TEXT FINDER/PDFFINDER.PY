import tkinter as tk
from tkinter import filedialog
import fitz
import os
import math
import subprocess
import sys
import uuid

os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] =  r"C:\PyQtPlatformFix\platforms"

# --------- 거리 계산 ---------
def distance(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

def highlight(page, rects, color=(0, 0, 1), opacity=0.4):
    if not isinstance(rects, list):
        rects = [rects]
    for rect in rects:
        annot = page.add_rect_annot(rect)
        annot.set_colors(stroke=color, fill=color)
        annot.set_opacity(opacity)
        annot.update()

def remove_all_highlights(doc):
    for page in doc:
        annot = page.first_annot
        while annot:
            next_annot = annot.next
            page.delete_annot(annot)
            annot = next_annot

def open_pdf():
    global pdf_path, doc
    path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
    if not path:
        return
    try:
        if doc:
            doc.close()
    except:
        pass
    pdf_path = path
    try:
        doc = fitz.open(pdf_path)
        file_name_var.set(os.path.basename(pdf_path)[:30])
        label_info.config(text=f"✅ 열림: {os.path.basename(pdf_path)}")
    except Exception as e:
        label_info.config(text=f"❌ 열기 실패: {e}")
        doc = None

# --------- 미리보기 프로세스 관리 ---------
preview_proc = None
last_temp_pdf = None

def show_page_preview_with_zoom(doc, page_num):
    global preview_proc, last_temp_pdf
    # 이전 미리보기 프로세스 종료
    if preview_proc is not None:
        try:
            preview_proc.terminate()
        except Exception:
            pass
        preview_proc = None
    # 이전 임시파일 삭제
    if last_temp_pdf is not None:
        try:
            if os.path.exists(last_temp_pdf):
                os.remove(last_temp_pdf)
        except Exception:
            pass
        last_temp_pdf = None
    # 새로운 임시파일명 생성
    temp_pdf = os.path.join(
        os.path.dirname(pdf_path),
        f"_temp_highlight_{uuid.uuid4().hex}.pdf"
    )
    doc.save(temp_pdf)
    preview_proc = subprocess.Popen([
        sys.executable,
        "preview_viewer.py",
        temp_pdf,
        str(page_num)
    ])
    last_temp_pdf = temp_pdf

def run_line_finder():
    if not doc:
        label_info.config(text="❌ PDF 파일이 없습니다.")
        return
    keyword = entry_line.get().strip().upper()
    if not keyword:
        label_info.config(text="❗ 검색어가 없습니다.")
        return
    remove_all_highlights(doc)
    for page_num, page in enumerate(doc):
        words = page.get_text("words")
        all_text, all_pos, all_rects, all_heights = [], [], [], []
        for w in words:
            txt = w[4].strip()
            if not txt:
                continue
            height = abs(w[3] - w[1])
            all_text.append(txt)
            all_pos.append(((w[0]+w[2])/2, (w[1]+w[3])/2))
            all_rects.append(fitz.Rect(w[:4]))
            all_heights.append(height)
        for i, p1 in enumerate(all_text):
            if len(p1) != 7 or not keyword.startswith(p1):
                continue
            p1_pos = all_pos[i]
            h = all_heights[i]
            radius_lp2 = h * 3
            LP2 = LP3 = None
            lp2_idx = lp3_idx = -1
            for j, t2 in enumerate(all_text):
                if len(t2) == 5 and t2.upper().startswith("BR") and distance(p1_pos, all_pos[j]) <= radius_lp2:
                    if not keyword.startswith(f"{p1}-{t2}"):
                        continue
                    LP2 = t2
                    lp2_idx = j
                    break
            if LP2:
                lp2_pos = all_pos[lp2_idx]
                radius_lp3 = h * 3
                for k, t3 in enumerate(all_text):
                    if "DN" in t3.upper() and distance(lp2_pos, all_pos[k]) <= radius_lp3:
                        if f"{p1}-{LP2}-{t3}" == keyword:
                            LP3 = t3
                            lp3_idx = k
                            break
                targets = [all_rects[i], all_rects[lp2_idx]]
                if LP3 and lp3_idx != -1:
                    targets.append(all_rects[lp3_idx])
                highlight(page, targets)
                label_info.config(text=f"📄 LINE 찾음: Page {page_num + 1}")
                show_page_preview_with_zoom(doc, page_num)
                return
    label_info.config(text="❌ LINE 찾지 못함")

def run_valv_finder():
    if not doc:
        label_info.config(text="❌ PDF 파일이 없습니다.")
        return
    keyword = entry_valv.get().strip().upper()
    if not keyword:
        label_info.config(text="❗ 검색어가 없습니다.")
        return
    remove_all_highlights(doc)
    for page_num, page in enumerate(doc):
        words = page.get_text("words")
        all_text, all_pos, all_rects, all_heights = [], [], [], []
        for w in words:
            txt = w[4].strip()
            if not txt:
                continue
            height = abs(w[3] - w[1])
            all_text.append(txt)
            all_pos.append(((w[0]+w[2])/2, (w[1]+w[3])/2))
            all_rects.append(fitz.Rect(w[:4]))
            all_heights.append(height)
        for i, p1 in enumerate(all_text):
            if len(p1) != 7 or not keyword.startswith(p1):
                continue
            p1_pos = all_pos[i]
            h = all_heights[i]
            radius = h * 2
            for j, t2 in enumerate(all_text):
                if len(t2) == 5 and t2.upper().startswith("AA") and distance(p1_pos, all_pos[j]) <= radius:
                    if f"{p1}-{t2}" == keyword:
                        highlight(page, [all_rects[i], all_rects[j]])
                        label_info.config(text=f"📄 VALVE 찾음: Page {page_num + 1}")
                        show_page_preview_with_zoom(doc, page_num)
                        return
        for i, txt in enumerate(all_text):
            if txt.upper() == keyword:
                highlight(page, all_rects[i])
                label_info.config(text=f"📄 VALVE 직접 찾음: Page {page_num + 1}")
                show_page_preview_with_zoom(doc, page_num)
                return
    label_info.config(text="❌ VALVE 찾지 못함")

# --------- 전역 변수 및 UI ---------
pdf_path = None
doc = None

root = tk.Tk()
root.title("PDF TEXT FINDER")
root.geometry("400x150")

file_name_var = tk.StringVar()
top = tk.Frame(root)
top.pack(pady=4)
tk.Button(top, text="📂 PDF 열기", width=15, command=open_pdf).pack(side=tk.LEFT, padx=5)
tk.Entry(top, textvariable=file_name_var, width=30).pack(side=tk.LEFT)

line_frame = tk.Frame(root)
line_frame.pack(pady=4)
tk.Button(line_frame, text="🔍 LINE FINDER", width=15, command=run_line_finder).pack(side=tk.LEFT, padx=5)
entry_line = tk.Entry(line_frame, width=30)
entry_line.insert(0, "22LCQ20-BR001-DN100")
entry_line.pack(side=tk.LEFT)

valv_frame = tk.Frame(root)
valv_frame.pack(pady=4)
tk.Button(valv_frame, text="🔍 VALVE FINDER", width=15, command=run_valv_finder).pack(side=tk.LEFT, padx=5)
entry_valv = tk.Entry(valv_frame, width=30)
entry_valv.insert(0, "22QUB10-AA601")
entry_valv.pack(side=tk.LEFT)

label_info = tk.Label(root, text="")
label_info.pack(pady=5)

root.mainloop()
