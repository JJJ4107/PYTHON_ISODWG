import os
import re
import ezdxf

def get_all_dxf_files(folder='.'):
    return [f for f in os.listdir(folder) if f.lower().endswith('.dxf')]

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
    if match:
        return int(match.group(1))
    return 100

def find_header_positions(all_texts):
    headers = {}
    for text, x, y, _ in all_texts:
        txt = text.strip().upper()
        for key in ['NO', 'DN', 'TYPE']:
            if txt == key:
                headers[key] = (round(x, 2), round(y, 2))
    return headers

def modify_table(doc, all_texts, bore_value, headers):
    if 'NO' not in headers:
        return

    msp = doc.modelspace()
    no_x, no_y = headers['NO']
    dn_x = headers.get('DN', (None, None))[0]
    type_x = headers.get('TYPE', (None, None))[0]
    header_y = no_y

    y_positions = sorted(
        set([t[2] for t in all_texts if abs(t[1] - no_x) < 1 and t[2] < header_y and t[0].strip()]),
        reverse=True
    )

    for y in y_positions:
        if dn_x is not None:
            dn_texts = [t for t in all_texts if abs(t[1] - dn_x) < 1 and abs(t[2] - y) < 0.5]
            for t in dn_texts:
                msp.delete_entity(t[3])
            dn_string = str(bore_value)
            msp.add_text(dn_string, dxfattribs={'height': 2.5, 'insert': (dn_x + 5, y)})  # 🔧 여기서 +5로 변경

        if type_x is not None:
            type_texts = [t for t in all_texts if abs(t[1] - type_x) < 1 and abs(t[2] - y) < 0.5]
            for t in type_texts:
                msp.delete_entity(t[3])
            type_value = "BW" if bore_value >= 65 else "SW"
            type_string = f"  {type_value}"
            msp.add_text(type_string, dxfattribs={'height': 2.5, 'insert': (type_x + 3, y)})

def process_dxf_file(filepath):
    print(f"\n📂 Processing: {filepath}")
    doc = ezdxf.readfile(filepath)
    all_texts = get_texts_by_position(extract_text_entities(doc))

    size_x = None
    header_y = None

    for text, x, y, _ in all_texts:
        if text.strip().upper() == "SIZE":
            size_x = x
            header_y = y
            break

    if size_x is None or header_y is None:
        print("⚠ SIZE 헤더를 찾지 못했습니다.")
        return

    candidates = [t for t in all_texts if abs(t[1] - size_x) < 1 and t[2] < header_y]
    if not candidates:
        print("⚠ SIZE 아래 텍스트가 없습니다.")
        return

    below_size_text = sorted(candidates, key=lambda t: header_y - t[2])[0]
    size_text_value = below_size_text[0]
    bore_value = extract_bore_from_size(size_text_value)

    print(f"✅ BORE 값 추출됨: {bore_value}")

    headers = find_header_positions(all_texts)
    modify_table(doc, all_texts, bore_value, headers)

    new_filename = filepath[:-4] + "-W.dxf"
    doc.saveas(new_filename)
    print(f"💾 저장 완료: {new_filename}")

def main():
    dxf_files = get_all_dxf_files()
    if not dxf_files:
        print("❌ DXF 파일이 없습니다.")
        return

    for dxf in dxf_files:
        try:
            process_dxf_file(dxf)
        except Exception as e:
            print(f"❌ 오류 발생: {dxf} / {e}")

if __name__ == "__main__":
    main()
