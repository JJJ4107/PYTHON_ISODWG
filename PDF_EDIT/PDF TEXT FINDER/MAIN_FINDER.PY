import tkinter as tk
from tkinter import filedialog
import fitz
import os
import math
import subprocess
import sys
import uuid

os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = os.path.join(
    sys.prefix,
    "Lib", "site-packages", "PyQt5", "Qt5", "plugins", "platforms"
)

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

preview_proc = None
last_temp_pdf = None

def show_page_preview_with_zoom(doc, page_num):
    global preview_proc, last_temp_pdf
    if preview_proc is not None:
        try:
            preview_proc.terminate()
        except Exception:
            pass
        preview_proc = None
    if last_temp_pdf is not None:
        try:
            if os.path.exists(last_temp_pdf):
                os.remove(last_temp_pdf)
        except Exception:
            pass
        last_temp_pdf = None
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

# ------- 순환 찾기 인덱스 및 결과 저장 전역 ---------
line_finds = []
valv_finds = []
line_idx = -1
valv_idx = -1

def run_line_finder():
    global line_finds, line_idx
    if not doc:
        label_info.config(text="❌ PDF 파일이 없습니다.")
        return
    keyword = entry_line.get().strip()
    if not keyword:
        label_info.config(text="❗ 검색어가 없습니다.")
        return

    mode = line_mode.get()

    # 첫 시도이거나 검색어가 바뀌면 새로 찾기
    if not hasattr(run_line_finder, 'last_keyword') or run_line_finder.last_keyword != keyword or run_line_finder.last_mode != mode:
        remove_all_highlights(doc)
        line_finds = []
        line_idx = -1
        run_line_finder.last_keyword = keyword
        run_line_finder.last_mode = mode
        for page_num, page in enumerate(doc):
            words = page.get_text("words")
            if mode == "1":
                line_map = {}
                for w in words:
                    line_idx1 = (w[5], w[6])
                    if line_idx1 not in line_map:
                        line_map[line_idx1] = []
                    line_map[line_idx1].append(w)
                for idx, line_words in line_map.items():
                    line_words = sorted(line_words, key=lambda x: x[0])
                    full_line = " ".join([w[4] for w in line_words])
                    if full_line.replace(" ", "") == keyword.replace(" ", ""):
                        line_finds.append( (page_num, [fitz.Rect(w[:4]) for w in line_words]) )
            elif mode == "2":
                line_map = {}
                for w in words:
                    line_idx1 = (w[5], w[6])
                    if line_idx1 not in line_map:
                        line_map[line_idx1] = []
                    line_map[line_idx1].append(w)
                line_idxs = sorted(line_map.keys())
                for idx, line_words in line_map.items():
                    line1 = " ".join([w[4] for w in sorted(line_words, key=lambda x: x[0])])
                    prev_idx = (idx[0], idx[1]-1)
                    if prev_idx in line_map:
                        comb = " ".join([w[4] for w in sorted(line_map[prev_idx]+line_words, key=lambda x: x[0])])
                        if comb.replace(" ", "") == keyword.replace(" ", ""):
                            line_finds.append( (page_num, [fitz.Rect(w[:4]) for w in line_map[prev_idx]+line_words]) )
                    next_idx = (idx[0], idx[1]+1)
                    if next_idx in line_map:
                        comb = " ".join([w[4] for w in sorted(line_words+line_map[next_idx], key=lambda x: x[0])])
                        if comb.replace(" ", "") == keyword.replace(" ", ""):
                            line_finds.append( (page_num, [fitz.Rect(w[:4]) for w in line_words+line_map[next_idx]]) )
                    ws = sorted(line_words, key=lambda x: x[0])
                    for i in range(len(ws)-1):
                        comb = (ws[i][4] + ws[i+1][4]).replace(" ", "")
                        if comb == keyword.replace(" ", ""):
                            line_finds.append( (page_num, [fitz.Rect(ws[i][:4]), fitz.Rect(ws[i+1][:4])]) )
            elif mode == "3":
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
                    if len(p1) != 7 or not keyword.upper().startswith(p1.upper()):
                        continue
                    p1_pos = all_pos[i]
                    h = all_heights[i]
                    radius_lp2 = h * 3
                    LP2 = LP3 = None
                    lp2_idx = lp3_idx = -1
                    for j, t2 in enumerate(all_text):
                        if len(t2) == 5 and t2.upper().startswith("BR") and distance(p1_pos, all_pos[j]) <= radius_lp2:
                            if not keyword.upper().startswith(f"{p1}-{t2}".upper()):
                                continue
                            LP2 = t2
                            lp2_idx = j
                            break
                    if LP2:
                        lp2_pos = all_pos[lp2_idx]
                        radius_lp3 = h * 3
                        for k, t3 in enumerate(all_text):
                            if "DN" in t3.upper() and distance(lp2_pos, all_pos[k]) <= radius_lp3:
                                if f"{p1}-{LP2}-{t3}".upper() == keyword.upper():
                                    LP3 = t3
                                    lp3_idx = k
                                    break
                        targets = [all_rects[i], all_rects[lp2_idx]]
                        if LP3 and lp3_idx != -1:
                            targets.append(all_rects[lp3_idx])
                        line_finds.append( (page_num, targets) )
        if line_finds:
            line_idx = 0
        else:
            line_idx = -1

    if not line_finds:
        label_info.config(text="❌ LINE 찾지 못함")
        return

    # 순환
    if line_idx == -1:
        line_idx = 0
    else:
        line_idx = (line_idx + 1) % len(line_finds)
    # 저장 (순환 index)
    globals()['line_idx'] = line_idx
    page_num, rects = line_finds[line_idx]
    remove_all_highlights(doc)
    highlight(doc[page_num], rects)
    # 상태 표기
    label_info.config(text=f"📄 LINE 찾음: {line_idx+1}/{len(line_finds)}개 (Page {page_num+1})")
    # 결과가 1개면 첫 클릭만 미리보기
    if len(line_finds) == 1:
        if getattr(run_line_finder, "already_shown", False):
            return
        run_line_finder.already_shown = True
    else:
        run_line_finder.already_shown = False
    show_page_preview_with_zoom(doc, page_num)

