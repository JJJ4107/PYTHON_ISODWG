import os, re, ezdxf, math
import tkinter as tk
from tkinter import filedialog

DENSITY_STEEL = 7.85e-6  # kg/mm^3

FIXED_WT = {"DN150XS/40": 9.9, "SP-H200X200": 0.8}

# 정규식 정의
PLATE_PAT = re.compile(r"PL(\d+)[xX](\d+)[xX](\d+)", re.I)
HBEAM_PAT = re.compile(r"H(\d+)[xX](\d+)[xX](\d+)[xX](\d+)", re.I)
CCHAN_PAT = re.compile(r"C(\d+)[xX](\d+)[xX](\d+(?:\.\d+)?)[xX](\d+(?:\.\d+)?)", re.I)
ANGLE_PAT = re.compile(r"L(\d+)[xX](\d+)[xX](\d+)", re.I)
PIPE_PAT = re.compile(r"(?:DN)?(\d+)[aA]?$", re.I)

HEADERS = ["NO.", "Q'TY", "DESCRIPTION", "SIZE", "LENGTH", "MAT'L", "UNIT", "TOTAL", "REMARK"]

SCH40_PIPE_DATA = {
    15:  (21.3, 2.77), 20:  (26.7, 2.87), 25:  (33.4, 3.38), 32:  (42.2, 3.56),
    40:  (48.3, 3.68), 50:  (60.3, 3.91), 65:  (73.0, 5.16), 80:  (88.9, 5.49),
    100: (114.3, 6.02), 150: (168.3, 7.11), 200: (219.1, 8.18),
    250: (273.0, 9.27), 300: (323.8, 9.53),
}

def calc_sch40_pipe_weight(DN, density=DENSITY_STEEL):
    if DN not in SCH40_PIPE_DATA:
        return 0.0
    OD, thickness = SCH40_PIPE_DATA[DN]
    ID = OD - 2 * thickness
    area = (math.pi / 4) * (OD**2 - ID**2)
    return area * density  # kg/mm

def calc_h_beam_weight(H, B, tw, tf, density=DENSITY_STEEL):
    return (2 * B * tf + (H - 2 * tf) * tw) * density

def calc_c_channel_weight(H, B, tw, tf, density=DENSITY_STEEL):
    return (2 * B * tf + (H - 2 * tf) * tw) * density

def calc_angle_weight(L1, L2, t, density=DENSITY_STEEL):
    return (L1 * t + L2 * t - t * t) * density

def calc_unit_weight(size_txt: str, length_mm: float) -> float:
    s = size_txt.strip().upper()

    if s in FIXED_WT:
        return FIXED_WT[s]  # 무게가 정의된 경우 단위 무게 그대로 사용 (계산 X)

    if m := HBEAM_PAT.fullmatch(s):
        H, B, tw, tf = map(int, m.groups())
        return round(calc_h_beam_weight(H, B, tw, tf) * length_mm, 1)

    if m := CCHAN_PAT.fullmatch(s):
        H, B, tw, tf = map(float, m.groups())
        return round(calc_c_channel_weight(H, B, tw, tf) * length_mm, 1)

    if m := ANGLE_PAT.fullmatch(s):
        L1, L2, t = map(int, m.groups())
        return round(calc_angle_weight(L1, L2, t) * length_mm, 1)

    if m := PLATE_PAT.fullmatch(s):
        t, w, l = map(float, m.groups())
        return round(t * w * l * DENSITY_STEEL, 1)

    if m := PIPE_PAT.fullmatch(s):
        DN = int(m.group(1))
        weight_per_mm = calc_sch40_pipe_weight(DN)
        return round(weight_per_mm * length_mm, 1)

    return 0.0

def group_rows(entities, header_y, tol=2.0):
    rows, current_row = [], []
    last_y = None
    for (y, x, txt, ent) in entities:
        if y >= header_y:
            continue
        if last_y is None or abs(y - last_y) <= tol:
            current_row.append((x, txt, ent))
        else:
            rows.append(current_row)
            current_row = [(x, txt, ent)]
        last_y = y
    if current_row:
        rows.append(current_row)
    return rows

