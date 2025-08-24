import os
import re
import ezdxf
from collections import defaultdict
import shutil
import tempfile
import sys

# === 저장 보조 유틸리티(로직 영향 없음) ===
def ensure_parent_dir(path: str):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except Exception:
        pass

def next_unique_path(path: str):
    base, ext = os.path.splitext(path)
    i = 1
    while True:
        cand = f"{base}({i}){ext}"
        if not os.path.exists(cand):
            return cand
        i += 1

def safe_save_dxf(doc, target_path: str):
    try:
        ensure_parent_dir(target_path)
        doc.saveas(target_path)
        return target_path
    except Exception:
        try:
            alt_path = next_unique_path(target_path)
            ensure_parent_dir(alt_path)
            doc.saveas(alt_path)
            return alt_path
        except Exception:
            try:
                tmpdir = tempfile.gettempdir()
                fallback = os.path.join(tmpdir, os.path.basename(target_path))
                if os.path.exists(fallback):
                    fallback = next_unique_path(fallback)
                doc.saveas(fallback)
                return fallback
            except Exception:
                return None

# === 공통 유틸리티 함수들 ===
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

def clean_str(s):
    return ''.join(s.split())

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

# === CLI 파일 입력 ===
file_paths = [p for p in sys.argv[1:] if p.lower().endswith(".dxf")]
if not file_paths:
    sys.exit(0)

# === STEP 1: 첫 번째 파일의 로직 실행 (메모리상에서만) ===
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
all_linenos = []
cont_dlno_map = []

# 문서를 메모리에 보관하기 위한 딕셔너리
doc_cache = {}

# (1) 전체 LINENO-FDNO 매핑 테이블 만들기
lineno_to_fdno = {}
for f in fdno_list:
    try:
        doc = ezdxf.readfile(f['path'])
        msp = doc.modelspace()
        doc_cache[f['path']] = doc
        for e in msp.query('TEXT MTEXT'):
            try:
                e.dxf.color = 2
            except Exception:
                pass
        for e in msp.query('POLYLINE LWPOLYLINE LINE CIRCLE ARC'):
            try:
                if hasattr(e.dxf, 'color') and e.dxf.color == 1:
                    e.dxf.color = 7
            except Exception:
                pass
    except Exception:
        continue
    for e in msp.query('TEXT MTEXT'):
        txt = get_text(e).strip()
        x, y = get_xy(e)
        if 0 <= x <= 150 and 0 <= y <= 85 and '-' in txt and len(txt) >= 10:
            txt_clean = clean_str(txt)
            all_linenos.append((f['FDNO'], txt_clean, (x, y), os.path.basename(f['path'])))
            lineno_to_fdno[txt_clean] = f['FDNO']

# (2) CONT-DLNO-FDNO 매핑 처리
for f in fdno_list:
    doc = doc_cache.get(f['path'])
    if not doc:
        continue
    msp = doc.modelspace()

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
    fdno_sorted = sorted(fdno_candidates, key=fdno_sort_key)

    for e in msp.query('TEXT MTEXT'):
        txt = get_text(e)
        x, y = get_xy(e)
        if (('CONT' in txt and '.' in txt) or ('CONN' in txt and '.' in txt)):
            cont_height = get_height(e)
            cont_style = e.dxf.style if hasattr(e.dxf, 'style') else 'Standard'
            cont_layer = e.dxf.layer if hasattr(e.dxf, 'layer') else '0'
            cont_width = getattr(e.dxf, 'width', 1.0)
            cont_rotation = getattr(e.dxf, 'rotation', 0.0)

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
                            dlno_e.dxf.color = 2
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

            if dlno_e is not None:
                try:
                    dlno_e.dxf.color = 2
                except Exception:
                    pass

            if cont_entity is not None:
                try:
                    cont_entity.dxf.insert = (cont_x, cont_y + cont_height * 1.3)
                    cont_entity.dxf.color = 2
                except Exception:
                    pass

            if fdno_to_output:
                msp.add_text(
                    fdno_to_output,
                    dxfattribs={
                        'insert': (cont_x, cont_y),
                        'color': 2,
                        'height': cont_height,
                        'style': cont_style,
                        'layer': cont_layer,
                        'width': cont_width,
                        'rotation': cont_rotation
                    }
                )

            cont_dlno_map.append((txt, dlno_txt, fdno_to_output, (cont_x, cont_y)))

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
                        'color': 2,
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

