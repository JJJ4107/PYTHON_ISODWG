import os, re, ezdxf

DENSITY_STEEL = 7.85e-6  # kg/mm³

FIXED_WT   = {"DN150xS/40": 9.9, "PL10x250x250": 4.9}
LINEAR_WT  = {"H150x150x7x10": 0.0315, "C150x75x6.5x10": 18.6 / 1000}
PLATE_PAT  = re.compile(r"PL(\d+)[xX](\d+)[xX](\d+)", re.I)

HEADERS = ["NO.", "Q'TY", "DESCRIPTION", "SIZE", "LENGTH", "UNIT", "TOTAL", "MAT'L", "REMARK"]

def calc_unit_weight(size_txt: str, length_mm: float) -> float:
    s = size_txt.strip()
    if s in FIXED_WT:
        return FIXED_WT[s]
    if s in LINEAR_WT:
        return round(LINEAR_WT[s] * length_mm, 1)
    m = PLATE_PAT.fullmatch(s)
    if m:
        t, w, l = map(float, m.groups())
        return round(t * w * l * DENSITY_STEEL, 1)
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

def process_dxf_file(dxf_path):
    base_name = os.path.splitext(os.path.basename(dxf_path))[0]
    new_dxf = base_name + "-A.DXF"
    new_txt = base_name + "-A.TXT"

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
        if len(header_pos) == len(HEADERS):
            break

    if len(header_pos) < len(HEADERS):
        print(f"[스킵됨] {dxf_path}: 헤더가 누락되었습니다.")
        return

    header_y = max([pos[1] for pos in header_pos.values()])
    col_order  = sorted(header_pos.items(), key=lambda kv: kv[1][0])
    col_names  = [c[0] for c in col_order]
    col_xpos   = [c[1][0] for c in col_order]

    rows_raw = group_rows(ents, header_y)
    output_lines = []
    total_weight_sum = 0.0

    for row in rows_raw:
        cols = {h: "" for h in col_names}
        ents_map = {h: None for h in col_names}

        for x, txt, ent in row:
            nearest_idx = min(range(len(col_xpos)), key=lambda i: abs(x - col_xpos[i]))
            header = col_names[nearest_idx]
            cols[header] = txt
            ents_map[header] = ent

        try:
            qty = int(float(cols["Q'TY"]))
        except ValueError:
            continue
        desc = cols["DESCRIPTION"]
        size = cols["SIZE"]
        try:
            length = int(float(cols["LENGTH"]))
        except ValueError:
            length = 0

        unit_wt = round(calc_unit_weight(size, length), 1)
        total_wt = round(unit_wt * qty, 1)
        total_weight_sum += total_wt

        if ents_map["UNIT"]:
            ents_map["UNIT"].dxf.text = f"{unit_wt:.1f}"
        if ents_map["TOTAL"]:
            ents_map["TOTAL"].dxf.text = f"{total_wt:.1f}"

        cols["UNIT"] = f"{unit_wt:.1f}"
        cols["TOTAL"] = f"{total_wt:.1f}"

        line = "{:<4} {:<6} {:<30} {:<20} {:>8} {:>10} {:>10} {:<10} {:<}".format(
            cols["NO."], qty, desc, size, length, cols["UNIT"], cols["TOTAL"], cols["MAT'L"], cols["REMARK"]
        )
        output_lines.append(line)

    # TOTAL WEIGHT 항목 덮어쓰기
    total_label = "TOTAL WEIGHT(Kg) :"
    for i in range(len(ents) - 1):
        if ents[i][2].upper() == total_label.upper():
            ents[i + 1][3].dxf.text = f"{round(total_weight_sum, 1)}"
            break

    # TXT 저장
    with open(new_txt, "w", encoding="utf-8") as f:
        f.write("{:<4} {:<6} {:<30} {:<20} {:>8} {:>10} {:>10} {:<10} {:<}\n".format(
            "NO.", "QTY", "DESCRIPTION", "SIZE", "LENGTH", "UNIT", "TOTAL", "MAT'L", "REMARK"
        ))
        for line in output_lines:
            f.write(line + "\n")
        f.write(f"\nTOTAL WEIGHT(Kg) : {round(total_weight_sum, 1)}\n")

    # DXF 저장
    doc.saveas(new_dxf)

    print(f"[완료] {dxf_path} → {new_dxf}, {new_txt} 저장 (총 {len(output_lines)}행, {round(total_weight_sum, 1)} Kg)")

def main():
    dxf_files = [f for f in os.listdir() if f.lower().endswith(".dxf")]
    if not dxf_files:
        print("DXF 파일이 현재 폴더에 없습니다.")
        return

    for dxf_file in dxf_files:
        try:
            process_dxf_file(dxf_file)
        except Exception as e:
            print(f"[오류] {dxf_file}: {e}")

if __name__ == "__main__":
    main()
