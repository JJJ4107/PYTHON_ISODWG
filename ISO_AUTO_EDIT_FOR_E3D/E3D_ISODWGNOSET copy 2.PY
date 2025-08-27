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
        # ZOOM ALL 효과를 위한 범위 계산
        try:
            msp = doc.modelspace()
            
            # 모든 엔티티의 경계 계산
            min_x = min_y = float('inf')
            max_x = max_y = float('-inf')
            
            has_entities = False
            for entity in msp:
                try:
                    # 엔티티의 위치 정보 수집
                    if hasattr(entity, 'dxf'):
                        if hasattr(entity.dxf, 'insert'):
                            x, y = get_xy(entity)
                            min_x, max_x = min(min_x, x), max(max_x, x)
                            min_y, max_y = min(min_y, y), max(max_y, y)
                            has_entities = True
                        elif hasattr(entity.dxf, 'start') and hasattr(entity.dxf, 'end'):
                            # LINE 엔티티
                            for point in [entity.dxf.start, entity.dxf.end]:
                                min_x, max_x = min(min_x, point[0]), max(max_x, point[0])
                                min_y, max_y = min(min_y, point[1]), max(max_y, point[1])
                                has_entities = True
                        elif hasattr(entity.dxf, 'center'):
                            # CIRCLE, ARC 엔티티
                            center = entity.dxf.center
                            radius = getattr(entity.dxf, 'radius', 0)
                            min_x = min(min_x, center[0] - radius)
                            max_x = max(max_x, center[0] + radius)
                            min_y = min(min_y, center[1] - radius)
                            max_y = max(max_y, center[1] + radius)
                            has_entities = True
                except:
                    pass
            
            # 범위가 유효한 경우 헤더에 설정
            if has_entities and min_x != float('inf'):
                # 여백 추가 (10%)
                margin = 0.1
                width = max_x - min_x
                height = max_y - min_y
                
                min_x -= width * margin
                max_x += width * margin
                min_y -= height * margin
                max_y += height * margin
                
                # DXF 헤더에 범위 설정
                doc.header['$EXTMIN'] = (min_x, min_y, 0)
                doc.header['$EXTMAX'] = (max_x, max_y, 0)
                
                # LIMMIN, LIMMAX도 설정
                doc.header['$LIMMIN'] = (min_x, min_y)
                doc.header['$LIMMAX'] = (max_x, max_y)
                
                # ZOOM ALL 상태로 설정
                doc.header['$LIMCHECK'] = 0
        except:
            # 범위 계산 실패 시 무시
            pass
        
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

def parse_filename(filepath):
    """파일명에서 DALL, DN, SHNO 추출"""
    base = os.path.basename(filepath)
    name = os.path.splitext(base)[0]
    parts = name.split('-')
    if len(parts) < 4:
        return None
    SHNO = parts[-1]
    DN = parts[-2]
    DALL = '-'.join(parts[:-2])
    return {'path': filepath, 'name': name, 'DN': DN, 'SHNO': SHNO, 'DALL': DALL}

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

def update_fdno_in_drawing(doc, index, old_fdno, new_fdno):
    """도면 내의 모든 FDNO 텍스트를 업데이트"""
    msp = doc.modelspace()
    update_count = 0
    
    # X740 Y20 근처의 FDNO 업데이트 (FABRICATION MATERIALS 옆)
    for entity_data in index.text_entities:
        x, y = entity_data['x'], entity_data['y']
        txt = entity_data['text'].strip()
        
        # X740 Y20 근처의 텍스트 확인
        if 700 <= x <= 800 and 0 <= y <= 40:
            if txt == old_fdno:
                set_text(entity_data['entity'], new_fdno, color=2)
                print(f"  ✓ X740 Y20 근처 FDNO 업데이트: {old_fdno} → {new_fdno}")
                update_count += 1
    
    # CONT 아래의 FDNO 업데이트
    for entity_data in index.text_entities:
        txt = entity_data['text']
        if txt == old_fdno:
            x, y = entity_data['x'], entity_data['y']
            # CONT 위치 확인 (위쪽에 CONT가 있는지)
            cont_found = False
            for other_entity in index.text_entities:
                other_txt = other_entity['text'].upper()
                other_x, other_y = other_entity['x'], other_entity['y']
                if (('CONT' in other_txt and '.' in other_txt) or ('CONN' in other_txt and '.' in other_txt)):
                    if abs(x - other_x) <= 4 and other_y > y and other_y - y <= 20:
                        cont_found = True
                        break
            
            if cont_found:
                set_text(entity_data['entity'], new_fdno, color=2)
                print(f"  ✓ CONT 아래 FDNO 업데이트: {old_fdno} → {new_fdno} @ ({x:.1f},{y:.1f})")
                update_count += 1
    
    return update_count