# === STEP 2: FNAME/FDNO 최종 매칭 ===
group_by_dall_dn = defaultdict(list)
for f in fdno_list:
    key = (f['DALL'], f['DN'])
    group_by_dall_dn[key].append(f)

fdno_mapping = {}
for key, group in group_by_dall_dn.items():
    if len(group) > 1:
        sorted_group = sorted(group, key=lambda x: (x['SHNO_NUM'], x['FN']))
        fdnos = [x['FDNO'] for x in sorted_group][::-1]
        for idx, info in enumerate(sorted_group):
            fdno_mapping[info['path']] = fdnos[idx]
            doc = doc_cache.get(info['path'])
            if not doc:
                continue
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
    else:
        info = group[0]
        fdno_mapping[info['path']] = info['FDNO']

dxf_folder = os.path.dirname(file_paths[0])
ALLCHK = []

# ALLCHK 구성 - 메모리상의 문서 사용
for path in file_paths:
    file_nx = fdno_mapping.get(path, filename_base(path))
    file = os.path.basename(path)
    doc = doc_cache.get(path)
    if not doc:
        continue
    msp = doc.modelspace()
    for e in msp.query('POLYLINE LWPOLYLINE LINE CIRCLE ARC'):
        try:
            if hasattr(e.dxf, 'color') and e.dxf.color == 1:
                e.dxf.color = 7
        except Exception:
            pass

    cont_entities = []
    for e in msp.query('TEXT MTEXT'):
        txt = get_text(e).upper()
        if (('CONT' in txt and '.' in txt) or
            ('CONN' in txt and '.' in txt)):
            cont_entities.append((e, txt, *get_xy(e)))
            try:
                e.dxf.color = 2
            except:
                pass

    if not cont_entities:
        continue

    for cont_e, cont_txt, cont_x, cont_y in cont_entities:
        chain = find_chain_below(msp, cont_e, cont_x, cont_y)
        if not chain:
            continue

        afdno_es = find_special_below(msp, cont_x, cont_y, x_tol=4, y_tol=20, patt=r"(-|FMF)")
        for afdno_e in afdno_es:
            afdno = get_text(afdno_e)
            afdno_x, afdno_y = get_xy(afdno_e)

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
                ALLCHK.append({
                    'CHFILE': file_nx,
                    'AFDNO': afdno,
                    'ADLNO': adlno,
                    'APOS': apos,
                    'ORIG_PATH': path,
                    'AFDNO_X': afdno_x,
                    'AFDNO_Y': afdno_y
                })

# APOS가 일치하는 쌍에 대해 상호 치환
for i, a in enumerate(ALLCHK):
    for j, b in enumerate(ALLCHK):
        if i >= j:
            continue
        if a['APOS'] == b['APOS']:
            for obj, newval, path, afdno in [
                (a, b['CHFILE'], a['ORIG_PATH'], a['AFDNO']),
                (b, a['CHFILE'], b['ORIG_PATH'], b['AFDNO'])
            ]:
                doc = doc_cache.get(path)
                if not doc:
                    continue
                msp = doc.modelspace()
                for e in msp.query('TEXT MTEXT'):
                    if get_text(e) == afdno:
                        set_text(e, newval, color=2)

# === STEP 3: 최종 저장 (FDNO_FIX.dxf) ===
for path, fdno in fdno_mapping.items():
    doc = doc_cache.get(path)
    if not doc:
        try:
            doc = ezdxf.readfile(path)
        except Exception:
            continue
    fix_path = os.path.join(os.path.dirname(path), f"{fdno}_FIX.dxf")
    _ = safe_save_dxf(doc, fix_path)

# === 매핑에 없던 파일도 무조건 저장 ===
unmapped = [p for p in file_paths if p not in fdno_mapping]
for path in unmapped:
    doc = doc_cache.get(path)
    if not doc:
        try:
            doc = ezdxf.readfile(path)
        except Exception:
            continue
    base = filename_base(path)
    fallback_fix = os.path.join(os.path.dirname(path), f"{base}_FIX.dxf")
    _ = safe_save_dxf(doc, fallback_fix)
