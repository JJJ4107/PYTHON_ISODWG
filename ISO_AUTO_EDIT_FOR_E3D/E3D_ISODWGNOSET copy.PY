import os
import re
import ezdxf
import tkinter as tk
from tkinter import filedialog
from collections import defaultdict
import shutil
import tempfile
from typing import List, Dict, Tuple, Optional

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
        print(f"[SAVE] {os.path.basename(target_path)} 저장 완료")
        return target_path
    except Exception as e:
        try:
            alt_path = next_unique_path(target_path)
            ensure_parent_dir(alt_path)
            doc.saveas(alt_path)
            print(f"[SAVE-ALT] {os.path.basename(target_path)} 실패 → {os.path.basename(alt_path)} 로 저장")
            return alt_path
        except Exception as e2:
            try:
                tmpdir = tempfile.gettempdir()
                fallback = os.path.join(tmpdir, os.path.basename(target_path))
                if os.path.exists(fallback):
                    fallback = next_unique_path(fallback)
                doc.saveas(fallback)
                print(f"[SAVE-TMP] {os.path.basename(target_path)} 실패 → 임시폴더로 저장: {fallback}")
                return fallback
            except Exception as e3:
                print(f"[ERROR] 저장 실패: {target_path}\n  - {e}\n  - {e2}\n  - {e3}")
                return None

