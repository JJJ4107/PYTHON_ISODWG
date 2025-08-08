import fitz  # PyMuPDF
import csv
import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox
from datetime import datetime
from collections import defaultdict

# ---------------- TBN 방식: LINELIST_TBN.PY에서 하이라이트까지 복사 ----------------
def extract_and_highlight_tbn(page, doc, already_line, already_valv, line_rects, valv_rects, all_line_list, all_valv_list, page_num):
    # 아래는 LINELIST_TBN.PY 코드 거의 그대로!
    def highlight_tbn(page, rect, color, opacity=0.3):
        if rect.get_area() == 0: return
        annot = page.add_rect_annot(rect)
        annot.set_colors(stroke=color, fill=color)
        annot.set_opacity(opacity)
        annot.update()

    def merge_to_N(words, start):
        text_acc = ""
        rects = []
        end = start
        found = False
        for j in range(start, len(words)):
            t = words[j][4]
            if text_acc: text_acc += " "
            text_acc += t
            rects.append(fitz.Rect(*words[j][:4]))
            end = j
            if "N" in t or "N" in text_acc:
                found = True
                break
        if found:
            return text_acc.strip(), rects, end
        else:
            return None, [], start

    def is_valvno_start(word):
        word = word.upper()
        return (
            word.startswith('(-V') or word.startswith('(V-') or
            word.startswith('-V-') or word.startswith('-V') or word.startswith('V-')
        )

    def is_valvno_any(word):
        wordu = word.upper()
        return (
            re.match(r'^(\(?-?V-?)\d{3,5}', wordu) or
            (wordu.startswith('3/4') and 'V-' in wordu)
        )

    def find_nearby_pv(words, idx, max_dist=30):
        x0, y0, x1, y1, _ = words[idx][:5]
        center = ((x0+x1)/2, (y0+y1)/2)
        candidates = []
        for j, w in enumerate(words):
            if j == idx: continue
            tx0, ty0, tx1, ty1, ttxt = w[:5]
            ttxt_strip = ttxt.strip()
            if "-" not in ttxt_strip or len(ttxt_strip) > 8: continue
            tcenter = ((tx0+tx1)/2, (ty0+ty1)/2)
            dx, dy = tcenter[0] - center[0], tcenter[1] - center[1]
            if abs(dx) < max_dist and abs(dy) < max_dist:
                dist = (dx*dx + dy*dy)**0.5
                candidates.append((dist, j, ttxt_strip, fitz.Rect(tx0, ty0, tx1, ty1)))
        if candidates:
            candidates.sort()
            return candidates[0][2], candidates[0][3]
        return None, None

    words = page.get_text("words")
    i = 0
    while i < len(words):
        x0, y0, x1, y1, text = words[i][:5]
        word1 = text.strip()

        # LINE 처리
        if re.match(r'^\d{3}-?[A-Z]\d*$', word1) or re.match(r'^\d{3}-[A-Z]', word1):
            merged, rects, end_idx = merge_to_N(words, i)
            key = (merged,)
            if merged and key not in already_line:
                for r in rects:
                    highlight_tbn(page, r, color=(0, 1, 0), opacity=0.3)
                already_line.add(key)
                all_line_list.append([merged, page_num])
                line_rects.setdefault(merged, []).append((page_num-1, rects))
            i = end_idx + 1
            continue
        elif re.match(r'^\d{3}-?[A-Z]\d*.*N', word1):
            rect = fitz.Rect(x0, y0, x1, y1)
            key = (word1,)
            if key not in already_line:
                highlight_tbn(page, rect, color=(0, 1, 0), opacity=0.3)
                already_line.add(key)
                all_line_list.append([word1, page_num])
                line_rects.setdefault(word1, []).append((page_num-1, [rect]))

        # VALVE 처리
        if is_valvno_any(word1):
            valv_final = word1
            pv_val, pv_rect = None, None
            if is_valvno_start(word1):
                pv_val, pv_rect = find_nearby_pv(words, i)
                if pv_val:
                    valv_final = pv_val + word1
            key = (valv_final,)
            if key not in already_valv:
                if pv_rect:
                    highlight_tbn(page, pv_rect, color=(0.5, 0, 1), opacity=0.15)
                highlight_tbn(page, fitz.Rect(x0, y0, x1, y1), color=(0.5, 0, 1), opacity=0.3)
                already_valv.add(key)
                all_valv_list.append([valv_final, page_num])
                valv_rects.setdefault(valv_final, []).append((page_num-1, [fitz.Rect(x0, y0, x1, y1)]))
        i += 1

