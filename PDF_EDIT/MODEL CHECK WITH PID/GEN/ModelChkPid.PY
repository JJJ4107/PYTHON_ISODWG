import fitz  # PyMuPDF
import csv
import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox
from datetime import datetime

# ---------------- 공통 하이라이트 함수 ----------------
def highlight(page, rect, color, opacity=0.4):
    if not rect or rect.is_empty or rect.is_infinite:
        return
    annot = page.add_rect_annot(rect)
    annot.set_colors(stroke=color, fill=color)
    annot.set_opacity(opacity)
    annot.update()

# ---------------- VALVE 및 LINE 추출 함수 ----------------
def extract_line_valve_from_page(page):
    import math

    def center(rect):
        return ((rect.x0 + rect.x1) / 2, (rect.y0 + rect.y1) / 2)

    def distance(r1, r2):
        c1 = center(r1)
        c2 = center(r2)
        return math.hypot(c1[0] - c2[0], c1[1] - c2[1])

    def normalize_p3(*words):
        return '-'.join(w.replace(' ', '-') for w in words if w).replace('--', '-')

    P1_PATTERN = re.compile(r'^(00|11|21|22)[A-Za-z0-9]{0,7}$', re.IGNORECASE)
    P2_PATTERN = re.compile(r'^(BR|AA)[A-Za-z0-9]{0,8}$', re.IGNORECASE)
    P3_DN_PATTERN = re.compile(r'^DN.{0,11}$', re.IGNORECASE)
    P3_H_PATTERN = re.compile(r'^H.{0,11}$', re.IGNORECASE)

    words = page.get_text("words")
    words.sort(key=lambda w: (w[1], w[0]))  # 정렬: y, x

    results = []
    n = len(words)

    if line_mode.get() == "1":
        for word in words:
            text = word[4].strip().upper().replace(" ", "")
            if P1_PATTERN.match(text):
                rect = fitz.Rect(word[:4])
                results.append((text, rect, page.number + 1))
    else:
        for i, w in enumerate(words):
            text = w[4].strip().replace(" ", "")
            if not P1_PATTERN.match(text):
                continue
            p1 = text
            p1_rect = fitz.Rect(w[:4])

            min_dist = float('inf')
            found_p2 = None
            found_p2_rect = None
            for j, next_w in enumerate(words):
                if i == j:
                    continue
                next_text = next_w[4].strip().replace(" ", "")
                if not P2_PATTERN.match(next_text):
                    continue
                next_rect = fitz.Rect(next_w[:4])
                dist = distance(p1_rect, next_rect)
                if dist < min_dist:
                    min_dist = dist
                    found_p2 = next_w[4].strip()
                    found_p2_rect = next_rect

            if not found_p2:
                continue

            if found_p2.upper().startswith("BR"):
                min_dist3 = float('inf')
                found_p3 = None
                found_p3_rect = None
                for k, next_w3 in enumerate(words):
                    dn_raw = next_w3[4].strip()
                    if not P3_DN_PATTERN.match(dn_raw):
                        continue
                    dn_rect = fitz.Rect(next_w3[:4])
                    dist3 = distance(found_p2_rect, dn_rect)
                    if dist3 < min_dist3:
                        p3_full = dn_raw
                        p3_rects = [dn_rect]
                        if k + 1 < n:
                            next_h_word = words[k + 1][4].strip()
                            next_h_rect = fitz.Rect(words[k + 1][:4])
                            if P3_H_PATTERN.match(next_h_word) and distance(dn_rect, next_h_rect) < 20:
                                p3_full = f"{dn_raw} {next_h_word}"
                                p3_rects.append(next_h_rect)
                        found_p3 = normalize_p3(*p3_full.split())
                        found_p3_rect = p3_rects[0]
                        min_dist3 = dist3
                if found_p3:
                    full_line = f"{p1}-{found_p2.replace(' ', '-')}-{found_p3}"
                    results.append((full_line, p1_rect, page.number + 1))
                    results.append((full_line, found_p2_rect, page.number + 1))
                    results.append((full_line, found_p3_rect, page.number + 1))
            elif found_p2.upper().startswith("AA"):
                valve_no = f"{p1}-{found_p2.replace(' ', '-')}"
                results.append((valve_no, p1_rect, page.number + 1))
                results.append((valve_no, found_p2_rect, page.number + 1))

    return results

# ... (생략: 기존 코드 동일) ...

# ---------------- 모델 비교 실행 함수 ----------------
def run_model_check():
    global last_chk_pdf_path  # 외부에서 열기 위해 경로 저장
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
    last_chk_pdf_path = out_pdf_path  # 저장해두기
    unmodel_csv = os.path.join(folder, f"UNMODEL_{base_name}_{today_str}.CSV")

    unmatched_dict = {}
    result_box.delete(0, tk.END)
    all_results = []

    for page in doc:
        results = extract_line_valve_from_page(page)
        all_results.extend(results)

    displayed_set = set()
    all_results.sort(key=lambda x: (x[2], x[0]))

    for val, rect, page_no in all_results:
        upper_val = val.upper()
        if upper_val in model_set:
            highlight(doc[page_no - 1], rect, color=(0, 0, 1))
        else:
            highlight(doc[page_no - 1], rect, color=(1, 0, 0))
            unmatched_dict[upper_val] = page_no

        if upper_val not in displayed_set:
            display_text = f"{val}   Page : {page_no}"
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

