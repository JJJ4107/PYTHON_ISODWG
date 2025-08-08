import os
import ezdxf
import csv
from datetime import datetime

def find_text_near(entities, target_x, target_y, tolerance=1.0):
    for e in entities:
        if not hasattr(e.dxf, 'text') or not hasattr(e.dxf, 'insert'):
            continue
        x, y = e.dxf.insert.x, e.dxf.insert.y
        if abs(x - target_x) <= tolerance and abs(y - target_y) <= tolerance:
            return e.dxf.text.strip()
    return ''

def find_text_in_box(entities, x_min, x_max, y_min, y_max):
    texts = []
    for e in entities:
        if not hasattr(e.dxf, 'text') or not hasattr(e.dxf, 'insert'):
            continue
        x, y = e.dxf.insert.x, e.dxf.insert.y
        if x_min <= x <= x_max and y_min <= y <= y_max:
            texts.append((y, e.dxf.text.strip()))
    texts.sort(reverse=True)  # Y값 기준 내림차순
    return ' '.join([t[1] for t in texts[:2]])

def extract_latest_date_text_in_box(entities, x_min, x_max, y_min, y_max):
    candidates = []
    for e in entities:
        if not hasattr(e.dxf, 'text') or not hasattr(e.dxf, 'insert'):
            continue
        x, y = e.dxf.insert.x, e.dxf.insert.y
        if x_min <= x <= x_max and y_min <= y <= y_max:
            candidates.append((y, e.dxf.text.strip()))
    if not candidates:
        return ''
    latest = max(candidates, key=lambda item: item[0])[1]
    return convert_date_format(latest)

def convert_date_format(text):
    try:
        dt = datetime.strptime(text.strip(), "%d-%b-%Y")
        return dt.strftime("%Y.%m.%d")
    except ValueError:
        return text  # 날짜 형식 아니면 그대로 반환

def extract_from_dxf(filepath):
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()
    texts = [e for e in msp if e.dxftype() in ['TEXT', 'MTEXT']]

    result = {
        'DWG NO': find_text_near(texts, 696.5453, 18.6671),
        'LINE NO': find_text_near(texts, 43.1000, 58.5000),
        'DESC': find_text_in_box(texts, 730, 830, 37, 60),  # TITLE을 DESC로 사용
        'BEP': find_text_near(texts, 413.6000, 58.5000),
        'DATE': extract_latest_date_text_in_box(texts, 670, 692, 169, 200),
    }

    return result

def main():
    output_rows = []
    header = ["DWG NO", "LINE NO", "DESC", "BEP", "DATE"]
    output_rows.append(header)

    for filename in os.listdir():
        if filename.lower().endswith('.dxf'):
            print(f"Processing {filename}...")
            try:
                data = extract_from_dxf(filename)
                output_rows.append([
                    data['DWG NO'],
                    data['LINE NO'],
                    data['DESC'],
                    data['BEP'],
                    data['DATE']
                ])
            except Exception as e:
                output_rows.append([f"ERROR in {filename}", "", "", "", str(e)])

    # CSV로 저장
    with open("LIST.CSV", "w", newline="", encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerows(output_rows)

    print("✅ LIST.CSV 저장 완료")

if __name__ == "__main__":
    main()
