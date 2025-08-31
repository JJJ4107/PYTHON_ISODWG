import os
import re
import ezdxf
import tkinter as tk
from tkinter import filedialog
from collections import defaultdict
import shutil
import tempfile
from typing import List, Dict, Tuple, Optional, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

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
class OptimizedEntityIndex:
    """최적화된 공간 인덱싱을 통한 빠른 엔티티 검색"""
    def __init__(self, msp=None):
        self.text_entities = []
        self.spatial_index = defaultdict(list)  # 그리드 기반 인덱스
        self.grid_size = 5  # 더 작은 그리드로 정밀도 향상
        self.cont_cache = []  # CONT 엔티티 캐시
        self.lineno_cache = None  # LINENO 캐시
        self.fabric_cache = []  # FABRICATION MATERIALS 영역 캐시
        
        if msp:
            self.build_index(msp)
    
    def build_index(self, msp):
        """인덱스 구축 - 한 번의 순회로 모든 정보 수집"""
        # 텍스트 엔티티 한 번만 순회
        for e in msp.query('TEXT MTEXT'):
            x, y = get_xy(e)
            txt = get_text(e)
            txt_upper = txt.upper()
            color = getattr(e.dxf, "color", 256)
            
            entity_data = {
                'entity': e,
                'x': x,
                'y': y,
                'text': txt,
                'text_upper': txt_upper,
                'color': color
            }
            
            self.text_entities.append(entity_data)
            
            # 그리드 인덱스에 추가
            grid_x = int(x // self.grid_size)
            grid_y = int(y // self.grid_size)
            self.spatial_index[(grid_x, grid_y)].append(entity_data)
            
            # 특수 엔티티 캐싱
            if ('CONT' in txt_upper and '.' in txt_upper) or ('CONN' in txt_upper and '.' in txt_upper):
                self.cont_cache.append(entity_data)
            
            # LINENO 캐싱
            if 0 <= x <= 150 and 0 <= y <= 85 and '-' in txt and len(txt) >= 10:
                txt_clean = clean_str(txt)
                self.lineno_cache = txt_clean
            
            # FABRICATION MATERIALS 영역 캐싱
            if 700 <= x <= 800 and 0 <= y <= 40 and '-' in txt and len(txt) > 10:
                self.fabric_cache.append(entity_data)
    
    def update_entity(self, entity_data, new_text=None, new_color=None):
        """엔티티 업데이트 및 인덱스 동기화"""
        if new_text is not None:
            entity_data['text'] = new_text
            entity_data['text_upper'] = new_text.upper()
            set_text(entity_data['entity'], new_text)
        if new_color is not None:
            entity_data['color'] = new_color
            if hasattr(entity_data['entity'], 'dxf'):
                entity_data['entity'].dxf.color = new_color
    
    def find_below_optimized(self, base_x: float, base_y: float, 
                            x_tol: float = 4, y_tol: float = 20, 
                            patt: Optional[str] = None, 
                            color: Optional[int] = None) -> List:
        """최적화된 아래쪽 엔티티 검색"""
        candidates = []
        
        # 검색할 그리드 범위 계산 (더 정밀한 그리드)
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
    
    def find_entities_at_position(self, target_x: float, target_y: float, tolerance: float = 1.0):
        """특정 위치의 엔티티 빠른 검색"""
        grid_x = int(target_x // self.grid_size)
        grid_y = int(target_y // self.grid_size)
        
        # 주변 그리드 포함 검색
        for dx in [-1, 0, 1]:
            for dy in [-1, 0, 1]:
                for entity_data in self.spatial_index[(grid_x + dx, grid_y + dy)]:
                    if (abs(entity_data['x'] - target_x) < tolerance and 
                        abs(entity_data['y'] - target_y) < tolerance):
                        return entity_data
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

def find_chain_below_optimized(index: OptimizedEntityIndex, cont_e, cont_x, cont_y, x_tol=4, y_tol=20):
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

# === 병렬 처리용 함수들 ===
def process_file_initial(args):
    """파일 초기 처리 (병렬 실행용)"""
    path, initial_fdno = args
    try:
        doc = ezdxf.readfile(path)
        msp = doc.modelspace()
        
        # 색상 변경
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
        
        # 인덱스 생성
        index = OptimizedEntityIndex(msp)
        
        return path, doc, index, True
    except Exception as e:
        print(f"  ✗ {os.path.basename(path)} 읽기 오류: {e}")
        return path, None, None, False

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
    
    # === STEP 1: FDNO 할당 (먼저!) ===
    print("=== STEP 1: FDNO 할당 시작 ===")
    
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
    
    # FDNO 계산 (벡터화된 연산)
    fdno_list = []
    initial_fdno_mapping = {}
    
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
            base_fn = dn - len(dn_files) + 1
            
            for idx, f in enumerate(sorted_files):
                # SHNO가 높을수록 높은 FDNO를 받음
                fn_num = base_fn + f['SHNO_NUM'] - 1  # SHNO가 1부터 시작하므로 -1
                f['FN'] = fn_num
                f['FDNO'] = f"{f['DALL']}-{fn_num:03d}"
                fdno_list.append(f)
                initial_fdno_mapping[f['path']] = f['FDNO']
                print(f"  {f['basename']}: DN={f['DN']}, SHNO={f['SHNO']} → FDNO={f['FDNO']}")
    
    print(f"\n총 {len(fdno_list)}개 도면에 FDNO 할당 완료")
    
    # === STEP 2: 도면 병렬 읽기 및 기본 색상 변경 ===
    print("\n=== STEP 2: 도면 병렬 읽기 및 초기 처리 ===")
    
    doc_cache = {}
    index_cache = {}
    
    # 병렬 처리로 파일 읽기
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        for path in file_paths:
            fdno = initial_fdno_mapping.get(path)
            futures.append(executor.submit(process_file_initial, (path, fdno)))
        
        for future in as_completed(futures):
            path, doc, index, success = future.result()
            if success:
                doc_cache[path] = doc
                index_cache[path] = index
                print(f"  ✓ {os.path.basename(path)} 읽기 완료")
    
    # === STEP 3: 초기 FDNO 적용 (CONT-DLNO 매핑과 X740 Y20 부근) ===
    print("\n=== STEP 3: 초기 FDNO 도면 적용 ===")
    
    yellow = 2
    all_linenos = []
    cont_dlno_map = []
    
    # (1) 전체 LINENO-FDNO 매핑 테이블 만들기 (캐시 활용)
    lineno_to_fdno = {}
    for f in fdno_list:
        index = index_cache.get(f['path'])
        if not index:
            continue
        
        # 캐시된 LINENO 사용
        if index.lineno_cache:
            lineno_to_fdno[index.lineno_cache] = f['FDNO']
            all_linenos.append((f['FDNO'], index.lineno_cache, None, os.path.basename(f['path'])))
    
    # (2) CONT-DLNO-FDNO 매핑 처리 및 FABRICATION MATERIALS 처리
    for f in fdno_list:
        doc = doc_cache.get(f['path'])
        index = index_cache.get(f['path'])
        if not doc or not index:
            continue
        msp = doc.modelspace()
        
        # 캐시된 LINENO 사용
        cur_lineno = index.lineno_cache
        if not cur_lineno:
            continue
        
        fdno_candidates = [
            fdno for fdno, lineno, _, _ in all_linenos if lineno == cur_lineno
        ]
        
        def fdno_sort_key(fdno):
            m = re.findall(r'\d+', fdno)
            return int(m[-1]) if m else 0
        
        fdno_sorted = sorted(fdno_candidates, key=fdno_sort_key)
        
        # CONT 엔티티 처리 (캐시 사용)
        for entity_data in index.cont_cache:
            txt = entity_data['text']
            x, y = entity_data['x'], entity_data['y']
            e = entity_data['entity']
            
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
            if dlno_e is not None and fdno_to_output:
                if is_digit:
                    # 숫자인 경우: 숫자를 FDNO로 대체 (CONT는 이동하지 않음)
                    try:
                        # 기존 숫자 텍스트를 FDNO로 변경
                        dlno_e.dxf.text = fdno_to_output
                        dlno_e.dxf.color = 2
                        print(f"    숫자 '{dlno_txt}' → FDNO '{fdno_to_output}'로 대체")
                    except:
                        pass
                    
                    # CONT는 그대로 두고 색상만 변경
                    if cont_entity is not None:
                        try:
                            cont_entity.dxf.color = 2
                        except:
                            pass
                else:
                    # 라인번호인 경우: 기존 방식대로 처리 (CONT 이동 및 FDNO 추가)
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
            
            # 매핑 정보 저장
            if fdno_to_output:
                cont_dlno_map.append((txt, dlno_txt, fdno_to_output, (cont_x, cont_y), is_digit))
        
        # FABRICATION MATERIALS 처리 (캐시 사용)
        if index.fabric_cache:
            entity_data = index.fabric_cache[0]  # 첫 번째 항목만
            txt = entity_data['text'].strip()
            x, y = entity_data['x'], entity_data['y']
            
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
            
            print(f"  ✓ {os.path.basename(f['path'])}: FABRICATION MATERIALS 영역 FDNO 업데이트 → {f['FDNO']}")
    
    print(f"\n초기 FDNO 적용 완료")
    
    # === STEP 4: 인덱스 재생성 및 APOS 수집 (FDNO 적용 후!) ===
    print("\n=== STEP 4: APOS 수집 (FDNO 적용 후) ===")
    
    # 인덱스 재생성 (FDNO가 업데이트된 상태를 반영) - 병렬 처리
    print("\n[인덱스 병렬 재생성 중...]")
    
    def rebuild_index(path):
        doc = doc_cache.get(path)
        if doc:
            msp = doc.modelspace()
            return path, OptimizedEntityIndex(msp)
        return path, None
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(rebuild_index, path) for path in file_paths]
        for future in as_completed(futures):
            path, new_index = future.result()
            if new_index:
                index_cache[path] = new_index
    
    # APOS 정보 수집 (캐시된 CONT 사용)
    ALLCHK = []
    apos_extraction_count = 0
    
    print("\n[APOS 추출 중...]")
    for path in file_paths:
        doc = doc_cache.get(path)
        index = index_cache.get(path)
        if not doc or not index:
            continue
        
        current_fdno = initial_fdno_mapping.get(path)
        
        # CONT 엔티티 찾기 및 APOS 추출 (캐시 사용)
        for entity_data in index.cont_cache:
            txt = entity_data['text_upper']
            cont_x, cont_y = entity_data['x'], entity_data['y']
            
            # CONT 아래 체인 찾기
            chain = find_chain_below_optimized(index, entity_data['entity'], cont_x, cont_y)
            if not chain:
                continue
            
            # AFDNO 검색 (이제 업데이트된 FDNO를 찾음)
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
                        'PATH': path,
                        'FILENAME': os.path.basename(path),
                        'FDNO': current_fdno,
                        'AFDNO': afdno,
                        'ADLNO': adlno,
                        'APOS': apos,
                        'CONT_X': cont_x,
                        'CONT_Y': cont_y,
                        'AFDNO_X': afdno_x,
                        'AFDNO_Y': afdno_y
                    })
                    apos_extraction_count += 1
                    print(f"  ✓ FDNO={current_fdno}: APOS='{apos}', AFDNO='{afdno}' 추출")
                    break  # 첫 번째 AFDNO만 처리
    
    print(f"\n총 {apos_extraction_count}개의 APOS 정보 추출 완료")
    
    # === STEP 5: APOS 기반 분석 (FDNO 재매핑은 하지 않음) ===
    print("\n=== STEP 5: APOS 기반 분석 ===")
    
    # APOS별로 그룹화
    apos_groups = defaultdict(list)
    for item in ALLCHK:
        apos_groups[item['APOS']].append(item)
    
    # APOS 그룹 요약 출력
    print("\n" + "="*100)
    print("[APOS 수집 결과]")
    print("="*100)
    print(f"총 {len(apos_groups)}개의 고유한 APOS 발견")
    
    # 디버깅: 모든 도면의 APOS 정보 출력
    print("\n[전체 도면 APOS 매핑 정보]")
    print(f"{'FDNO':<30} {'AFDNO':<30} {'APOS':<25} {'파일명':<40}")
    print("-"*125)
    for item in sorted(ALLCHK, key=lambda x: x['FDNO']):
        print(f"{item['FDNO']:<30} {item['AFDNO']:<30} {item['APOS']:<25} {os.path.basename(item['PATH']):<40}")
    
    print("\n[APOS 그룹별 상세]")
    for apos, group in sorted(apos_groups.items()):
        print(f"\n● APOS '{apos}' ({len(group)}개 도면)")
        if len(group) >= 2:
            print("  ▶ 상호 참조 대상:")
        else:
            print("  ▶ 단독 (참조 없음):")
        for item in sorted(group, key=lambda x: x['FDNO']):
            print(f"    - FDNO: {item['FDNO']:<25} AFDNO: {item['AFDNO']:<25} 파일: {os.path.basename(item['PATH'])}")
    
    # === STEP 6: APOS 기반 CONT 아래 상호 참조만 업데이트 (최적화) ===
    print("\n=== STEP 6: APOS 기반 CONT 아래 상호 참조 업데이트 ===")
    
    # APOS 그룹별로 상호 참조 업데이트
    reference_updates = []
    
    for apos, group in apos_groups.items():
        if len(group) >= 2:
            print(f"\nAPOS '{apos}' 그룹의 CONT 아래 상호 참조 업데이트")
            
            # 그룹 내에서 순환 참조 생성
            for i in range(len(group)):
                current = group[i]
                next_idx = (i + 1) % len(group)
                next_item = group[next_idx]
                
                # 현재 도면의 CONT 아래 AFDNO를 다음 도면의 FDNO로 변경
                index = index_cache.get(current['PATH'])
                
                if index:
                    # 위치 기반 빠른 검색
                    entity_data = index.find_entities_at_position(
                        current['AFDNO_X'], current['AFDNO_Y'], tolerance=1.0
                    )
                    
                    if entity_data:
                        old_text = entity_data['text']
                        new_text = next_item['FDNO']
                        
                        # CONT 아래 텍스트만 변경
                        index.update_entity(entity_data, new_text=new_text, new_color=2)
                        
                        reference_updates.append({
                            'file': os.path.basename(current['PATH']),
                            'fdno': current['FDNO'],
                            'old_ref': old_text,
                            'new_ref': new_text,
                            'apos': apos,
                            'position': f"({current['AFDNO_X']:.1f},{current['AFDNO_Y']:.1f})"
                        })
                        
                        print(f"  ✓ {os.path.basename(current['PATH'])}: CONT 아래 '{old_text}' → '{new_text}'")
    
    # 참조 업데이트 요약
    if reference_updates:
        print("\n" + "="*120)
        print("[CONT 아래 상호 참조 업데이트 요약]")
        print("="*120)
        print(f"{'도면 FDNO':<25} {'변경 전':<25} {'변경 후':<25} {'APOS':<15} {'위치':<20}")
        print("-" * 120)
        for update in sorted(reference_updates, key=lambda x: x['fdno']):
            print(f"{update['fdno']:<25} {update['old_ref']:<25} {update['new_ref']:<25} {update['apos']:<15} {update['position']:<20}")
        print(f"\n총 {len(reference_updates)}개의 CONT 아래 참조 업데이트 완료")
    
    # === STEP 7: 최종 저장 (병렬 처리) ===
    print("\n=== STEP 7: 최종 저장 (병렬 처리) ===")
    
    def save_file(args):
        path, fdno = args
        doc = doc_cache.get(path)
        if not doc:
            try:
                doc = ezdxf.readfile(path)
            except Exception as e:
                return None
        
        fix_path = os.path.join(os.path.dirname(path), f"{fdno}_FIX.dxf")
        saved = safe_save_dxf(doc, fix_path)
        if saved:
            return {
                'original': os.path.basename(path),
                'saved_as': os.path.basename(saved),
                'fdno': fdno,
                'path': path
            }
        return None
    
    saved_files = []
    save_args = [(path, initial_fdno_mapping.get(path, filename_base(path))) for path in file_paths]
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(save_file, args) for args in save_args]
        for future in as_completed(futures):
            result = future.result()
            if result:
                saved_files.append(result)
    
    # === 최종 결과 출력 ===
    print("\n" + "="*120)
    print("[최종 저장 결과 요약]")
    print("="*120)
    print(f"{'원본 파일':<40} | {'저장된 파일':<40} | {'FDNO':<30}")
    print("-" * 120)
    
    for file_info in sorted(saved_files, key=lambda x: x['fdno']):
        print(f"{file_info['original']:<40} | {file_info['saved_as']:<40} | {file_info['fdno']:<30}")
    
    print(f"\n총 {len(saved_files)}개 파일 저장 완료")
    
    # APOS 그룹 및 상호 참조 최종 요약
    print("\n" + "="*120)
    print("[APOS 그룹 및 상호 참조 최종 요약]")
    print("="*120)
    
    # APOS 그룹 통계
    single_groups = sum(1 for g in apos_groups.values() if len(g) == 1)
    multi_groups = sum(1 for g in apos_groups.values() if len(g) >= 2)
    total_multi_drawings = sum(len(g) for g in apos_groups.values() if len(g) >= 2)
    
    print(f"• 단독 APOS 그룹: {single_groups}개")
    print(f"• 상호 참조 APOS 그룹: {multi_groups}개 (총 {total_multi_drawings}개 도면)")
    print(f"• CONT 아래 참조 업데이트: {len(reference_updates)}개")
    
    print("\n[주요 변경 사항]")
    print("• X740 Y20 부근 FDNO: 초기 할당된 FDNO 유지 (변경 안 됨)")
    print("• 파일명: 초기 할당된 FDNO 사용 (변경 안 됨)")
    print("• CONT 아래 참조: APOS 기반 상호 참조로 업데이트됨")
    
    print("\n[성능 최적화]")
    print("• 공간 인덱싱: 그리드 크기 5로 정밀도 향상")
    print("• 병렬 처리: 파일 읽기/쓰기 4개 스레드")
    print("• 캐싱: CONT, LINENO, FABRIC 영역 사전 캐싱")
    print("• 위치 기반 검색: O(1) 엔티티 접근")
    
    print("\n==== 전체 작업 완료 ====")

if __name__ == "__main__":
    main()