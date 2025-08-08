import os
import re
import ezdxf
from collections import defaultdict

NODE_NO_PAT = re.compile(r".*NODE\s*NO.*", re.I)
SPRING_COLS = ["NODE", "QTY", "FIG", "SIZE", "VMOVEMENT", "HLOAD", "CLOAD", "ILOAD", "RATE", "HMOVEMENT"]

def find_closest_text_right(base_point, texts, limit=3):
    x0 = base_point.x
    y0 = base_point.y
    found = []
    for text in texts:
        x = text.dxf.insert.x
        y = text.dxf.insert.y
        if x > x0 and abs(y - y0) < 5:
            found.append((x, text))
    found.sort(key=lambda t: t[0])
    return [t[1] for t in found[:limit]]

def load_spring_data(nodeno, csv_path):
    reading = False
    with open(csv_path, encoding='utf-8-sig') as f:
        for line in f:
            line = line.strip()
            if not reading:
                if '--------+' in line:
                    reading = True
                    print("\n[SPRINGDATA.csv 읽기 시작]")
            elif line:
                tokens = line.split()
                if len(tokens) != 10:
                    continue
                try:
                    int(tokens[0])
                except ValueError:
                    continue
                data = dict(zip(SPRING_COLS, tokens))
                print("→ SPRING DATA:", data)
                if data["NODE"] == nodeno:
                    return data
    return None

def find_texts_below(base_point, texts, count=10):
    x0 = base_point.x
    y0 = base_point.y
    found = []
    for text in texts:
        x = text.dxf.insert.x
        y = text.dxf.insert.y
        if y < y0 and abs(x - x0) < 50:
            found.append((y, text))
    found.sort(reverse=True)
    return [t[1] for t in found[:count]]

def round_direction_texts_to_int(direction_vars):
    for key in ["E1", "W1", "N1", "S1", "U1", "D1"]:
        if key in direction_vars:
            text_obj = direction_vars[key]
            try:
                val = float(text_obj.plain_text().strip())
                rounded = int(round(val, 1))
                text_obj.dxf.text = str(rounded)
                print(f"✓ {key} 반올림 적용: {val} → {rounded}")
            except ValueError:
                print(f"⚠️ {key} 값 숫자 아님: {text_obj.plain_text()}")

def update_dxf_file(filepath, springdata_path):
    print(f"\n▶ 파일 처리 시작: {filepath}")
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()
    texts = list(msp.query('TEXT'))

    nodeno = None
    base_point = None
    for text in texts:
        if NODE_NO_PAT.fullmatch(text.plain_text().strip().upper()):
            right_texts = find_closest_text_right(text.dxf.insert, texts)
            if right_texts and right_texts[0].plain_text().strip().isdigit():
                nodeno = right_texts[0].plain_text().strip()
                base_point = text.dxf.insert
                print(f"✓ NODE NO = {nodeno}")
            else:
                print("✗ NODE NO 없음")
            break

    if not nodeno:
        return

    spring_data = load_spring_data(nodeno, springdata_path)
    if not spring_data:
        print("✗ SPRING DATA 없음")
        return

    def replace_text(tag, new_value, qty):
        print(f"[디버깅] {tag} 입력값: {new_value}, 수량: {qty}")
        for text in texts:
            if text.plain_text().strip().upper() == tag:
                x, y = text.dxf.insert.x, text.dxf.insert.y
                tgt_texts = find_closest_text_right(text.dxf.insert, texts)
                new_text = f"{int(float(new_value))}x{int(qty)}" if int(qty) >= 2 else f"{int(float(new_value))}"
                if tgt_texts:
                    print(f"→ {tag} 기존 텍스트: {tgt_texts[0].plain_text()} → {new_text}")
                    tgt_texts[0].dxf.text = new_text
                else:
                    msp.add_text(new_text, dxfattribs={'height': 3.5}).dxf.insert = (x + 5, y)
                    print(f"+ {tag} 추가 → {new_text}")
                break

    replace_text("HOT LOAD", spring_data["HLOAD"], spring_data["QTY"])
    replace_text("COLD LOAD", spring_data["CLOAD"], spring_data["QTY"])

    direction_vars = {}
    below_texts = find_texts_below(base_point, texts, count=10)

    for line_text in below_texts:
        right_texts = find_closest_text_right(line_text.dxf.insert, texts, limit=3)
        if len(right_texts) >= 3:
            dir_key = right_texts[0].plain_text().strip().upper()
            if dir_key:
                key1 = f"{dir_key[0]}1"
                key2 = f"{dir_key[0]}2"
                direction_vars[key1] = right_texts[1]
                direction_vars[key2] = right_texts[2]
                print(f"[디버깅] {dir_key}: {key1}={right_texts[1].plain_text()}, {key2}={right_texts[2].plain_text()}")

    try:
        qty = int(float(spring_data["QTY"]))
        cload = float(str(spring_data["CLOAD"]).split('x')[0])
        vm = float(spring_data["VMOVEMENT"])
        d1_val = round(abs(qty * cload), 1)
        d2_val = round(abs(vm), 1)

        if d1_val > 0:
            if vm < 0 and "D1" in direction_vars:
                direction_vars["D1"].dxf.text = str(d1_val)
                print(f"✓ D1 = {direction_vars['D1'].plain_text()} → {d1_val}")
            elif vm >= 0 and "U1" in direction_vars:
                direction_vars["U1"].dxf.text = str(d1_val)
                print(f"✓ U1 = {direction_vars['U1'].plain_text()} → {d1_val}")

        if d2_val > 0:
            if vm < 0 and "D2" in direction_vars:
                direction_vars["D2"].dxf.text = str(d2_val)
                print(f"✓ D2 = {direction_vars['D2'].plain_text()} → {d2_val}")
            elif vm >= 0 and "U2" in direction_vars:
                direction_vars["U2"].dxf.text = str(d2_val)
                print(f"✓ U2 = {direction_vars['U2'].plain_text()} → {d2_val}")

        # 추가 요청된 반올림 처리
        round_direction_texts_to_int(direction_vars)

    except Exception as e:
        print(f"⚠️ 계산 오류 발생: {e}")

    newname = os.path.basename(filepath).replace("-A", "")
    newpath = os.path.join(os.path.dirname(filepath), newname)
    doc.saveas(newpath)
    print(f"📁 저장 완료 → {newpath}")

