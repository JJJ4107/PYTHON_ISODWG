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

def set_text(e, value, color=None):
    try:
        if hasattr(e, 'dxf') and hasattr(e.dxf, 'text'):
            e.dxf.text = value
            if color is not None:
                e.dxf.color = color
        elif hasattr(e, 'text'):
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

def find_special_below(msp, base_x, base_y, x_tol=4, y_tol=20, patt=None):
    candidates = []
    for e in msp.query('TEXT MTEXT'):
        txt = get_text(e)
        x, y = get_xy(e)
        if abs(x-base_x) <= x_tol and (y < base_y) and (0 < base_y - y <= y_tol):
            if patt is None or re.search(patt, txt, re.I):
                candidates.append((base_y - y, e))
    if not candidates:
        return []
    return [e for _, e in sorted(candidates, key=lambda t: t[0])]

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

# 1. 정보 추출 및 CYAN 저장
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
        txt = get_text(e)
        if 'CONT' in txt.upper():
            cont_entities.append((e, txt, *get_xy(e)))
            try: e.dxf.color = 4  # CYAN
            except: pass

    if not cont_entities:
        print(f"{file_nx:<28} | {'[CONT 없음]':<16}")
        continue

    apos_found = False
    for cont_e, cont_txt, cont_x, cont_y in cont_entities:
        afdno_es = find_special_below(msp, cont_x, cont_y, x_tol=4, y_tol=20, patt=r"(-|FMF)")
        if not afdno_es: continue
        afdno_e = afdno_es[0]
        afdno = get_text(afdno_e)
        afdno_x, afdno_y = get_xy(afdno_e)
        adlno_es = find_special_below(msp, afdno_x, afdno_y, x_tol=4, y_tol=20, patt=r"(-|FMF)")
        adlno = get_text(adlno_es[0]) if adlno_es else ''
        epos_es = find_special_below(msp, afdno_x, afdno_y, x_tol=4, y_tol=20, patt=r"\b(E|W)\b")
        if not epos_es: continue
        epos = get_text(epos_es[0])
        npos_es = find_special_below(msp, get_xy(epos_es[0])[0], get_xy(epos_es[0])[1], x_tol=4, y_tol=20, patt=r"\b(S|N)\b")
        if not npos_es: continue
        npos = get_text(npos_es[0])
        flpos_es = find_special_below(msp, get_xy(npos_es[0])[0], get_xy(npos_es[0])[1], x_tol=4, y_tol=20, patt=r"(FL|EL)")
        if not flpos_es: continue
        flpos = get_text(flpos_es[0])
        apos = ''.join([epos, npos, flpos]).replace(' ', '')

        ALLCHK.append({
            'CHFILE': file_nx,
            'AFDNO': afdno,
            'ADLNO': adlno,
            'APOS': apos,
            'ORIG_PATH': full_path
        })
        if not apos_found and apos:
            print(f"{file_nx:<28} | {cont_txt:<16} | {afdno:<16} | {adlno:<16} | {apos:<28}")
            apos_found = True

    try:
        doc.saveas(full_path)
    except Exception as e:
        print(f"[저장실패] {full_path} -> {e}")

