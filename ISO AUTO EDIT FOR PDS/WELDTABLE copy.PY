import os
import re
import ezdxf
import tkinter as tk
from tkinter import filedialog
from math import hypot

def get_selected_dxf_files():
    root = tk.Tk()
    root.withdraw()
    return list(filedialog.askopenfilenames(
        title="DXF 파일을 선택하세요",
        filetypes=[("DXF files", "*.dxf")]
    ))

def extract_text_entities(doc):
    msp = doc.modelspace()
    return [e for e in msp if e.dxftype() == 'TEXT']

def get_texts_by_position(entities):
    texts = []
    for e in entities:
        pos = e.dxf.insert
        texts.append((e.plain_text().strip(), round(pos.x, 2), round(pos.y, 2), e))
    return sorted(texts, key=lambda t: (-t[2], t[1]))

def extract_bore_from_size(size_text):
    match = re.search(r'(\d+)', size_text)
    return int(match.group(1)) if match else 100

def find_header_positions(all_texts):
    headers = {}
    for text, x, y, _ in all_texts:
        txt = text.strip().upper()
        for key in ['NO', 'DN', 'TYPE', '/FLD']:
            if key in txt:
                headers[key] = (round(x, 2), round(y, 2))
    return headers

def modify_fld_column(doc, all_texts, headers):
    if 'NO' not in headers or '/FLD' not in headers:
        return
    msp = doc.modelspace()
    no_x, no_y = headers['NO']
    fld_x, fld_y = headers['/FLD']
    y_positions = sorted(
        set(t[2] for t in all_texts if abs(t[1] - no_x) < 1 and t[2] < no_y and t[0].strip()),
        reverse=True
    )
    for y in y_positions:
        fld_texts = [t for t in all_texts if abs(t[1] - fld_x) < 1 and abs(t[2] - y) < 0.5]
        for text, x, y2, e in fld_texts:
            val = text.strip().upper()
            if val in ['F', 'S']:
                new_val = val + 'W'
                try: msp.delete_entity(e)
                except: continue
                msp.add_text(new_val, dxfattribs={'height': 2.5, 'insert': (x + 5, y2)})

def modify_table(doc, all_texts, bore_value, headers):
    if 'NO' not in headers:
        return
    msp = doc.modelspace()
    no_x, no_y = headers['NO']
    dn_x = headers.get('DN', (None, None))[0]
    type_x = headers.get('TYPE', (None, None))[0]
    header_y = no_y
    y_positions = sorted(
        set(t[2] for t in all_texts if abs(t[1] - no_x) < 1 and t[2] < header_y and t[0].strip()),
        reverse=True
    )
    for y in y_positions:
        if dn_x is not None:
            dn_texts = [t for t in all_texts if abs(t[1] - dn_x) < 1 and abs(t[2] - y) < 0.5]
            for t in dn_texts:
                try: msp.delete_entity(t[3])
                except: continue
            msp.add_text(str(bore_value), dxfattribs={'height': 2.5, 'insert': (dn_x + 5, y)})
        if type_x is not None:
            type_texts = [t for t in all_texts if abs(t[1] - type_x) < 1 and abs(t[2] - y) < 0.5]
            for t in type_texts:
                try: msp.delete_entity(t[3])
                except: continue
            type_str = "  BW" if bore_value >= 65 else "  SW"
            msp.add_text(type_str, dxfattribs={'height': 2.5, 'insert': (type_x + 3, y)})

def get_table_bounds(headers, all_texts):
    xs = [headers[k][0] for k in ['NO', '/FLD', 'DN', 'TYPE'] if k in headers]
    min_x = min(xs) - 20
    max_x = max(xs) + 10
    no_x, no_y = headers['NO']
    ys = [t[2] for t in all_texts if abs(t[1] - no_x) < 1 and t[2] < no_y and re.match(r'\d+', t[0].strip())]
    min_y = min(ys) - 10 if ys else no_y - 100
    max_y = no_y + 15
    return min_x, max_x, min_y, max_y

def stretch_entities(doc, bounds):
    min_x, max_x, min_y, max_y = bounds
    msp = doc.modelspace()
    for e in list(msp):
        if not hasattr(e, "dxf"):
            continue
        try:
            if e.dxftype() in ['TEXT', 'MTEXT']:
                p = e.dxf.insert
                if min_x <= p.x <= max_x and min_y <= p.y <= max_y:
                    e.dxf.insert = (p.x + 25, p.y)
            elif e.dxftype() == 'LWPOLYLINE':
                new_points = []
                for x, y, *rest in e.get_points():
                    if min_x <= x <= max_x and min_y <= y <= max_y:
                        x += 25
                    new_points.append((x, y, *rest))
                e.set_points(new_points)
            elif e.dxftype() == 'POLYLINE':
                for v in e.vertices:
                    loc = v.dxf.location
                    if min_x <= loc.x <= max_x and min_y <= loc.y <= max_y:
                        v.dxf.location = (loc.x + 25, loc.y)
        except Exception:
            continue

def find_bore_from_fabrication_zone(all_texts):
    fab_pos = None
    for text, x, y, _ in all_texts:
        if "FABRICATION MATERIAL" in text.upper():
            fab_pos = (x, y)
            break
    if not fab_pos:
        print("⚠ 'FABRICATION MATERIALS' 텍스트를 찾을 수 없습니다.")
        return None
    size_candidates = [
        (text, x, y) for text, x, y, _ in all_texts
        if "SIZE" in text.upper() and hypot(x - fab_pos[0], y - fab_pos[1]) <= 100
    ]
    if not size_candidates:
        print("⚠ SIZE 텍스트가 'FABRICATION MATERIALS' 반경 100mm 내에 없습니다.")
        return None
    size_text, size_x, size_y = sorted(size_candidates, key=lambda t: hypot(t[1] - fab_pos[0], t[2] - fab_pos[1]))[0]
    below_texts = [t for t in all_texts if abs(t[1] - size_x) < 1 and t[2] < size_y]
    if not below_texts:
        print("⚠ SIZE 아래 텍스트가 없습니다.")
        return None
    return sorted(below_texts, key=lambda t: size_y - t[2])[0][0]

def process_dxf_file(filepath):
    print(f"\n📂 Processing: {os.path.basename(filepath)}")
    doc = ezdxf.readfile(filepath)
    all_texts = get_texts_by_position(extract_text_entities(doc))

    size_text_value = find_bore_from_fabrication_zone(all_texts)
    if not size_text_value:
        print("❌ BORE 값을 추출할 수 없습니다.")
        return
    bore_value = extract_bore_from_size(size_text_value)
    print(f"✅ BORE 값 추출됨: {bore_value}")

    headers = find_header_positions(all_texts)
    modify_table(doc, all_texts, bore_value, headers)
    modify_fld_column(doc, all_texts, headers)
    bounds = get_table_bounds(headers, all_texts)
    stretch_entities(doc, bounds)

    new_filename = os.path.splitext(filepath)[0] + "_wt.dxf"
    doc.saveas(new_filename)
    print(f"💾 저장 완료: {os.path.basename(new_filename)}")

def main():
    dxf_files = get_selected_dxf_files()
    if not dxf_files:
        print("❌ DXF 파일이 선택되지 않았습니다.")
        return
    for dxf in dxf_files:
        try:
            process_dxf_file(dxf)
        except Exception as e:
            print(f"❌ 오류 발생: {dxf} / {e}")

if __name__ == "__main__":
    main()