def process_all_dxf_files():
    current = os.getcwd()
    springdata_file = os.path.join(current, "SPRINGDATA.csv")
    for f in os.listdir(current):
        if f.lower().endswith(".dxf"):
            update_dxf_file(os.path.join(current, f), springdata_file)

process_all_dxf_files()

# ... (기존 코드 상단 동일 - 생략)
def apply_loaddata_values(nodeno, direction_vars, loaddata_path):
    if not os.path.exists(loaddata_path):
        print("✗ LOADDATA.csv 파일이 없습니다.")
        return

    with open(loaddata_path, encoding="utf-8-sig") as f:
        lines = [line.strip() for line in f if line.strip()]
        matched = False

        for i, line in enumerate(lines):
            row = [x.strip() for x in line.split(",")]

            if not matched:
                if row[0] == nodeno:
                    matched = True
                    print(f"\n[LOADDATA.csv] NODE {nodeno} → 처리 시작")
                continue

            if matched:
                if len(row) < 12:
                    continue

                label = row[1].upper()

                try:
                    if "(OPE)" in label:
                        a9 = float(row[8])
                        a10 = float(row[9])
                        a11 = float(row[10])

                        if a9 > 0 and "E2" in direction_vars:
                            direction_vars["E2"].dxf.text = f"{round(abs(a9), 1)}"
                        elif a9 < 0 and "W2" in direction_vars:
                            direction_vars["W2"].dxf.text = f"{round(abs(a9), 1)}"

                        if a10 > 0 and "N2" in direction_vars:
                            direction_vars["N2"].dxf.text = f"{round(abs(a10), 1)}"
                        elif a10 < 0 and "S2" in direction_vars:
                            direction_vars["S2"].dxf.text = f"{round(abs(a10), 1)}"

                        if a11 > 0 and "U2" in direction_vars:
                            direction_vars["U2"].dxf.text = f"{round(abs(a11), 1)}"
                        elif a11 < 0 and "D2" in direction_vars:
                            direction_vars["D2"].dxf.text = f"{round(abs(a11), 1)}"

                        print("✓ (OPE) 항목 처리 완료")

                    elif "MAX" in label:
                        a3 = float(row[2])
                        a4 = float(row[3])
                        a5 = float(row[4])

                        if a3 > 0 and "E1" in direction_vars:
                            direction_vars["E1"].dxf.text = f"{round(abs(a3), 1)}"
                        elif a3 < 0 and "W1" in direction_vars:
                            direction_vars["W1"].dxf.text = f"{round(abs(a3), 1)}"

                        if a4 > 0 and "N1" in direction_vars:
                            direction_vars["N1"].dxf.text = f"{round(abs(a4), 1)}"
                        elif a4 < 0 and "S1" in direction_vars:
                            direction_vars["S1"].dxf.text = f"{round(abs(a4), 1)}"

                        if a5 > 0 and "U1" in direction_vars:
                            direction_vars["U1"].dxf.text = f"{round(abs(a5), 1)}"
                        elif a5 < 0 and "D1" in direction_vars:
                            direction_vars["D1"].dxf.text = f"{round(abs(a5), 1)}"

                        print("✓ (MAX) 항목 처리 완료")
                        break  # MAX까지 처리했으면 종료

                except Exception as e:
                    print(f"⚠️ LOADDATA 파싱 오류: {e}")


# ... (기존 update_dxf_file 안에 아래 내용 추가)

    # LOADDATA.csv 경로 정의 및 처리
    loaddata_path = os.path.join(os.getcwd(), "LOADDATA.csv")
    apply_loaddata_values(nodeno, direction_vars, loaddata_path)

# ... (나머지 기존 함수들 동일, 예: process_all_dxf_files, main 등)