# === 최적화된 엔티티 인덱스 클래스 ===
class EntityIndex:
    """공간 인덱싱을 통한 빠른 엔티티 검색"""
    def __init__(self, msp):
        self.text_entities = []
        self.spatial_index = defaultdict(list)  # 그리드 기반 인덱스
        self.grid_size = 10  # 그리드 셀 크기
        
        # 한 번만 순회하여 모든 텍스트 엔티티 인덱싱
        for e in msp.query('TEXT MTEXT'):
            x, y = get_xy(e)
            txt = get_text(e)
            color = getattr(e.dxf, "color", 256)
            
            entity_data = {
                'entity': e,
                'x': x,
                'y': y,
                'text': txt,
                'color': color
            }
            
            self.text_entities.append(entity_data)
            
            # 그리드 인덱스에 추가
            grid_x = int(x // self.grid_size)
            grid_y = int(y // self.grid_size)
            self.spatial_index[(grid_x, grid_y)].append(entity_data)
    
    def find_below_optimized(self, base_x: float, base_y: float, 
                            x_tol: float = 4, y_tol: float = 20, 
                            patt: Optional[str] = None, 
                            color: Optional[int] = None) -> List:
        """최적화된 아래쪽 엔티티 검색"""
        candidates = []
        
        # 검색할 그리드 범위 계산
        min_grid_x = int((base_x - x_tol) // self.grid_size) - 1
        max_grid_x = int((base_x + x_tol) // self.grid_size) + 1
        min_grid_y = int((base_y - y_tol) // self.grid_size) - 1
        max_grid_y = int(base_y // self.grid_size) + 1
        
        # 해당 그리드 셀들만 검색
        for gx in range(min_grid_x, max_grid_x + 1):
            for gy in range(min_grid_y, max_grid_y + 1):
                for entity_data in self.spatial_index[(gx, gy)]:
                    x = entity_data['x']
                    y = entity_data['y']
                    
                    if (abs(x - base_x) <= x_tol and 
                        y < base_y and 
                        0 < base_y - y <= y_tol):
                        
                        if patt is None or re.search(patt, entity_data['text'], re.I):
                            if color is None or entity_data['color'] == color:
                                candidates.append((base_y - y, entity_data['entity']))
        
        return [e for _, e in sorted(candidates, key=lambda t: t[0])]

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

def find_chain_below_optimized(index: EntityIndex, cont_e, cont_x, cont_y, x_tol=4, y_tol=20):
    """최적화된 체인 검색"""
    chain = [(cont_e, get_text(cont_e), cont_x, cont_y)]
    last_x, last_y = cont_x, cont_y
    
    for _ in range(4):
        next_es = index.find_below_optimized(last_x, last_y, x_tol=x_tol, y_tol=y_tol)
        if not next_es:
            break
        next_e = next_es[0]
        chain.append((next_e, get_text(next_e), *get_xy(next_e)))
        last_x, last_y = get_xy(next_e)
    
    return chain if len(chain) == 5 else None

# === 메인 프로그램 시작 ===
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

# === STEP 1: 첫 번째 파일의 로직 실행 (메모리상에서만) ===
print("=== STEP 1: FDNO 처리 시작 ===")

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

# 파일 정보 파싱 및 그룹화
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

# FDNO 계산
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

# 문서와 인덱스를 함께 캐시
doc_cache = {}
index_cache = {}

# (1) 전체 LINENO-FDNO 매핑 테이블 만들기
lineno_to_fdno = {}
for f in fdno_list:
    try:
        doc = ezdxf.readfile(f['path'])
        msp = doc.modelspace()
        doc_cache[f['path']] = doc
        
        # 인덱스 생성
        index = EntityIndex(msp)
        index_cache[f['path']] = index
        
        # 색상 변경은 한 번의 순회로 처리
        for e in msp:
            if e.dxftype() in ('TEXT', 'MTEXT'):
                try:
                    e.dxf.color = 2  # YELLOW
                except:
                    pass
            elif e.dxftype() in ('POLYLINE', 'LWPOLYLINE', 'LINE', 'CIRCLE', 'ARC'):
                try:
                    if hasattr(e.dxf, 'color') and e.dxf.color == 1:
                        e.dxf.color = 7  # WHITE
                except:
                    pass
    except Exception as e:
        print(f"{f['path']} 읽기 오류: {e}")
        continue
    
    # LINENO 추출 (인덱스 활용)
    for entity_data in index.text_entities:
        x, y = entity_data['x'], entity_data['y']
        txt = entity_data['text'].strip()
        if 0 <= x <= 150 and 0 <= y <= 85 and '-' in txt and len(txt) >= 10:
            txt_clean = clean_str(txt)
            all_linenos.append((f['FDNO'], txt_clean, (x, y), os.path.basename(f['path'])))
            lineno_to_fdno[txt_clean] = f['FDNO']

# (2) CONT-DLNO-FDNO 매핑 처리 (최적화된 검색 사용)
for f in fdno_list:
    doc = doc_cache.get(f['path'])
    index = index_cache.get(f['path'])
    if not doc or not index:
        continue
    msp = doc.modelspace()

    # 현 도면의 LINENO 추출 (인덱스 활용)
    cur_lineno = None
    for entity_data in index.text_entities:
        x, y = entity_data['x'], entity_data['y']
        txt = entity_data['text'].strip()
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

    # CONT 엔티티 처리 (인덱스 활용)
    for entity_data in index.text_entities:
        txt = entity_data['text']
        x, y = entity_data['x'], entity_data['y']
        e = entity_data['entity']
        
        if (('CONT' in txt and '.' in txt) or ('CONN' in txt and '.' in txt)):
            cont_height = get_height(e)
            cont_style = e.dxf.style if hasattr(e.dxf, 'style') else 'Standard'
            cont_layer = e.dxf.layer if hasattr(e.dxf, 'layer') else '0'
            cont_width = getattr(e.dxf, 'width', 1.0)
            cont_rotation = getattr(e.dxf, 'rotation', 0.0)

            cont_entity = e
            cont_x, cont_y = x, y

            # 최적화된 DLNO 검색
            dlno_candidates = index.find_below_optimized(cont_x, cont_y, x_tol=2, y_tol=10)
            dlno_e = None
            dlno_txt = None
            
            for candidate in dlno_candidates:
                t2 = get_text(candidate).strip()
                t2_clean = clean_str(t2)
                if '-' in t2_clean or re.fullmatch(r'\d+', t2_clean):
                    dlno_e = candidate
                    dlno_txt = t2_clean
                    try:
                        dlno_e.dxf.color = 2  # YELLOW
                    except:
                        pass
                    break

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

            # 엔티티 업데이트
            if dlno_e is not None:
                try:
                    dlno_e.dxf.color = 2
                except:
                    pass

            if cont_entity is not None:
                try:
                    cont_entity.dxf.insert = (cont_x, cont_y + cont_height * 1.3)
                    cont_entity.dxf.color = 2
                except:
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

    # FABRICATION MATERIALS 처리 (인덱스 활용)
    fab_mat_e = None
    fab_x, fab_y = None, None
    
    for entity_data in index.text_entities:
        txt = entity_data['text']
        if "FABRICATION MATERIALS" in txt.upper():
            fab_mat_e = entity_data['entity']
            fab_x, fab_y = entity_data['x'], entity_data['y']
            break
    
    if fab_mat_e:
        fname_e = None
        for entity_data in index.text_entities:
            txt = entity_data['text'].strip()
            x, y = entity_data['x'], entity_data['y']
            if fab_x is not None and fab_y is not None:
                if (x > fab_x) and (0 <= y <= 20) and ('-' in txt):
                    fname_e = entity_data['entity']
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
                except:
                    pass

# 결과 요약 출력
print("\n==== FDNO-LINENO-도면명 매핑 ====")
for fdno, lineno, (x, y), filename in all_linenos:
    print(f"FDNO: {fdno}   <->   LINENO: {lineno}   <->   FILE: {filename}")

print("\n==== CONT-DLNO-FDNO-LINENO 매핑 ====")
for cont, dlno, fdno, (x, y) in cont_dlno_map:
    print(f"CONT: {cont}   DLNO: {dlno}   FDNO: {fdno}   (좌표: {x:.1f}, {y:.1f})")

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
            index = index_cache.get(info['path'])
            if not doc or not index:
                continue
            msp = doc.modelspace()
            
            # FABRICATION MATERIALS 처리 (인덱스 활용)
            fab_e = None
            fab_x, fab_y = None, None
            for entity_data in index.text_entities:
                txt = entity_data['text']
                if "FABRICATION MATERIALS" in txt.upper():
                    fab_e = entity_data['entity']
                    fab_x, fab_y = entity_data['x'], entity_data['y']
                    break
            
            if fab_e:
                for entity_data in index.text_entities:
                    txt = entity_data['text'].strip()
                    x, y = entity_data['x'], entity_data['y']
                    if fab_x is not None and fab_y is not None:
                        if (x > fab_x) and (0 <= y <= 20) and ('-' in txt):
                            set_text(entity_data['entity'], fdnos[idx])
                            break
    else:
        info = group[0]
        fdno_mapping[info['path']] = info['FDNO']

print("\n=== STEP 2: APOS 매칭 및 치환 시작 ===")

dxf_folder = os.path.dirname(file_paths[0])
ALLCHK = []

header = f"{'도면명':<28} | {'CONT':<16} | {'AFDNO':<16} | {'ADLNO':<16} | {'APOS':<28}"
print(header)
print("-" * len(header))

# ALLCHK 구성 - 인덱스 활용
for path in file_paths:
    file_nx = fdno_mapping.get(path, filename_base(path))
    file = os.path.basename(path)
    doc = doc_cache.get(path)
    index = index_cache.get(path)
    if not doc or not index:
        print(f"{file} 읽기 오류: 캐시에 없음")
        continue
    msp = doc.modelspace()

    cont_entities = []
    for entity_data in index.text_entities:
        txt = entity_data['text'].upper()
        if (('CONT' in txt and '.' in txt) or ('CONN' in txt and '.' in txt)):
            cont_entities.append((entity_data['entity'], txt, 
                                entity_data['x'], entity_data['y']))
            try: 
                entity_data['entity'].dxf.color = 2  # YELLOW
            except: 
                pass

    if not cont_entities:
        print(f"{file_nx:<28} | {'[CONT 없음]':<16}")
        continue

    for cont_e, cont_txt, cont_x, cont_y in cont_entities:
        chain = find_chain_below_optimized(index, cont_e, cont_x, cont_y)
        if not chain:
            print(f"{file_nx:<28} | [CONT 5개 미만 SKIP]")
            continue

        # 최적화된 AFDNO 검색
        afdno_es = index.find_below_optimized(cont_x, cont_y, x_tol=4, y_tol=20, 
                                             patt=r"(-|FMF)")
        
        for afdno_e in afdno_es:
            afdno = get_text(afdno_e)
            afdno_x, afdno_y = get_xy(afdno_e)

            # 최적화된 하위 요소 검색들
            adlno_es = index.find_below_optimized(afdno_x, afdno_y, x_tol=4, y_tol=20, 
                                                 patt=r"(-|FMF)")
            adlno = get_text(adlno_es[0]) if adlno_es else ''
            
            epos_es = index.find_below_optimized(afdno_x, afdno_y, x_tol=4, y_tol=20, 
                                                patt=r"\b(E|W)\b")
            epos = get_text(epos_es[0]) if epos_es else ''
            
            if epos_es:
                epos_x, epos_y = get_xy(epos_es[0])
                npos_es = index.find_below_optimized(epos_x, epos_y, x_tol=4, y_tol=20, 
                                                    patt=r"\b(S|N)\b")
                npos = get_text(npos_es[0]) if npos_es else ''
                
                if npos_es:
                    npos_x, npos_y = get_xy(npos_es[0])
                    flpos_es = index.find_below_optimized(npos_x, npos_y, x_tol=4, y_tol=20, 
                                                         patt=r"(FL|EL)")
                    flpos = get_text(flpos_es[0]) if flpos_es else ''
                else:
                    flpos = ''
            else:
                npos = ''
                flpos = ''
            
            apos = ''.join([epos, npos, flpos]).replace(' ', '')

            if all([cont_txt, afdno, adlno, apos]):
                print(f"{file_nx:<28} | {cont_txt:<16} | {afdno:<16} | {adlno:<16} | {apos:<28}")
                ALLCHK.append({
                    'CHFILE': file_nx,
                    'AFDNO': afdno,
                    'ADLNO': adlno,
                    'APOS': apos,
                    'ORIG_PATH': path,
                    'AFDNO_X': afdno_x,
                    'AFDNO_Y': afdno_y
                })

# APOS 매칭 최적화 - 해시맵 사용으로 O(k²) → O(k)
print("\n[APOS MATCH & MUTUAL UPDATE]")

apos_groups = defaultdict(list)
for item in ALLCHK:
    apos_groups[item['APOS']].append(item)

# 같은 APOS를 가진 항목들끼리 매칭
for apos, group in apos_groups.items():
    if len(group) >= 2:
        # 그룹 내 모든 쌍에 대해 처리
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                print(f"[APOS MATCH] {a['CHFILE']} <-> {b['CHFILE']} : APOS = {a['APOS']}")
                
                for obj, newval, path, afdno in [
                    (a, b['CHFILE'], a['ORIG_PATH'], a['AFDNO']),
                    (b, a['CHFILE'], b['ORIG_PATH'], b['AFDNO'])
                ]:
                    doc = doc_cache.get(path)
                    index = index_cache.get(path)
                    if not doc or not index:
                        continue
                    msp = doc.modelspace()
                    
                    # 인덱스를 활용한 빠른 검색
                    for entity_data in index.text_entities:
                        if entity_data['text'] == afdno:
                            set_text(entity_data['entity'], newval, color=2)
                            print(f"  -> {os.path.basename(path)} : {afdno} → {newval}")
                            break

# === STEP 3: 최종 저장 (FDNO_FIX.dxf) ===
print("\n=== STEP 3: 최종 저장 ===")
for path, fdno in fdno_mapping.items():
    doc = doc_cache.get(path)
    if not doc:
        try:
            doc = ezdxf.readfile(path)
        except Exception as e:
            print(f"[ERROR] {os.path.basename(path)} 재오픈 실패: {e}")
            continue
    fix_path = os.path.join(os.path.dirname(path), f"{fdno}_FIX.dxf")
    saved = safe_save_dxf(doc, fix_path)
    if not saved:
        print(f"[ERROR] {os.path.basename(path)} 저장 실패(최종)")

# 매핑에 없던 파일도 저장
unmapped = [p for p in file_paths if p not in fdno_mapping]
for path in unmapped:
    doc = doc_cache.get(path)
    if not doc:
        try:
            doc = ezdxf.readfile(path)
        except Exception as e:
            print(f"[ERROR] {os.path.basename(path)} 재오픈 실패: {e}")
            continue
    base = filename_base(path)
    fallback_fix = os.path.join(os.path.dirname(path), f"{base}_FIX.dxf")
    saved = safe_save_dxf(doc, fallback_fix)
    if not saved:
        print(f"[ERROR] {os.path.basename(path)} 저장 실패(최종)")

# 최종 ALLCHK 결과 표로 출력
print("\n최종 결과:")
print(header)
print("-" * len(header))
for row in ALLCHK:
    print(f"{row['CHFILE']:<28} | {'CONT':<16} | {row['AFDNO']:<16} | {row['ADLNO']:<16} | {row['APOS']:<28}")

print("\n==== 전체 작업 완료 ====")