# ---------------- OTHER 방식: LINELIST_OTHER.PY에서 하이라이트까지 복사 ----------------
def extract_and_highlight_other(page, doc, line_list, valve_list, special_list, line_no_rects, valve_no_rects, special_no_rects, page_num):
    def highlight_other(page, rect, color, opacity=0.4):
        if rect.get_area() == 0: return
        annot = page.add_rect_annot(rect)
        annot.set_colors(stroke=color, fill=color)
        annot.set_opacity(opacity)
        annot.update()

    def extract_vertical_words(page, min_len=4, gap_tol=2.2):
        try:
            chars = page.get_text("chars")
        except Exception:
            return []
        columns = defaultdict(list)
        for x0, y0, x1, y1, ch, *_ in chars:
            if not ch.strip(): continue
            col_key = round(x0, 1)
            columns[col_key].append((y0, x0, x1, y1, ch))
        results = []
        for col_items in columns.values():
            col_items.sort(key=lambda it: it[0])
            word, rects, prev_y, prev_h = [], [], None, None
            for y0, x0, x1, y1, ch in col_items:
                h = y1 - y0
                if prev_y is not None and (y0 - prev_y) > (prev_h or h) * gap_tol:
                    if len(word) >= min_len: results.append((''.join(word), rects))
                    word, rects = [], []
                word.append(ch)
                rects.append(fitz.Rect(x0, y0, x1, y1))
                prev_y, prev_h = y0, h
            if len(word) >= min_len: results.append((''.join(word), rects))
        return [(txt, rects) for txt, rects in results]

    special_pattern = re.compile(r'^(AJ|BJ|AT)[0-9]{3,4}', re.IGNORECASE)
    words_h = page.get_text("words")
    words_v = page.get_text("words", sort=False)
    words_set = {tuple(w[:5]) for w in words_h}
    words = words_h + [w for w in words_v if tuple(w[:5]) not in words_set]
    rect_map = {}
    vert_words = extract_vertical_words(page)
    for vtxt, vrects in vert_words:
        t_clean = vtxt.strip().replace(" ", "")
        if len(t_clean) < 4: continue
        rect_map[vtxt] = vrects
        if any(abs(vrects[0].x0 - w[0]) < 0.1 and abs(vrects[0].y0 - w[1]) < 0.1 for w in words_h):
            continue
        words.append([vrects[0].x0, vrects[0].y0, vrects[-1].x1, vrects[-1].y1, vtxt])

    i = 0
    while i < len(words):
        x0, y0, x1, y1, text = words[i][:5]
        clean_text = text.strip().replace(" ", "")
        if len(clean_text) < 4:
            i += 1
            continue
        prefix4 = clean_text[:4].upper()
        rect = fitz.Rect(x0, y0, x1, y1)
        # LINE NO
        if re.match(r'^\d{3}', text.strip()) and '"' in text:
            merged_text = text.strip()
            j = i + 1
            while j < len(words):
                part = words[j][4].strip()
                merged_text += ' ' + part
                if re.search(r'[A-Za-z]', part):
                    x1, y1 = words[j][2], words[j][3]
                    break
                x1, y1 = words[j][2], words[j][3]
                j += 1
            full_line = merged_text.strip().replace('" /', '"/').replace(' ', '')
            highlight_other(page, rect, color=(0, 1, 0), opacity=0.2)
            line_list.append([full_line, page_num])
            line_no_rects[full_line].append((page_num - 1, rect))
            i = j - 1
        # VALVE NO
        elif (len(prefix4) > 0 and prefix4[0] == 'V' and re.match(r'^V\d{3,4}', clean_text)) or \
             (re.match(r'^\d{3}', clean_text) and '-V' in clean_text):
            highlight_other(page, rect, color=(1, 0, 1), opacity=0.2)
            valve_list.append([clean_text, page_num])
            valve_no_rects[clean_text].append((page_num - 1, rect))
        # SPECIAL NO
        elif special_pattern.match(clean_text):
            special_list.append([clean_text, page_num])
            special_no_rects[clean_text].append((page_num - 1, rect))
        i += 1