# 2. CONF 치환저장 (조건 엄격히 반영, 항상 _FIX 저장)
for chk in ALLCHK:
    cfile_nx = chk['CHFILE']
    cfile_afdno = chk['AFDNO']
    cfile_apos = chk['APOS']
    cfile_path = None
    for candidate in ALLCHK:
        if candidate['CHFILE'] == cfile_nx:
            cfile_path = candidate['ORIG_PATH']
            break
    if not cfile_path:
        print(f"[CONF 저장 SKIP] {cfile_nx}: 파일을 찾지 못했습니다.\n")
        continue

    # 1) APOS 동일한 CHFILE 중 ADLNO가 없는(빈) AFDNO면 PASS
    same_apos = [row for row in ALLCHK if row['APOS'] == cfile_apos]
    if not same_apos:
        print(f"[CONF 저장 SKIP] {cfile_nx}: APOS 일치 후보 없음. PASS(저장 X)\n")
        # → 그래도 _FIX로 저장
        try:
            doc = ezdxf.readfile(cfile_path)
            doc.saveas(os.path.join(dxf_folder, cfile_nx + "_FIX.dxf"))
        except Exception as e:
            print(f"[PASS 저장 실패] {cfile_nx}_FIX.dxf: {e}")
        continue

    adlno_exist = any(row['ADLNO'] not in ('', None) for row in same_apos)
    if not adlno_exist:
        print(f"[CONF 저장 SKIP] {cfile_nx}: APOS 동일 CHFILE에 ADLNO가 없는 경우. PASS(저장 X)\n")
        try:
            doc = ezdxf.readfile(cfile_path)
            doc.saveas(os.path.join(dxf_folder, cfile_nx + "_FIX.dxf"))
        except Exception as e:
            print(f"[PASS 저장 실패] {cfile_nx}_FIX.dxf: {e}")
        continue

    # 2) CFILE의 AFDNO와 CHFILE(파일명)이 같으면 PASS
    found_match = None
    for row in same_apos:
        chfile_val = row['CHFILE']
        if cfile_afdno == chfile_val:
            found_match = chfile_val
            break

    if found_match:
        print(f"[CONF 저장 SKIP] {cfile_nx}: APOS 동일, AFDNO가 CHFILE값과 일치. PASS(저장 X)\n")
        try:
            doc = ezdxf.readfile(cfile_path)
            doc.saveas(os.path.join(dxf_folder, cfile_nx + "_FIX.dxf"))
        except Exception as e:
            print(f"[PASS 저장 실패] {cfile_nx}_FIX.dxf: {e}")
        continue

    # 3) 다를 경우 CFILE의 첫번째 AFDNO만 교체, FIX로 저장
    change_flag = False
    for row in same_apos:
        chfile_val = row['CHFILE']
        if cfile_afdno != chfile_val and row['ADLNO'] not in ('', None):
            change_afdno = chfile_val
            try:
                cfile_doc = ezdxf.readfile(cfile_path)
                cfile_msp = cfile_doc.modelspace()
            except Exception as e:
                print(f"[CFILE OPEN 실패] {cfile_nx}: {e}")
                continue

            changed = False
            for cont_e, cont_txt, cont_x, cont_y in [
                (e, get_text(e), *get_xy(e)) for e in cfile_msp.query('TEXT MTEXT') if 'CONT' in get_text(e).upper()
            ]:
                afdno_es = find_special_below(cfile_msp, cont_x, cont_y, x_tol=4, y_tol=20, patt=r"(-|FMF)")
                if afdno_es:
                    afdno_e = afdno_es[0]
                    old_val = get_text(afdno_e)
                    set_text(afdno_e, change_afdno, color=4)
                    new_val = get_text(afdno_e)
                    print(f"  [DEBUG] {cfile_nx} CONT({cont_txt}) AFDNO '{old_val}' → '{new_val}'")
                    changed = True
                else:
                    print(f"  [DEBUG] {cfile_nx} CONT({cont_txt})에서 첫번째 AFDNO를 찾지 못했습니다.")
            if not changed:
                print(f"  [DEBUG] {cfile_nx}에서 바꿀 첫번째 AFDNO가 없음.")
            conf_path = os.path.join(dxf_folder, cfile_nx + "_FIX.dxf")
            try:
                cfile_doc.saveas(conf_path)
                print(f"[CONF 저장] {cfile_nx} -> {os.path.basename(conf_path)} (AFDNO:{change_afdno})\n")
            except Exception as e:
                print(f"[CONF 저장 실패] {conf_path} -> {e}\n")
            change_flag = True
            break

    if not change_flag:
        # 치환이 없었어도 무조건 저장
        try:
            doc = ezdxf.readfile(cfile_path)
            doc.saveas(os.path.join(dxf_folder, cfile_nx + "_FIX.dxf"))
        except Exception as e:
            print(f"[PASS 저장 실패] {cfile_nx}_FIX.dxf: {e}")

print("\n=== 전체 CONF 변환 및 저장 완료 ===")
