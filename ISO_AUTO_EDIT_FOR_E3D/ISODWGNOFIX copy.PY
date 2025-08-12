import os
import re
import ezdxf
import tkinter as tk
from tkinter import filedialog

def get_xy(e):
    try:
        if hasattr(e, 'dxf') and hasattr(e.dxf, 'insert'):
            ins = e.dxf.insert
            if hasattr(ins, 'x') and hasattr(ins, 'y'):
                return float(ins.x), float(ins.y)
            elif isinstance(ins, (tuple, list)) and len(ins) >= 2:
                return float(ins[0]), float(ins[1])
        elif hasattr(e, 'insert'):
            ins = e.insert
            if isinstance(ins, (tuple, list)) and len(ins) >= 2:
                return float(ins[0]), float(ins[1])
    except Exception:
        pass
    return 0.0, 0.0

def get_text(e):
    try:
        if hasattr(e, 'dxf') and hasattr(e.dxf, 'text'):
            return e.dxf.text.strip()
        elif hasattr(e, 'text'):
            return e.text.strip()
    except Exception:
        pass
    return ''

def set_text(e, value=None, color=None):
    try:
        if hasattr(e, 'dxf') and hasattr(e.dxf, 'text'):
            if value is not None:
                e.dxf.text = value
            if color is not None:
                e.dxf.color = color
        elif hasattr(e, 'text'):
            if value is not None:
                e.text = value
            if color is not None and hasattr(e, 'dxf'):
                e.dxf.color = color
    except Exception:
        pass

def filename_base(fname):
    base = os.path.basename(fname)
    name = os.path.splitext(base)[0]
    if '_' in name:
        return name.split('_')[0]
    else:
        return name

def find_special_below(msp, base_x, base_y, x_tol=4, y_tol=20, patt=None, color=None):
    candidates = []
    for e in msp.query('TEXT MTEXT'):
        txt = get_text(e)
        x, y = get_xy(e)
        ecolor = getattr(e.dxf, "color", 256)
        if abs(x-base_x) <= x_tol and (y < base_y) and (0 < base_y - y <= y_tol):
            if (patt is None or re.search(patt, txt, re.I)) and (color is None or ecolor == color):
                candidates.append((base_y - y, e))
    if not candidates:
        return []
    return [e for _, e in sorted(candidates, key=lambda t: t[0])]

def find_chain_below(msp, cont_e, cont_x, cont_y, x_tol=4, y_tol=20):
    chain = [(cont_e, get_text(cont_e), cont_x, cont_y)]
    last_x, last_y = cont_x, cont_y
    for _ in range(4):
        next_es = find_special_below(msp, last_x, last_y, x_tol=x_tol, y_tol=y_tol)
        if not next_es:
            break
        next_e = next_es[0]
        chain.append((next_e, get_text(next_e), *get_xy(next_e)))
        last_x, last_y = get_xy(next_e)
    return chain if len(chain) == 5 else None

# 파일 선택
root = tk.Tk()
root.withdraw()
file_paths = filedialog.askopenfilenames(
    title="DXF 도면 선택", filetypes=[("DXF files", "*.dxf")]
)
root.destroy()
if not file_paths:
    print("DXF 파일이 선택되지 않았습니다.")
    exit()

dxf_folder = os.path.dirname(file_paths[0])
ALLCHK = []

header = f"{'도면명':<28} | {'CONT':<16} | {'AFDNO':<16} | {'ADLNO':<16} | {'APOS':<28}"
print(header)
print("-" * len(header))

