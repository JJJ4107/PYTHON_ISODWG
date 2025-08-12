import os
import re
import ezdxf
import tkinter as tk
from tkinter import filedialog
from collections import defaultdict
import shutil

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

def get_height(e):
    try:
        if hasattr(e, 'dxf') and hasattr(e.dxf, 'height'):
            return float(e.dxf.height)
        elif hasattr(e, 'height'):
            return float(e.height)
    except Exception:
        pass
    return 3.0

def get_text(e):
    try:
        if hasattr(e, 'dxf') and hasattr(e.dxf, 'text'):
            return e.dxf.text
        elif hasattr(e, 'text'):
            return e.text
    except Exception:
        pass
    return ''

def set_text(e, value):
    try:
        if hasattr(e, 'dxf') and hasattr(e.dxf, 'text'):
            e.dxf.text = value
        elif hasattr(e, 'text'):
            e.text = value
    except Exception:
        pass

def clean_str(s):
    return ''.join(s.split())

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

group_by_dall = defaultdict(list)
def parse_filename(filepath):
    base = os.path.basename(filepath)
    name = os.path.splitext(base)[0]
    parts = name.split('-')
    if len(parts) < 4:
        return None
    SHNO = parts[-1]
    DN = parts[-2]
    DALL = '-'.join(parts[:-2])
    return {'path': filepath, 'name': name, 'DN': DN, 'SHNO': SHNO, 'DALL': DALL}

for path in file_paths:
    info = parse_filename(path)
    if info:
        try:
            info['DN_NUM'] = int(re.sub(r'\D','', info['DN']))
        except:
            info['DN_NUM'] = 0
        try:
            info['SHNO_NUM'] = int(re.sub(r'\D','', info['SHNO']))
        except:
            info['SHNO_NUM'] = 0
        info['basename'] = os.path.basename(path)
        group_by_dall[info['DALL']].append(info)

fdno_list = []
for DALL, files in group_by_dall.items():
    dn_nums = []
    for f in files:
        try:
            f['DN_NUM'] = int(re.sub(r'\D','', f['DN']))
            f['SHNO_NUM'] = int(re.sub(r'\D','', f['SHNO']))
            dn_nums.append(f['DN_NUM'])
        except:
            f['DN_NUM'] = None
            f['SHNO_NUM'] = None
    if not dn_nums:
        continue
    max_dn = max(dn_nums)
    for f in files:
        if f['DN_NUM'] == max_dn:
            fn_num = f['DN_NUM']
        else:
            fn_num = f['DN_NUM'] - f['SHNO_NUM'] + 1
        f['FN'] = fn_num
        f['FDNO'] = f"{f['DALL']}-{fn_num:03d}"
        fdno_list.append(f)

yellow = 2
red = 1
all_linenos = []  # (FDNO, LINENO, (x, y), FILENAME)
cont_dlno_map = []

# (1) 전체 LINENO-FDNO 매핑 테이블 만들기 (공백제거 LINENO: FDNO)
lineno_to_fdno = {}
for f in fdno_list:
    try:
        doc = ezdxf.readfile(f['path'])
        msp = doc.modelspace()
    except Exception as e:
        print(f"{f['path']} 읽기 오류: {e}")
        continue
    for e in msp.query('TEXT MTEXT'):
        txt = get_text(e).strip()
        x, y = get_xy(e)
        if 0 <= x <= 150 and 0 <= y <= 85 and '-' in txt and len(txt) >= 10:
            txt_clean = clean_str(txt)
            all_linenos.append((f['FDNO'], txt_clean, (x, y), os.path.basename(f['path'])))
            lineno_to_fdno[txt_clean] = f['FDNO']