def process_dxf_file(dxf_path, output_dir):
    base_name = os.path.splitext(os.path.basename(dxf_path))[0].replace("-A", "")
    new_dxf = os.path.join(output_dir, base_name + ".DXF")
    new_txt = os.path.join(output_dir, base_name + ".TXT")

    doc = ezdxf.readfile(dxf_path)
    msp = doc.modelspace()

    ents = []
    for e in msp:
        if e.dxftype() == "TEXT":
            ents.append((e.dxf.insert[1], e.dxf.insert[0], e.dxf.text.strip(), e))
        elif e.dxftype() == "MTEXT":
            ents.append((e.dxf.insert[1], e.dxf.insert[0], e.text.strip(), e))

    ents.sort(key=lambda t: (-t[0], t[1]))

    header_pos = {}
    for y, x, txt, _ in ents:
        key = txt.upper()
        if key in HEADERS and key not in header_pos:
            header_pos[key] = (x, y)

    if not all(k in header_pos for k in ("DESCRIPTION", "SIZE")):
        print(f"[스킵됨] {dxf_path}: 'DESCRIPTION' 또는 'SIZE' 헤더가 누락되었습니다.")
        return

    header_y = max([pos[1] for pos in header_pos.values()])
    col_order = sorted(header_pos.items(), key=lambda kv: kv[1][0])
    col_names = [c[0] for c in col_order]
    col_xpos = [c[1][0] for c in col_order]

    rows_raw = group_rows(ents, header_y)
    output_lines = []
    total_weight_sum = 0.0
    total_col_y = header_pos.get("TOTAL", (0, 0))[1]

    for row in rows_raw:
        cols = {h: "" for h in col_names}
        ents_map = {h: None for h in col_names}

        for x, txt, ent in row:
            nearest_idx = min(range(len(col_xpos)), key=lambda i: abs(x - col_xpos[i]))
            header = col_names[nearest_idx]
            cols[header] = txt
            ents_map[header] = ent

        try:
            qty = int(float(cols.get("Q'TY", "1") or "1"))
        except ValueError:
            qty = 1

        desc = cols.get("DESCRIPTION", "")
        size = cols.get("SIZE", "")
        try:
            length = int(float(cols.get("LENGTH", "0") or "0"))
        except ValueError:
            length = 0

        unit_wt = round(calc_unit_weight(size, length), 1)
        total_wt = round(unit_wt * qty, 1)

        if unit_wt == 0.0:
            continue

        if ents_map.get("UNIT") and ents_map["UNIT"].dxf.text.upper() != "UNIT":
            ents_map["UNIT"].dxf.text = "-" if qty == 1 else f"{unit_wt:.1f}"

        if ents_map.get("TOTAL") and ents_map["TOTAL"].dxf.text.upper() != "TOTAL":
            ents_map["TOTAL"].dxf.text = f"{total_wt:.1f}"

        cols["UNIT"] = "-" if qty == 1 else f"{unit_wt:.1f}"
        cols["TOTAL"] = f"{total_wt:.1f}"

        try:
            total_weight_sum += float(cols["TOTAL"])
        except:
            pass

        line = "{:<4} {:<6} {:<30} {:<20} {:>8} {:<10} {:>10} {:>10} {:<}".format(
            cols.get("NO.", ""), qty, desc, size, length,
            cols.get("MAT'L", ""), cols["UNIT"], cols["TOTAL"], cols.get("REMARK", "")
        )
        output_lines.append(line)

    for i in range(len(ents) - 1):
        if ents[i][2].upper() == "TOTAL WEIGHT(KG) :":
            ents[i + 1][3].dxf.text = f"{round(total_weight_sum, 1)}"
            break

    with open(new_txt, "w", encoding="utf-8") as f:
        f.write("{:<4} {:<6} {:<30} {:<20} {:>8} {:<10} {:>10} {:>10} {:<}\n".format(
            "NO.", "QTY", "DESCRIPTION", "SIZE", "LENGTH", "MAT'L", "UNIT", "TOTAL", "REMARK"
        ))
        for line in output_lines:
            f.write(line + "\n")
        f.write(f"\nTOTAL WEIGHT(Kg) : {round(total_weight_sum, 1)}\n")

    doc.saveas(new_dxf)
    print(f"[완료] {dxf_path} → {new_dxf}, {new_txt} 저장 (총 {len(output_lines)}행, {round(total_weight_sum, 1)} Kg)")

def main():
    root = tk.Tk()
    root.withdraw()
    folder_selected = filedialog.askdirectory(title="DXF 파일이 들어있는 폴더 선택")

    if not folder_selected:
        print("폴더가 선택되지 않았습니다.")
        return

    dxf_files = [f for f in os.listdir(folder_selected) if f.lower().endswith(".dxf")]
    if not dxf_files:
        print("선택된 폴더에 DXF 파일이 없습니다.")
        return

    for dxf_file in dxf_files:
        try:
            full_path = os.path.join(folder_selected, dxf_file)
            process_dxf_file(full_path, folder_selected)
        except Exception as e:
            print(f"[오류] {dxf_file}: {e}")

if __name__ == "__main__":
    main()