def run_valv_finder():
    global valv_finds, valv_idx
    if not doc:
        label_info.config(text="❌ PDF 파일이 없습니다.")
        return
    keyword = entry_valv.get().strip().upper()
    if not keyword:
        label_info.config(text="❗ 검색어가 없습니다.")
        return

    # 첫 시도이거나 검색어가 바뀌면 새로 찾기
    if not hasattr(run_valv_finder, 'last_keyword') or run_valv_finder.last_keyword != keyword:
        remove_all_highlights(doc)
        valv_finds = []
        valv_idx = -1
        run_valv_finder.last_keyword = keyword
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
                            valv_finds.append( (page_num, [all_rects[i], all_rects[j]]) )
                # 직접 매치
            for i, txt in enumerate(all_text):
                if txt.upper() == keyword:
                    valv_finds.append( (page_num, [all_rects[i]]) )
        if valv_finds:
            valv_idx = 0
        else:
            valv_idx = -1

    if not valv_finds:
        label_info.config(text="❌ VALVE 찾지 못함")
        return

    if valv_idx == -1:
        valv_idx = 0
    else:
        valv_idx = (valv_idx + 1) % len(valv_finds)
    globals()['valv_idx'] = valv_idx
    page_num, rects = valv_finds[valv_idx]
    remove_all_highlights(doc)
    highlight(doc[page_num], rects)
    label_info.config(text=f"📄 VALVE 찾음: {valv_idx+1}/{len(valv_finds)}개 (Page {page_num+1})")
    # 1개일 때 첫 클릭만 미리보기
    if len(valv_finds) == 1:
        if getattr(run_valv_finder, "already_shown", False):
            return
        run_valv_finder.already_shown = True
    else:
        run_valv_finder.already_shown = False
    show_page_preview_with_zoom(doc, page_num)

pdf_path = None
doc = None

root = tk.Tk()
root.title("PDF TEXT FINDER")
root.geometry("400x180")

file_name_var = tk.StringVar()
top = tk.Frame(root)
top.pack(pady=4)
tk.Button(top, text="📂 PDF 열기", width=15, command=open_pdf).pack(side=tk.LEFT, padx=5)
tk.Entry(top, textvariable=file_name_var, width=30).pack(side=tk.LEFT)

mode_frame = tk.Frame(root)
mode_frame.pack(pady=4)
line_mode = tk.StringVar(value="3")
tk.Label(mode_frame, text="LINE 찾기 옵션:").pack(side=tk.LEFT)
tk.Radiobutton(mode_frame, text="1 LINE", variable=line_mode, value="1").pack(side=tk.LEFT)
tk.Radiobutton(mode_frame, text="2 LINE", variable=line_mode, value="2").pack(side=tk.LEFT)
tk.Radiobutton(mode_frame, text="3 LINE", variable=line_mode, value="3").pack(side=tk.LEFT)

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