# ---------------- 나머지 tkinter 및 UI는 동일하게 유지 ----------------
root = tk.Tk()
root.title("Model Check with P&ID")

screen_width = root.winfo_screenwidth()
window_width = 400
window_height = 340
x = screen_width - window_width - 10
y = 10
root.geometry(f"{window_width}x{window_height}+{x}+{y}")

frame = tk.Frame(root, padx=10, pady=10)
frame.pack()

last_model_dir = os.getcwd()
def get_initial_dir(): global last_model_dir; return last_model_dir

def select_model_file():
    global last_model_dir
    path = filedialog.askopenfilename(
        filetypes=[("CSV files", "*.csv")], initialdir=last_model_dir)
    if path:
        last_model_dir = os.path.dirname(path)
        model_entry.delete(0, tk.END)
        model_entry.insert(0, path)

def select_pid_file():
    model_path = model_entry.get()
    init_dir = os.path.dirname(model_path) if model_path and os.path.exists(model_path) else get_initial_dir()
    path = filedialog.askopenfilename(
        filetypes=[("PDF files", "*.pdf")], initialdir=init_dir)
    if path:
        pid_entry.delete(0, tk.END)
        pid_entry.insert(0, path)

# MODEL FILE 입력창 및 버튼
model_entry = tk.Entry(frame, width=30)
model_entry.grid(row=0, column=1)
model_entry.insert(0, "Model.CSV")
tk.Button(frame, text="MODEL FILE :", width=12, command=select_model_file).grid(row=0, column=0, sticky="w")

# PID FILE 입력창 및 버튼
pid_entry = tk.Entry(frame, width=30)
pid_entry.grid(row=1, column=1)
tk.Button(frame, text="PID FILE :", width=12, command=select_pid_file).grid(row=1, column=0, sticky="w")

line_mode = tk.StringVar(value="OTHER")
tk.Radiobutton(frame, text="TBN", variable=line_mode, value="OTHER").grid(row=2, column=0, sticky="w", padx=(70,0))
tk.Radiobutton(frame, text="OTHER", variable=line_mode, value="TBN").grid(row=2, column=1, sticky="w", padx=(90,0))

tk.Button(frame, text="Model Check With P&ID", width=42, command=lambda: run_model_check()).grid(row=3, column=0, columnspan=2, pady=10)
tk.Button(frame, text="Open CHK PDF", width=21, command=lambda: open_chk_pdf()).grid(row=4, column=0, pady=5)
tk.Button(frame, text="Open CSV", width=21, command=lambda: open_model_csv()).grid(row=4, column=1, pady=5)

def on_right_click(event):
    selection = result_box.curselection()
    if selection:
        value = result_box.get(selection[0]).split("   Page")[0]
        root.clipboard_clear()
        root.clipboard_append(value)
        root.update()
result_box = tk.Listbox(root, width=50, height=10)
result_box.pack(padx=10, pady=10)
result_box.bind("<Button-3>", on_right_click)

last_chk_pdf_path = ""

