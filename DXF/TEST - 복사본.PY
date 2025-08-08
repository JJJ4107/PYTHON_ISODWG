"""
필수: pip install ezdxf
"""
import os, re, ezdxf

DXF_FILE  = "TEST.DXF"
TXT_FILE  = "TEST1.TXT"
NEW_DXF   = "TEST1.DXF"

DENSITY_STEEL = 7.85e-6   # kg / mm³

FIXED_WT   = {"DN150xS/40": 9.9, "PL10x250x250": 4.9}
LINEAR_WT  = {"H150x150x7x10": 0.0315, "C150x75x6.5x10": 18.6 / 1000}
PLATE_PAT  = re.compile(r"PL(\d+)[xX](\d+)[xX](\d+)", re.I)

def calc_unit_weight(size_txt: str, length_mm: float) -> float:
    s = size_txt.strip()
    if s in FIXED_WT:
        return FIXED_WT[s]
    if s in LINEAR_WT:
        return LINEAR_WT[s] * length_mm
    m = PLATE_PAT.fullmatch(s)
    if m:
        t, w, l = map(float, m.groups())
        return round(t * w * l * DENSITY_STEEL, 2)
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

def main():
    if not os.path.exists(DXF_FILE):
        raise FileNotFoundError(f"{DXF_FILE} not found")

    doc = ezdxf.readfile(DXF_FILE)
    msp = doc.modelspace()

    # 모든 TEXT/MTEXT 수집 → (Y, X, TEXT, ENTITY)
    ents = []
    for e in msp:
        if e.dxftype() == "TEXT":
            ents.append((e.dxf.insert[1], e.dxf.insert[0], e.dxf.text.strip(), e))
        elif e.dxftype() == "MTEXT":
            ents.append((e.dxf.insert[1], e.dxf.insert[0], e.text.strip(), e))

    ents.sort(key=lambda t: (-t[0], t[1]))  # Y 내림, X 오름

    headers = ["Q'TY", "DESCRIPTION", "SIZE", "LENGTH", "UNIT", "TOTAL"]
    header_pos = {}
    for y, x, txt, _ in ents:
        if txt.upper() in headers:
            header_pos[txt.upper()] = (x, y)
        if len(header_pos) == 6:
            break
    if len(header_pos) < 6:
        raise RuntimeError("헤더 6개(Q'TY ~ TOTAL)를 모두 찾지 못했습니다")

    header_y   = list(header_pos.values())[0][1]
    col_order  = sorted(header_pos.items(), key=lambda kv: kv[1][0])
    col_names  = [c[0] for c in col_order]
    col_xpos   = [c[1][0] for c in col_order]

    rows_raw = group_rows(ents, header_y)
    output_lines = []

    unit_texts_to_update = []
    total_texts_to_update = []

    for row in rows_raw:
        cols = {h: "" for h in col_names}
        ents_map = {h: None for h in col_names}

        for x, txt, ent in row:
            nearest_idx = min(range(len(col_xpos)), key=lambda i: abs(x - col_xpos[i]))
            header = col_names[nearest_idx]
            cols[header] = txt
            ents_map[header] = ent if txt == '-' else ents_map[header]

        try:
            qty = int(float(cols["Q'TY"]))
        except ValueError:
            continue
        desc    = cols["DESCRIPTION"]
        size    = cols["SIZE"]
        try:
            length = int(float(cols["LENGTH"]))
        except ValueError:
            length = 0

        unit_wt = calc_unit_weight(size, length)
        total_wt = round(unit_wt * qty, 2)

        # DXF 수정 대상 저장
        if ents_map["UNIT"] and cols["UNIT"] == '-':
            ents_map["UNIT"].dxf.text = f"{unit_wt:.2f}"
            unit_texts_to_update.append(ents_map["UNIT"])

        if ents_map["TOTAL"] and cols["TOTAL"] == '-':
            ents_map["TOTAL"].dxf.text = f"{total_wt:.2f}"
            total_texts_to_update.append(ents_map["TOTAL"])

        cols["UNIT"] = f"{unit_wt:.2f}"
        cols["TOTAL"] = f"{total_wt:.2f}"

        line = "{:<6} {:<30} {:<20} {:>8} {:>10} {:>10}".format(
            qty, desc, size, length, cols["UNIT"], cols["TOTAL"]
        )
        output_lines.append(line)

    # TXT 파일 저장
    with open(TXT_FILE, "w", encoding="utf-8") as f:
        f.write("{:<6} {:<30} {:<20} {:>8} {:>10} {:>10}\n".format(
            "QTY", "DESCRIPTION", "SIZE", "LENGTH", "UNIT", "TOTAL"
        ))
        for line in output_lines:
            f.write(line + "\n")

    # DXF 저장
    if os.path.exists(NEW_DXF):
        os.remove(NEW_DXF)
    doc.saveas(NEW_DXF)

    print(f"[완료] {TXT_FILE} 및 {NEW_DXF} 생성 – 총 {len(output_lines)}행 처리됨")

if __name__ == "__main__":
    main()
