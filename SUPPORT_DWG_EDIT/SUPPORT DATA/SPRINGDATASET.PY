import csv
import os
import ezdxf
from pathlib import Path

def is_integer_string(text):
    try:
        int(text.strip().lstrip('-'))
        return True
    except ValueError:
        return False

def is_float_string(text):
    try:
        float(text.strip().replace(',', '').replace('-', ''))
        return True
    except ValueError:
        return False

def find_closest_texts_right_any_y(base_point, texts, count=2):
    candidates = [t for t in texts if t.dxf.insert.x > base_point.x and is_float_string(t.plain_text())]
    return sorted(candidates, key=lambda t: (abs(t.dxf.insert.y - base_point.y), t.dxf.insert.x))[:count]

def extract_node_no(texts):
    for text in texts:
        if "NODE NO" in text.plain_text().strip().upper():
            base_point = text.dxf.insert
            right_texts = find_closest_texts_right_any_y(base_point, texts, count=1)
            for rt in right_texts:
                rt_text = rt.plain_text().strip()
                print(f"➡ 오른쪽 텍스트 검사: '{rt_text}'")
                if is_integer_string(rt_text):
                    return rt_text
    return ""

def find_direction_texts(texts):
    direction_map = {
        "EAST": ("E1", "E2"), "WEST": ("W1", "W2"),
        "NORTH": ("N1", "N2"), "SOUTH": ("S1", "S2"),
        "UP": ("U1", "U2"), "DOWN": ("D1", "D2")
    }
    found = {}
    for text in texts:
        dir_label = text.plain_text().strip().upper()
        if dir_label in direction_map:
            right_texts = find_closest_texts_right_any_y(text.dxf.insert, texts, count=2)
            key1, key2 = direction_map[dir_label]
            if len(right_texts) >= 2:
                found[key1] = right_texts[0]
                found[key2] = right_texts[1]
                print(f"[방향] {key1}: 값 = '{right_texts[0].plain_text().strip()}', 위치 = {right_texts[0].dxf.insert}")
                print(f"[방향] {key2}: 값 = '{right_texts[1].plain_text().strip()}', 위치 = {right_texts[1].dxf.insert}")
            else:
                print(f"[경고] {dir_label} 방향에서 충분한 텍스트를 찾지 못했습니다.")
        else:
            print(f"[스킵] 인식되지 않는 방향 텍스트: {dir_label}")
    return found

def overwrite_text(text_entity, new_text):
    if new_text:
        print(f"[갱신] '{text_entity.plain_text().strip()}' → '{new_text}' at {text_entity.dxf.insert}")
        text_entity.dxf.text = new_text

def format_value_float(val):
    try:
        val = str(val).replace('-', '').strip()
        return f"{round(abs(float(val)), 1):.1f}"
    except:
        return ""

def format_value_int(val):
    try:
        val = str(val).replace('-', '').strip()
        return str(int(round(abs(float(val)))))
    except:
        return ""

def to_int(value):
    try:
        return int(str(value).strip().lstrip('0'))
    except:
        return None

def process_dxf_with_csv(dxf_path, csv_path):
    try:
        doc = ezdxf.readfile(dxf_path)
    except Exception as e:
        print(f"[오류] DXF 파일 열기 실패: {dxf_path} → {e}")
        return

    msp = doc.modelspace()
    texts = list(msp.query('TEXT'))
    node_no = extract_node_no(texts)
    if not node_no:
        print(f"[무시됨] {dxf_path}: NODE NO. not found.")
        return

    print(f"\n🔍 DXF 파일: {dxf_path}")
    print(f"🔍 추출된 NODE NO: {node_no}")

    node_no_int = to_int(node_no)
    if node_no_int is None:
        print(f"[오류] DXF NODE NO. 값을 숫자로 변환할 수 없습니다: {node_no}")
        return

    direction_texts = find_direction_texts(texts)

    try:
        with open(csv_path, newline='', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            rows = list(reader)
    except Exception as e:
        print(f"[오류] CSV 파일 열기 실패: {csv_path} → {e}")
        return

    matched = False
    ope_processed = False
    for i, row in enumerate(rows):
        if not row:
            continue
        a1_raw = row[0].strip()
        a1_int = to_int(a1_raw)
        if a1_int == node_no_int:
            matched = True
            i += 1
            while i < len(rows):
                row = rows[i]
                if not row or len(row) < 12:
                    i += 1
                    continue
                a2 = row[1].strip().upper()
                if 'OPE' in a2 and not ope_processed:
                    row[1] = "OPE"
                    print(f"📋 OPE 데이터: A1~A11 = {row[:11]}")
                    ope_processed = True
                    val9 = format_value_float(row[8])
                    val10 = format_value_float(row[9])
                    val11 = format_value_float(row[10])
                    if row[8].strip().startswith('-'):
                        if 'W2' in direction_texts: overwrite_text(direction_texts['W2'], val9)
                    elif val9:
                        if 'E2' in direction_texts: overwrite_text(direction_texts['E2'], val9)
                    if row[9].strip().startswith('-'):
                        if 'S2' in direction_texts: overwrite_text(direction_texts['S2'], val10)
                    elif val10:
                        if 'N2' in direction_texts: overwrite_text(direction_texts['N2'], val10)
                    if row[10].strip().startswith('-'):
                        if 'D2' in direction_texts: overwrite_text(direction_texts['D2'], val11)
                    elif val11:
                        if 'U2' in direction_texts: overwrite_text(direction_texts['U2'], val11)
                if 'MAX' in a2:
                    val3 = format_value_int(row[2])
                    val4 = format_value_int(row[3])
                    val5 = format_value_int(row[4])
                    if row[2].strip().startswith('-'):
                        if 'W1' in direction_texts: overwrite_text(direction_texts['W1'], val3)
                    elif val3:
                        if 'E1' in direction_texts: overwrite_text(direction_texts['E1'], val3)
                    if row[3].strip().startswith('-'):
                        if 'S1' in direction_texts: overwrite_text(direction_texts['S1'], val4)
                    elif val4:
                        if 'N1' in direction_texts: overwrite_text(direction_texts['N1'], val4)
                    if row[4].strip().startswith('-'):
                        if 'D1' in direction_texts: overwrite_text(direction_texts['D1'], val5)
                    elif val5:
                        if 'U1' in direction_texts: overwrite_text(direction_texts['U1'], val5)
                    break
                i += 1
            break

    if not matched:
        print(f"[⚠️ 불일치] {dxf_path}: NODE NO. '{node_no_int}' 와 일치하는 A1 값을 찾을 수 없습니다.")
        return

    stem = Path(dxf_path).stem.replace("-A", "")
    out_path = Path(dxf_path).with_name(stem + ".dxf")
    try:
        doc.saveas(out_path)
        print(f"✅ 저장 완료 (덮어쓰기): {out_path}")
    except Exception as e:
        print(f"[오류] 저장 실패: {out_path} → {e}")

if __name__ == "__main__":
    csv_path = "LOADDATA.CSV"
    for file in os.listdir():
        if file.lower().endswith(".dxf"):
            process_dxf_with_csv(file, csv_path)