# 1. ALLCHK 구성
for path in file_paths:
    file_nx = filename_base(path)
    file = os.path.basename(path)
    full_path = os.path.join(dxf_folder, file)
    try:
        doc = ezdxf.readfile(full_path)
        msp = doc.modelspace()
    except Exception as e:
        print(f"{file} 읽기 오류: {e}")
        continue

    cont_entities = []
    for e in msp.query('TEXT MTEXT'):
        txt = get_text(e).upper()
        if (('CONT' in txt and '.' in txt) or
            ('CONN' in txt and '.' in txt)):
            cont_entities.append((e, txt, *get_xy(e)))
            try: e.dxf.color = 4  # CYAN
            except: pass

    if not cont_entities:
        print(f"{file_nx:<28} | {'[CONT 없음]':<16}")
        continue

    for cont_e, cont_txt, cont_x, cont_y in cont_entities:
        chain = find_chain_below(msp, cont_e, cont_x, cont_y)
        if not chain:
            print(f"{file_nx:<28} | [CONT 5개 미만 SKIP]")
            continue

        # AFDNO(색상 RED, YELLOW, BLUE 가능)
        afdno_es = find_special_below(msp, cont_x, cont_y, x_tol=4, y_tol=20, patt=r"(-|FMF)")
        for afdno_e in afdno_es:
            color = getattr(afdno_e.dxf, "color", 256)
            if color in (1, 2, 5):  # RED, YELLOW, BLUE
                afdno = get_text(afdno_e)
                afdno_x, afdno_y = get_xy(afdno_e)

                # ADLNO, E/W, S/N, FL/EL (색상 무관)
                adlno_es = find_special_below(msp, afdno_x, afdno_y, x_tol=4, y_tol=20, patt=r"(-|FMF)")
                adlno = get_text(adlno_es[0]) if adlno_es else ''
                epos_es = find_special_below(msp, afdno_x, afdno_y, x_tol=4, y_tol=20, patt=r"\b(E|W)\b")
                epos = get_text(epos_es[0]) if epos_es else ''
                npos_es = find_special_below(msp, get_xy(epos_es[0])[0], get_xy(epos_es[0])[1], x_tol=4, y_tol=20, patt=r"\b(S|N)\b") if epos_es else []
                npos = get_text(npos_es[0]) if npos_es else ''
                flpos_es = find_special_below(msp, get_xy(npos_es[0])[0], get_xy(npos_es[0])[1], x_tol=4, y_tol=20, patt=r"(FL|EL)") if npos_es else []
                flpos = get_text(flpos_es[0]) if flpos_es else ''
                apos = ''.join([epos, npos, flpos]).replace(' ', '')

                if all([cont_txt, afdno, adlno, apos]):
                    print(f"{file_nx:<28} | {cont_txt:<16} | {afdno:<16} | {adlno:<16} | {apos:<28}")
                    ALLCHK.append({
                        'CHFILE': file_nx,
                        'AFDNO': afdno,
                        'ADLNO': adlno,
                        'APOS': apos,
                        'ORIG_PATH': full_path,
                        'AFDNO_X': afdno_x,
                        'AFDNO_Y': afdno_y
                    })

# 2. APOS가 일치하는 쌍에 대해, 서로 상대방의 AFDNO를 자신의 CHFILE로 치환
print("\n[APOS MATCH & MUTUAL UPDATE]")

already_fixed = set()
fix_file_map = {}  # {filename: fixfile path}

for i, a in enumerate(ALLCHK):
    for j, b in enumerate(ALLCHK):
        if i >= j:
            continue
        if a['APOS'] == b['APOS']:
            print(f"[APOS MATCH] {a['CHFILE']} <-> {b['CHFILE']} : APOS = {a['APOS']}")

            for obj, newval, path, afdno in [
                (a, b['CHFILE'], a['ORIG_PATH'], a['AFDNO']),
                (b, a['CHFILE'], b['ORIG_PATH'], b['AFDNO'])
            ]:
                # === [핵심] ===
                orig_fix = os.path.splitext(path)[0] + "_FIX.dxf"
                use_file = orig_fix if os.path.exists(orig_fix) else path
                fix_file_map[path] = orig_fix  # 저장할 fix 파일 이름 등록

                try:
                    docf = ezdxf.readfile(use_file)
                    msp_f = docf.modelspace()
                    changed = False
                    for e in msp_f.query('TEXT MTEXT'):
                        if get_text(e) == afdno:
                            set_text(e, newval, color=2)
                            changed = True
                    if changed or (not os.path.exists(orig_fix)):
                        docf.saveas(orig_fix)
                        print(f"  -> {os.path.basename(orig_fix)} : {afdno} → {newval}")
                    already_fixed.add((orig_fix, newval))
                except Exception as ex:
                    print(f"  [ERROR] {obj['CHFILE']} 치환/저장 오류: {ex}")

# 3. 각 선택 파일별로 _FIX.DXF가 없으면, 원본 또는 이미 작업된 도면을 fix 파일로 저장 (실제 수정 없어도)
for path in file_paths:
    fix_path = os.path.splitext(path)[0] + "_FIX.dxf"
    if not os.path.exists(fix_path):
        # 최신 _FIX 도면이 있다면 그걸, 아니면 원본을 읽어서 저장
        src_file = fix_file_map.get(path, path)
        try:
            docf = ezdxf.readfile(src_file)
            docf.saveas(fix_path)
            print(f"[SAVE] {os.path.basename(fix_path)} (최초 생성)")
        except Exception as ex:
            print(f"  [ERROR] {os.path.basename(path)} 저장 오류: {ex}")

# 4. 최종 ALLCHK 결과 표로 출력
print("\n최종 결과:")
print(header)
print("-" * len(header))
for row in ALLCHK:
    print(f"{row['CHFILE']:<28} | {'CONT':<16} | {row['AFDNO']:<16} | {row['ADLNO']:<16} | {row['APOS']:<28}")