# (2) CONT-DLNO-FDNO 매핑/출력
for f in fdno_list:
    try:
        doc = ezdxf.readfile(f['path'])
        msp = doc.modelspace()
    except Exception as e:
        print(f"{f['path']} 읽기 오류: {e}")
        continue

    # 현 도면의 LINENO 1개 추출
    cur_lineno = None
    for e in msp.query('TEXT MTEXT'):
        txt = get_text(e).strip()
        x, y = get_xy(e)
        if 0 <= x <= 150 and 0 <= y <= 85 and '-' in txt and len(txt) >= 10:
            cur_lineno = clean_str(txt)
            break
    if not cur_lineno:
        continue

    fdno_candidates = [
        fdno for fdno, lineno, _, _ in all_linenos if lineno == cur_lineno
    ]
    def fdno_sort_key(fdno):
        m = re.findall(r'\d+', fdno)
        return int(m[-1]) if m else 0
    fdno_sorted = sorted(fdno_candidates, key=fdno_sort_key)  # 오름차순

    for e in msp.query('TEXT MTEXT'):
        txt = get_text(e)
        x, y = get_xy(e)
        if (('CONT' in txt and '.' in txt) or ('CONN' in txt and '.' in txt)):
            cont_height = get_height(e)
            cont_style = e.dxf.style if hasattr(e.dxf, 'style') else 'Standard'
            cont_layer = e.dxf.layer if hasattr(e.dxf, 'layer') else '0'
            cont_width = getattr(e.dxf, 'width', 1.0)
            cont_rotation = getattr(e.dxf, 'rotation', 0.0)

            # CONT 기준점 저장
            cont_entity = e
            cont_x, cont_y = x, y

            min_dy = float('inf')
            dlno_e = None
            dlno_txt = None
            for e2 in msp.query('TEXT MTEXT'):
                t2 = get_text(e2)
                tx, ty = get_xy(e2)
                t2_clean = clean_str(t2.strip())
                if abs(tx - cont_x) <= 2 and ty < cont_y and abs(ty - cont_y) < 10:
                    if '-' in t2_clean or re.fullmatch(r'\d+', t2_clean):
                        dy = abs(ty - cont_y)
                        if dy < min_dy:
                            min_dy = dy
                            dlno_e = e2
                            dlno_txt = t2_clean
                    if dlno_e is not None:
                        try:
                         dlno_e.dxf.color = 3   # ← GREEN으로 변경
                        except Exception:
                         pass

            fdno_to_output = None
            is_digit = False

            if dlno_e and dlno_txt:
                if dlno_txt.isdigit():
                    idx = int(dlno_txt) - 1
                    if 0 <= idx < len(fdno_sorted):
                        fdno_to_output = fdno_sorted[idx]
                        is_digit = True
                else:
                    fdno_to_output = lineno_to_fdno.get(dlno_txt)
                    is_digit = False
                    if not fdno_to_output:
                        continue

            # 1. DLNO(아래쪽 번호/키워드)는 이동하지 않고 색상만 노란색으로 변경
            if dlno_e is not None:
                try:
                    dlno_e.dxf.color = yellow
                except Exception:
                    pass

            # 2. CONT(기준점)는 위쪽(Y)으로 cont_height*1.3 이동, 색상 노란색
            if cont_entity is not None:
                try:
                    cont_entity.dxf.insert = (cont_x, cont_y + cont_height * 1.3)
                    cont_entity.dxf.color = yellow
                except Exception:
                    pass

            # 3. FDNO(빨간색)는 CONT 원래 위치에 add_text로 출력
            if fdno_to_output:
                msp.add_text(
                    fdno_to_output,
                    dxfattribs={
                        'insert': (cont_x, cont_y),
                        'color': red,
                        'height': cont_height,
                        'style': cont_style,
                        'layer': cont_layer,
                        'width': cont_width,
                        'rotation': cont_rotation
                    }
                )

            cont_dlno_map.append((txt, dlno_txt, fdno_to_output, (cont_x, cont_y)))

    # === FABRICATION MATERIALS → FNAME → FDNO 출력/삭제 ===
    fab_mat_e = None
    fab_x, fab_y = None, None
    for e in msp.query('TEXT MTEXT'):
        txt = get_text(e)
        if "FABRICATION MATERIALS" in txt.upper():
            fab_mat_e = e
            fab_x, fab_y = get_xy(e)
            break
    if fab_mat_e:
        fname_e = None
        fname_x, fname_y = None, None
        for e in msp.query('TEXT MTEXT'):
            txt = get_text(e).strip()
            x, y = get_xy(e)
            if fab_x is not None and fab_y is not None:
                if (x > fab_x) and (0 <= y <= 20) and ('-' in txt):
                    fname_e = e
                    fname_x, fname_y = x, y
                    fname_txt = txt
                    break
        if fname_e:
            filename = os.path.basename(f['path'])
            fdno_for_file = None
            for fdno, lineno, _, file in all_linenos:
                if file == filename:
                    fdno_for_file = fdno
                    break
            if fdno_for_file:
                style = fname_e.dxf.style if hasattr(fname_e.dxf, 'style') else 'Standard'
                height = fname_e.dxf.height if hasattr(fname_e.dxf, 'height') else 3.0
                layer = fname_e.dxf.layer if hasattr(fname_e.dxf, 'layer') else '0'
                width = getattr(fname_e.dxf, 'width', 1.0)
                rotation = getattr(fname_e.dxf, 'rotation', 0.0)
                msp.add_text(
                    fdno_for_file,
                    dxfattribs={
                        'insert': (fname_x, fname_y),
                        'color': 3, # green for debug
                        'height': height,
                        'style': style,
                        'layer': layer,
                        'width': width,
                        'rotation': rotation
                    }
                )
                try:
                    msp.delete_entity(fname_e)
                except Exception:
                    pass

    # 임시 저장(최종 저장은 아래서)
    tmp_save = f['path'][:-4] + '_autosave.dxf'
    try:
        doc.saveas(tmp_save)
        f['tmp_save'] = tmp_save
    except Exception as e:
        print(f"{tmp_save} 저장 오류: {e}")