# === 메인 프로그램 시작 ===
def main():
    # 파일 선택
    root = tk.Tk()
    root.withdraw()
    file_paths = filedialog.askopenfilenames(
        title="DXF 도면 선택", filetypes=[("DXF files", "*.dxf")]
    )
    root.destroy()
    if not file_paths:
        print("DXF 파일이 선택되지 않았습니다.")
        return
    
    # === STEP 1: 첫 번째 파일의 로직 실행 (메모리상에서만) ===
    print("=== STEP 1: FDNO 처리 시작 ===")
    
    group_by_dall = defaultdict(list)
    
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
        # DN별로 다시 그룹화
        dn_groups = defaultdict(list)
        for f in files:
            if f['DN_NUM'] is not None:
                dn_groups[f['DN_NUM']].append(f)
        
        # 각 DN 그룹 내에서 SHNO 순서대로 FDNO 할당
        for dn, dn_files in dn_groups.items():
            # SHNO 순으로 정렬
            sorted_files = sorted(dn_files, key=lambda x: x['SHNO_NUM'])
            
            # base_fn은 DN - SHNO 개수 + 1로 계산
            base_fn = dn - len(dn_files)
            
            for idx, f in enumerate(sorted_files):
                # SHNO가 높을수록 높은 FDNO를 받음
                fn_num = base_fn + f['SHNO_NUM']
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
        
        # LINENO 추출
        for entity_data in index.text_entities:
            x, y = entity_data['x'], entity_data['y']
            txt = entity_data['text'].strip()
            if 0 <= x <= 150 and 0 <= y <= 85 and '-' in txt and len(txt) >= 10:
                txt_clean = clean_str(txt)
                all_linenos.append((f['FDNO'], txt_clean, (x, y), os.path.basename(f['path'])))
                lineno_to_fdno[txt_clean] = f['FDNO']
    
    # (2) CONT-DLNO-FDNO 매핑 처리
    for f in fdno_list:
        doc = doc_cache.get(f['path'])
        index = index_cache.get(f['path'])
        if not doc or not index:
            continue
        msp = doc.modelspace()
        
        # 현 도면의 LINENO 추출
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
        
        # CONT 엔티티 처리
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
                
                # DLNO 검색
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
        
        # FABRICATION MATERIALS 처리 (X740 Y20 근처)
        for entity_data in index.text_entities:
            txt = entity_data['text'].strip()
            x, y = entity_data['x'], entity_data['y']
            
            # FABRICATION MATERIALS 근처의 파일명 찾기
            if 700 <= x <= 800 and 0 <= y <= 40 and '-' in txt and len(txt) > 10:
                # 기존 파일명을 FDNO로 교체
                style = entity_data['entity'].dxf.style if hasattr(entity_data['entity'].dxf, 'style') else 'Standard'
                height = entity_data['entity'].dxf.height if hasattr(entity_data['entity'].dxf, 'height') else 3.0
                layer = entity_data['entity'].dxf.layer if hasattr(entity_data['entity'].dxf, 'layer') else '0'
                width = getattr(entity_data['entity'].dxf, 'width', 1.0)
                rotation = getattr(entity_data['entity'].dxf, 'rotation', 0.0)
                
                msp.add_text(
                    f['FDNO'],
                    dxfattribs={
                        'insert': (x, y),
                        'color': 2,
                        'height': height,
                        'style': style,
                        'layer': layer,
                        'width': width,
                        'rotation': rotation
                    }
                )
                try:
                    msp.delete_entity(entity_data['entity'])
                except:
                    pass
                break
    
    # === STEP 2: APOS 수집 ===
    print("\n=== STEP 2: APOS 수집 및 매핑 시작 ===")
    
    # 초기 FDNO 매핑 (path -> FDNO)
    initial_fdno_mapping = {}
    for f in fdno_list:
        initial_fdno_mapping[f['path']] = f['FDNO']
    
    # APOS 정보 수집
    ALLCHK = []
    
    for f in fdno_list:
        doc = doc_cache.get(f['path'])
        index = index_cache.get(f['path'])
        if not doc or not index:
            continue
        
        # CONT 엔티티 찾기 및 APOS 추출
        for entity_data in index.text_entities:
            txt = entity_data['text'].upper()
            x, y = entity_data['x'], entity_data['y']
            
            if (('CONT' in txt and '.' in txt) or ('CONN' in txt and '.' in txt)):
                cont_x, cont_y = x, y
                
                # CONT 아래 체인 찾기
                chain = find_chain_below_optimized(index, entity_data['entity'], cont_x, cont_y)
                if not chain:
                    continue
                
                # AFDNO 검색
                afdno_es = index.find_below_optimized(cont_x, cont_y, x_tol=4, y_tol=20, 
                                                     patt=r"(-|FMF)")
                
                for afdno_e in afdno_es:
                    afdno = get_text(afdno_e)
                    afdno_x, afdno_y = get_xy(afdno_e)
                    
                    # 하위 요소 검색
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
                    
                    if all([txt, afdno, adlno, apos]):
                        ALLCHK.append({
                            'PATH': f['path'],
                            'INITIAL_FDNO': f['FDNO'],
                            'AFDNO': afdno,
                            'ADLNO': adlno,
                            'APOS': apos,
                            'CONT_X': cont_x,
                            'CONT_Y': cont_y,
                            'AFDNO_X': afdno_x,
                            'AFDNO_Y': afdno_y
                        })
    
    # === STEP 3: APOS 기반 FDNO 재매핑 ===
    print("\n=== STEP 3: APOS 기반 전체 도면 FDNO 재매핑 ===")
    
    # APOS별로 그룹화
    apos_groups = defaultdict(list)
    for item in ALLCHK:
        apos_groups[item['APOS']].append(item)
    
    # APOS 그룹 요약 출력
    print("\n[APOS 그룹 요약]")
    print(f"총 {len(apos_groups)}개의 고유한 APOS 발견")
    for apos, group in sorted(apos_groups.items()):
        print(f"\nAPOS '{apos}': {len(group)}개 도면")
        for item in group:
            print(f"  - 초기 FDNO: {item['INITIAL_FDNO']}")
    
    # 최종 FDNO 매핑 테이블 생성 (path -> 최종 FDNO)
    final_fdno_mapping = {}
    fdno_change_log = {}  # 변경 내역 추적
    
    # APOS 기반으로 FDNO 재할당
    print("\n=== APOS 기반 FDNO 재할당 ===")
    
    # 각 APOS 그룹 처리
    for apos, group in sorted(apos_groups.items()):
        if len(group) >= 2:
            print(f"\nAPOS '{apos}' 그룹 처리 ({len(group)}개 도면)")
            
            # 그룹 내에서 가장 작은 FDNO를 기준으로 정렬
            sorted_group = sorted(group, key=lambda x: x['INITIAL_FDNO'])
            
            # 순환 매핑 생성 (A→B, B→C, ..., Z→A)
            for i in range(len(sorted_group)):
                current = sorted_group[i]
                next_idx = (i + 1) % len(sorted_group)
                next_item = sorted_group[next_idx]
                
                # 현재 도면은 다음 도면의 FDNO를 받음
                old_fdno = initial_fdno_mapping[current['PATH']]
                new_fdno = initial_fdno_mapping[next_item['PATH']]
                
                final_fdno_mapping[current['PATH']] = new_fdno
                
                if old_fdno != new_fdno:
                    fdno_change_log[current['PATH']] = {
                        'old': old_fdno,
                        'new': new_fdno,
                        'apos': apos
                    }
                    print(f"  {old_fdno} → {new_fdno}")
        else:
            # 그룹에 하나만 있으면 변경 없음
            item = group[0]
            final_fdno_mapping[item['PATH']] = item['INITIAL_FDNO']
    
    # 매핑되지 않은 도면들은 원래 FDNO 유지
    for path in file_paths:
        if path not in final_fdno_mapping:
            final_fdno_mapping[path] = initial_fdno_mapping.get(path, filename_base(path))
    
    # === STEP 4: 도면 내 모든 FDNO 업데이트 ===
    print("\n=== STEP 4: 도면 내 모든 FDNO 업데이트 ===")
    
    for path in file_paths:
        doc = doc_cache.get(path)
        index = index_cache.get(path)
        if not doc or not index:
            continue
        
        old_fdno = initial_fdno_mapping.get(path)
        new_fdno = final_fdno_mapping.get(path)
        
        if old_fdno and new_fdno and old_fdno != new_fdno:
            print(f"\n도면 {os.path.basename(path)} 업데이트:")
            print(f"  FDNO 변경: {old_fdno} → {new_fdno}")
            
            # 도면 내의 모든 FDNO 텍스트 업데이트
            update_count = update_fdno_in_drawing(doc, index, old_fdno, new_fdno)
            
            if update_count > 0:
                print(f"  총 {update_count}개 위치 업데이트 완료")
    
    # === STEP 5: APOS 기반 상호 참조 업데이트 ===
    print("\n=== STEP 5: APOS 기반 상호 참조 업데이트 ===")
    
    for apos, group in apos_groups.items():
        if len(group) >= 2:
            print(f"\nAPOS '{apos}' 그룹의 상호 참조 업데이트")
            
            # 그룹 내 모든 쌍에 대해 상호 참조 업데이트
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    a, b = group[i], group[j]
                    
                    # A 도면과 B 도면의 최종 FDNO 가져오기
                    final_fdno_a = final_fdno_mapping[a['PATH']]
                    final_fdno_b = final_fdno_mapping[b['PATH']]
                    
                    # A 도면의 CONT 아래 FDNO를 B의 최종 FDNO로 변경
                    doc_a = doc_cache.get(a['PATH'])
                    index_a = index_cache.get(a['PATH'])
                    if doc_a and index_a:
                        for entity_data in index_a.text_entities:
                            if abs(entity_data['x'] - a['AFDNO_X']) < 1 and \
                               abs(entity_data['y'] - a['AFDNO_Y']) < 1:
                                set_text(entity_data['entity'], final_fdno_b, color=2)
                                print(f"  {os.path.basename(a['PATH'])}: CONT 아래 → {final_fdno_b}")
                                break
                    
                    # B 도면의 CONT 아래 FDNO를 A의 최종 FDNO로 변경
                    doc_b = doc_cache.get(b['PATH'])
                    index_b = index_cache.get(b['PATH'])
                    if doc_b and index_b:
                        for entity_data in index_b.text_entities:
                            if abs(entity_data['x'] - b['AFDNO_X']) < 1 and \
                               abs(entity_data['y'] - b['AFDNO_Y']) < 1:
                                set_text(entity_data['entity'], final_fdno_a, color=2)
                                print(f"  {os.path.basename(b['PATH'])}: CONT 아래 → {final_fdno_a}")
                                break
    
    # === STEP 6: 최종 저장 ===
    print("\n=== STEP 6: 최종 저장 ===")
    
    saved_files = []
    for path in file_paths:
        doc = doc_cache.get(path)
        if not doc:
            try:
                doc = ezdxf.readfile(path)
            except Exception as e:
                print(f"[ERROR] {os.path.basename(path)} 재오픈 실패: {e}")
                continue
        
        # 최종 FDNO
        final_fdno = final_fdno_mapping.get(path, filename_base(path))
        
        # 파일 저장
        fix_path = os.path.join(os.path.dirname(path), f"{final_fdno}_FIX.dxf")
        saved = safe_save_dxf(doc, fix_path)
        if saved:
            saved_files.append({
                'original': os.path.basename(path),
                'saved_as': os.path.basename(saved),
                'fdno': final_fdno,
                'changed': path in fdno_change_log
            })
        else:
            print(f"[ERROR] {os.path.basename(path)} 저장 실패")
    
    # === 최종 결과 출력 ===
    print("\n=== 최종 저장 결과 요약 ===")
    print(f"{'원본 파일':<40} | {'저장된 파일':<40} | {'FDNO':<20} | {'변경 여부':<10}")
    print("-" * 120)
    
    for file_info in saved_files:
        change_status = "변경됨" if file_info['changed'] else "유지"
        print(f"{file_info['original']:<40} | {file_info['saved_as']:<40} | {file_info['fdno']:<20} | {change_status:<10}")
    
    print(f"\n총 {len(saved_files)}개 파일 저장 완료")
    
    # FDNO 변경 내역 상세 출력
    print("\n=== FDNO 변경 내역 상세 ===")
    for path, change_info in fdno_change_log.items():
        print(f"{os.path.basename(path)}: {change_info['old']} → {change_info['new']} (APOS: {change_info['apos']})")
    
    print(f"\n총 {len(fdno_change_log)}개 도면의 FDNO가 변경됨")
    
    print("\n==== 전체 작업 완료 ====")

if __name__ == "__main__":
    main()