def run_model_check():
    global last_chk_pdf_path
    model_path = model_entry.get()
    pdf_path = pid_entry.get()
    if not os.path.exists(model_path) or not os.path.exists(pdf_path):
        messagebox.showerror("오류", "파일 경로가 올바르지 않습니다.")
        return
    with open(model_path, newline='', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        model_set = set(row[0].strip().upper() for row in reader if row and row[0].strip())
    doc = fitz.open(pdf_path)
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    folder = os.path.dirname(pdf_path)
    today_str = datetime.now().strftime("%Y%m%d")
    out_pdf_path = os.path.join(folder, f"CHK_{base_name}_{today_str}.PDF")
    last_chk_pdf_path = out_pdf_path
    unmodel_csv = os.path.join(folder, f"UNMODEL_{base_name}_{today_str}.CSV")

    result_box.delete(0, tk.END)
    displayed_set = set()
    unmatched_dict = {}

    if line_mode.get() == "TBN":
        already_line = set()
        already_valv = set()
        all_line_list = []
        all_valv_list = []
        line_rects = {}
        valv_rects = {}
        for page_num, page in enumerate(doc, 1):
            extract_and_highlight_tbn(page, doc, already_line, already_valv, line_rects, valv_rects, all_line_list, all_valv_list, page_num)
        # 결과 표시
        for l in all_line_list:
            val = l[0]
            page_no = l[1]
            upper_val = val.upper()
            display_text = f"{val}   Page : {page_no}"
            if upper_val in model_set:
                pass
            else:
                unmatched_dict[upper_val] = page_no
            if upper_val not in displayed_set:
                result_box.insert(tk.END, display_text)
                result_box.itemconfig(tk.END, {'fg': 'purple'})
                displayed_set.add(upper_val)
        for v in all_valv_list:
            val = v[0]
            page_no = v[1]
            upper_val = val.upper()
            display_text = f"{val}   Page : {page_no}"
            if upper_val in model_set:
                pass
            else:
                unmatched_dict[upper_val] = page_no
            if upper_val not in displayed_set:
                result_box.insert(tk.END, display_text)
                result_box.itemconfig(tk.END, {'fg': 'purple'})
                displayed_set.add(upper_val)
    else:
        line_list, valve_list, special_list = [], [], []
        line_no_rects, valve_no_rects, special_no_rects = defaultdict(list), defaultdict(list), defaultdict(list)
        for page_num, page in enumerate(doc, 1):
            extract_and_highlight_other(page, doc, line_list, valve_list, special_list, line_no_rects, valve_no_rects, special_no_rects, page_num)
        # 결과 표시
        for l in line_list:
            val = l[0]
            page_no = l[1]
            upper_val = val.upper()
            display_text = f"{val}   Page : {page_no}"
            if upper_val in model_set:
                pass
            else:
                unmatched_dict[upper_val] = page_no
            if upper_val not in displayed_set:
                result_box.insert(tk.END, display_text)
                result_box.itemconfig(tk.END, {'fg': 'purple'})
                displayed_set.add(upper_val)
        for v in valve_list:
            val = v[0]
            page_no = v[1]
            upper_val = val.upper()
            display_text = f"{val}   Page : {page_no}"
            if upper_val in model_set:
                pass
            else:
                unmatched_dict[upper_val] = page_no
            if upper_val not in displayed_set:
                result_box.insert(tk.END, display_text)
                result_box.itemconfig(tk.END, {'fg': 'purple'})
                displayed_set.add(upper_val)
        for s in special_list:
            val = s[0]
            page_no = s[1]
            upper_val = val.upper()
            display_text = f"SPECIAL: {val}   Page : {page_no}"
            if upper_val in model_set:
                pass
            else:
                unmatched_dict[upper_val] = page_no
            if upper_val not in displayed_set:
                result_box.insert(tk.END, display_text)
                result_box.itemconfig(tk.END, {'fg': 'purple'})
                displayed_set.add(upper_val)
    doc.save(out_pdf_path)
    doc.close()
    if unmatched_dict:
        with open(unmodel_csv, "w", newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(["UNMODELED NO", "PID PAGE"])
            for val in sorted(unmatched_dict):
                writer.writerow([val, unmatched_dict[val]])
        messagebox.showinfo("완료", f"비모델 NO가 저장되었습니다:\n{unmodel_csv}")
    else:
        messagebox.showinfo("완료", "모든 항목이 모델과 일치합니다.")

def open_chk_pdf():
    try:
        if last_chk_pdf_path and os.path.exists(last_chk_pdf_path):
            os.startfile(last_chk_pdf_path)
        else:
            messagebox.showerror("오류", "CHK PDF 파일이 존재하지 않습니다.")
    except Exception as e:
        messagebox.showerror("오류", f"PDF 열기에 실패했습니다.\n{e}")

def open_model_csv():
    path = model_entry.get()
    if path and os.path.exists(path):
        try:
            os.startfile(path)
        except Exception as e:
            messagebox.showerror("오류", f"CSV 열기에 실패했습니다.\n{e}")
    else:
        messagebox.showerror("오류", "모델 파일 경로가 올바르지 않습니다.")

root.mainloop()