# 결과 요약 출력 (도면명 포함)
print("\n==== FDNO-LINENO-도면명 매핑 ====")
for fdno, lineno, (x, y), filename in all_linenos:
    print(f"FDNO: {fdno}   <->   LINENO: {lineno}   <->   FILE: {filename}")

print("\n==== CONT-DLNO-FDNO-LINENO 매핑 ====")
for cont, dlno, fdno, (x, y) in cont_dlno_map:
    print(f"CONT: {cont}   DLNO: {dlno}   FDNO: {fdno}   (좌표: {x:.1f}, {y:.1f})")

print("\n==== 완료! ====")
print("각 도면 FDNO.dxf 파일로 저장\n")

# ====================== [마지막 매칭 및 저장 단계] =========================
group_by_dall_dn = defaultdict(list)
for f in fdno_list:
    key = (f['DALL'], f['DN'])
    group_by_dall_dn[key].append(f)

for key, group in group_by_dall_dn.items():
    if len(group) > 1:
        sorted_group = sorted(group, key=lambda x: (x['SHNO_NUM'], x['FN']))
        fdnos = [x['FDNO'] for x in sorted_group][::-1]
        for idx, info in enumerate(sorted_group):
            tmp_path = info.get('tmp_save')
            if not tmp_path or not os.path.exists(tmp_path):
                continue
            try:
                doc = ezdxf.readfile(tmp_path)
                msp = doc.modelspace()
                fab_e = None
                fab_x, fab_y = None, None
                for e in msp.query('TEXT MTEXT'):
                    txt = get_text(e)
                    if "FABRICATION MATERIALS" in txt.upper():
                        fab_e = e
                        fab_x, fab_y = get_xy(e)
                        break
                if fab_e:
                    for e in msp.query('TEXT MTEXT'):
                        txt = get_text(e).strip()
                        x, y = get_xy(e)
                        if fab_x is not None and fab_y is not None:
                            if (x > fab_x) and (0 <= y <= 20) and ('-' in txt):
                                set_text(e, fdnos[idx])
                                break
                out_path = os.path.join(os.path.dirname(info['path']), f"{fdnos[idx]}.dxf")
                doc.saveas(out_path)
                print(f"[FNAME/저장] {os.path.basename(info['path'])} → {fdnos[idx]}.dxf")
                try:
                    os.remove(tmp_path)
                except:
                    pass
            except Exception as e:
                print(f"[에러] {tmp_path}: {e}")
    else:
        info = group[0]
        tmp_path = info.get('tmp_save')
        if tmp_path and os.path.exists(tmp_path):
            try:
                out_path = os.path.join(os.path.dirname(info['path']), f"{info['FDNO']}.dxf")
                shutil.move(tmp_path, out_path)
                print(f"[FNAME/저장] {os.path.basename(info['path'])} → {info['FDNO']}.dxf")
            except Exception as e:
                print(f"[에러] {tmp_path}: {e}")

print("==== FNAME/FDNO 최종 매칭 및 파일명 저장 완료 ====")