# ---------------- CHK PDF 열기 함수 ----------------
def open_chk_pdf():
    try:
        if last_chk_pdf_path and os.path.exists(last_chk_pdf_path):
            os.startfile(last_chk_pdf_path)
        else:
            messagebox.showerror("오류", "CHK PDF 파일이 존재하지 않습니다.")
    except Exception as e:
        messagebox.showerror("오류", f"PDF 열기에 실패했습니다.\n{e}")

# ---------------- MODEL CSV 열기 함수 ----------------
def open_model_csv():
    path = model_entry.get()
    if path and os.path.exists(path):
        try:
            os.startfile(path)
        except Exception as e:
            messagebox.showerror("오류", f"CSV 열기에 실패했습니다.\n{e}")
    else:
        messagebox.showerror("오류", "모델 파일 경로가 올바르지 않습니다.")

# ---------------- tkinter UI 구성 ----------------
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

def get_initial_dir():
    global last_model_dir
    return last_model_dir

def select_model_file():
    global last_model_dir
    path = filedialog.askopenfilename(
        filetypes=[("CSV files", "*.csv")],
        initialdir=last_model_dir
    )
    if path:
        last_model_dir = os.path.dirname(path)
        model_entry.delete(0, tk.END)
        model_entry.insert(0, path)

def select_pid_file():
    model_path = model_entry.get()
    init_dir = os.path.dirname(model_path) if model_path and os.path.exists(model_path) else get_initial_dir()
    path = filedialog.askopenfilename(
        filetypes=[("PDF files", "*.pdf")],
        initialdir=init_dir
    )
    if path:
        pid_entry.delete(0, tk.END)
        pid_entry.insert(0, path)
        
# MODEL FILE 입력창 및 버튼
model_entry = tk.Entry(frame, width=30)
model_entry.grid(row=0, column=1)
model_entry.insert(0, "Model.CSV")
tk.Button(frame, text="MODEL FILE :", width=12, command=select_model_file).grid(row=0, column=0, sticky="e")

# PID FILE 입력창 및 버튼
pid_entry = tk.Entry(frame, width=30)
pid_entry.grid(row=1, column=1)
tk.Button(frame, text="PID FILE :", width=12, command=select_pid_file).grid(row=1, column=0, sticky="e")

# LINE MODE
line_mode = tk.StringVar(value="3")
tk.Radiobutton(frame, text="1LINE", variable=line_mode, value="1").grid(row=2, column=0, sticky="w", padx=(10,0))
tk.Radiobutton(frame, text="3LINE", variable=line_mode, value="3").grid(row=2, column=1, sticky="w", padx=(90,0))

# MODEL CHECK 버튼 - 전체 길이 통일
tk.Button(frame, text="Model Check With P&ID", width=42, command=run_model_check).grid(row=3, column=0, columnspan=2, pady=10)

# OPEN CHK PDF / OPEN CSV - 좌우 절반씩 분할
tk.Button(frame, text="Open CHK PDF", width=21, command=open_chk_pdf).grid(row=4, column=0, pady=5)
tk.Button(frame, text="Open CSV", width=21, command=open_model_csv).grid(row=4, column=1, pady=5)

# MODEL FILE 입력창 및 버튼 - 왼쪽 정렬
model_row = tk.Frame(frame)
model_row.grid(row=0, column=0, columnspan=2, sticky="w")
tk.Button(model_row, text="MODEL FILE :", width=12, command=select_model_file).pack(side="left")
model_entry = tk.Entry(model_row, width=30)
model_entry.pack(side="left")
model_entry.insert(0, "Model.CSV")

# PID FILE 입력창 및 버튼 - 왼쪽 정렬
pid_row = tk.Frame(frame)
pid_row.grid(row=1, column=0, columnspan=2, sticky="w")
tk.Button(pid_row, text="PID FILE :", width=12, command=select_pid_file).pack(side="left")
pid_entry = tk.Entry(pid_row, width=30)
pid_entry.pack(side="left")



# ▶ 결과 박스
def on_right_click(event):
    selection = result_box.curselection()
    if selection:
        full_text = result_box.get(selection[0])
        value = full_text.split("   Page")[0]
        if line_mode.get() == "3":
            match = re.match(r"^([0-9A-Z]+)-([A-Z]+[0-9]*)-(.+)$", value)
            if match:
                p1, p2, p3 = match.groups()
                value = f"{p1} {p2} {p3}"
            else:
                parts = value.split("-")
                if len(parts) == 2:
                    value = f"{parts[0]} {parts[1]}"
        root.clipboard_clear()
        root.clipboard_append(value)
        root.update()
       # messagebox.showinfo("복사됨", f"복사됨: {value}")

result_box = tk.Listbox(root, width=50, height=10)
result_box.pack(padx=10, pady=10)
result_box.bind("<Button-3>", on_right_click)

# ▶ CHK PDF 경로 저장용 전역 변수
last_chk_pdf_path = ""

root.mainloop()
