import os
import csv
import ezdxf

def is_float(s):
    try:
        float(s.replace(',', '').replace('−', '-').strip())
        return True
    except:
        return False

def get_right_texts(text_entity, texts, count=3, y_tolerance=3.0):
    x0, y0 = text_entity.dxf.insert.x
    y0 = text_entity.dxf.insert.y
    right_texts = [t for t in texts if abs(t.dxf.insert.y - y0) < y_tolerance and t.dxf.insert.x > x0]
    right_texts.sort(key=lambda t: t.dxf.insert.x)
    return right_texts[:count]

def format_float(val):
    try:
        return f"{round(float(val.replace(',', '').replace('−', '-')), 1):.1f}"
    except:
        return ""

def overwrite_text(entity, value):
    if entity and value and value != "0.0":
        print(f"→ 덮어쓰기: '{entity.dxf.text}' → '{value}' at {entity.dxf.insert}")
        entity.dxf.text = value

def process_dxf_file(dxf_path, csv_path):
    try:
        doc = ezdxf.readfile(dxf_path)
    except Exception as e:
        print(f"[오류] DXF 파일 열기 실패: {e}")
        return

    msp = doc.modelspace()
    texts = list(msp.query('TEXT'))
    nodeno = None

    for text in texts:
        if "NODE NO" in text.plain_text().strip().upper():
            base_x, base_y = text.dxf.insert.x, text.dxf.insert.y
            right_texts = get_right_texts(text, texts, 1)
            if right_texts:
                nodeno = right_texts[0].plain_text().strip()
                print(f"\n📄 파일: {os.path.basename(dxf_path)}")
                print(f"🔍 NODE NO: {nodeno} at ({base_x:.2f}, {base_y:.2f})")
            break

    if not nodeno:
        print("⚠ NODE NO 미발견")
        return

    # 방향 텍스트와 오른쪽 값 매핑
    dir_map = {'+X': 'E', '-X': 'W', '+Y': 'N', '-Y': 'S', '+Z': 'U', '-Z': 'D'}
    direction_values = {}

    for text in texts:
        tval = text.plain_text().strip().upper()
        if tval in dir_map:
            dir_key = dir_map[tval]
            right_vals = get_right_texts(text, texts, 3, y_tolerance=3.0)
            for i, rt in enumerate(right_vals):
                direction_values[f"{dir_key}{i}"] = rt

    # 화면에 E1~D1, E2~D2 현재 값 표시
    print("\n📌 현재 방향 값 (DXF 기준):")
    for key in ['W1','E1','S1','N1','D1','U1','W2','E2','S2','N2','D2','U2']:
        if key in direction_values:
            val = direction_values[key].plain_text().strip()
            pos = direction_values[key].dxf.insert
            print(f" - {key}: '{val}' at ({pos.x:.2f}, {pos.y:.2f})")
        else:
            print(f" - {key}: ❌ 없음")

    # CSV 처리
    try:
        with open(csv_path, encoding='utf-8-sig') as f:
            rows = list(csv.reader(f))
    except Exception as e:
        print(f"[오류] CSV 열기 실패: {e}")
        return

    matched = False
    ope_done = False
    max_done = False

    for i, row in enumerate(rows):
        if not row:
            continue
        if row[0].strip() == nodeno:
            matched = True
            print(f"\n📋 NODE NO 일치 → A1 = {row[0].strip()}")

            for j in range(i + 1, len(rows)):
                r = rows[j]
                if len(r) < 12:
                    continue

                A = [r[k].strip() if k < len(r) else '' for k in range(11)]
                print("\n🧾 A1~A11 한 줄 출력:")
                print(" | ".join(A))

                upper_fields = [x.upper() for x in A]

                if not ope_done and any('OPE' in x for x in upper_fields):
                    print("→ OPE 처리 시작")
                    a9, a10, a11 = format_float(r[8]), format_float(r[9]), format_float(r[10])

                    overwrite_text(direction_values.get("W2") if r[8].strip().startswith('-') else direction_values.get("E2"), a9)
                    overwrite_text(direction_values.get("S2") if r[9].strip().startswith('-') else direction_values.get("N2"), a10)
                    overwrite_text(direction_values.get("D2") if r[10].strip().startswith('-') else direction_values.get("U2"), a11)

                    ope_done = True

                elif not max_done and any('MAX' in x for x in upper_fields):
                    print("→ MAX 처리 시작")
                    a3, a4, a5 = format_float(r[2]), format_float(r[3]), format_float(r[4])

                    overwrite_text(direction_values.get("W1") if r[2].strip().startswith('-') else direction_values.get("E1"), a3)
                    overwrite_text(direction_values.get("S1") if r[3].strip().startswith('-') else direction_values.get("N1"), a4)
                    overwrite_text(direction_values.get("D1") if r[4].strip().startswith('-') else direction_values.get("U1"), a5)

                    max_done = True

                if ope_done and max_done:
                    break
            break

    if not matched:
        print(f"⚠ NODENO {nodeno}와 일치하는 A1을 찾을 수 없음")
        return

    out_path = dxf_path.replace("-A", "")
    doc.saveas(out_path)
    print(f"💾 저장 완료: {out_path}")

