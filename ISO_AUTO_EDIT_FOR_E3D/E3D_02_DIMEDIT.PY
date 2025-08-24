import os
import sys
import ezdxf
import math
import numpy as np
from ezdxf.entities import Line, LWPolyline, Polyline, Text
import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk

# ─────────────── 설정 값 ───────────────
ANGLE_TOLERANCE = 5.0  # 각도 허용 오차 (°)
DIM_LAYER_PREFIXES = ("GT_", "PL2")  # 치수선 레이어 접두사들

# TBOX 캐시를 위한 전역 딕셔너리
TBOX_CACHE = {}

# ─────────────── 파일 선택 GUI ───────────────
def select_dxf_files():
    """
    Windows 파일 선택 다이얼로그를 열어 DXF 파일들을 선택
    Returns: 선택된 파일 경로들의 리스트
    """
    root = tk.Tk()
    root.withdraw()
    
    file_paths = filedialog.askopenfilenames(
        title="DXF 파일을 선택하세요 (여러 개 선택 가능)",
        filetypes=[
            ("DXF files", "*.dxf"),
            ("All files", "*.*")
        ],
        multiple=True
    )
    
    root.destroy()
    return list(file_paths)

def show_progress_window(total_files):
    """
    진행 상황을 보여주는 프로그레스 윈도우 생성
    """
    progress_window = tk.Tk()
    progress_window.title("DXF 처리 진행 상황")
    progress_window.geometry("500x150")
    progress_window.resizable(False, False)
    
    progress_window.eval('tk::PlaceWindow . center')
    
    label = tk.Label(progress_window, text="DXF 파일을 처리 중입니다...", font=("Arial", 12))
    label.pack(pady=10)
    
    file_label = tk.Label(progress_window, text="", font=("Arial", 10), fg="blue")
    file_label.pack(pady=5)
    
    progress_var = tk.DoubleVar()
    progress_bar = ttk.Progressbar(
        progress_window, 
        variable=progress_var, 
        maximum=total_files, 
        length=400,
        mode='determinate'
    )
    progress_bar.pack(pady=10)
    
    progress_text = tk.Label(progress_window, text=f"0 / {total_files}", font=("Arial", 10))
    progress_text.pack()
    
    progress_window.update()
    
    return progress_window, progress_var, file_label, progress_text

def update_progress(window, progress_var, file_label, progress_text, current, total, current_file):
    """
    프로그레스 업데이트
    """
    if window and window.winfo_exists():
        progress_var.set(current)
        file_label.config(text=f"처리 중: {os.path.basename(current_file)}")
        progress_text.config(text=f"{current} / {total}")
        window.update()

def close_progress_window(window):
    """
    프로그레스 윈도우 닫기
    """
    if window and window.winfo_exists():
        window.destroy()

# ─────────────── 유틸 함수 ───────────────
def to2d(pt):
    if hasattr(pt, "__getitem__"):
        return np.array((pt[0], pt[1]), float)
    return np.array((pt.x, pt.y), float)

def distance(a, b):
    return float(np.linalg.norm(a - b))

def angle_deg(a, b):
    dx, dy = b - a
    return (math.degrees(math.atan2(dy, dx)) + 360) % 360

def get_entity_handle(entity):
    """
    엔티티의 핸들을 안전하게 가져오는 함수
    """
    try:
        if hasattr(entity, 'dxf') and hasattr(entity.dxf, 'handle'):
            return entity.dxf.handle
        elif hasattr(entity, 'handle'):
            return entity.handle
        else:
            return str(id(entity))  # 마지막 수단으로 객체 ID 사용
    except:
        return "unknown"

def extract_segments(ent):
    if isinstance(ent, Line):
        return [(ent.dxf.start, ent.dxf.end)]
    if isinstance(ent, LWPolyline):
        pts = list(ent.get_points("xyb"))
        z = ent.dxf.elevation
        return [
            ((x0, y0, z), (x1, y1, z)) for (x0, y0, _), (x1, y1, _) in zip(pts, pts[1:])
        ]
    if isinstance(ent, Polyline):
        verts = list(ent.vertices)
        return [
            (verts[i].dxf.location, verts[i + 1].dxf.location)
            for i in range(len(verts) - 1)
        ]
    return []

def is_enclosed(point, msp):
    """
    주어진 점이 닫힌 영역(폴리곤) 내부에 있는지 확인
    """
    x, y = float(point[0]), float(point[1])
    
    for entity in msp.query("LWPOLYLINE POLYLINE"):
        if not entity.is_closed:
            continue
            
        if hasattr(entity, 'get_points'):
            points = list(entity.get_points("xy"))
        else:
            points = [(v.dxf.location[0], v.dxf.location[1]) for v in entity.vertices]
        
        if len(points) < 3:
            continue
            
        if point_in_polygon(x, y, points):
            return True
    
    return False

def point_in_polygon(x, y, polygon_points):
    """
    Ray casting 알고리즘을 사용하여 점이 폴리곤 내부에 있는지 확인
    """
    n = len(polygon_points)
    inside = False
    
    p1x, p1y = polygon_points[0]
    for i in range(1, n + 1):
        p2x, p2y = polygon_points[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    
    return inside

def point_to_line_distance(point, line_start, line_end):
    """
    점에서 선분까지의 최단 거리를 계산
    """
    line_vec = line_end - line_start
    line_length_sq = np.dot(line_vec, line_vec)
    
    if line_length_sq == 0:
        return distance(point, line_start)
    
    point_vec = point - line_start
    t = np.dot(point_vec, line_vec) / line_length_sq
    t = max(0, min(1, t))
    closest_point = line_start + t * line_vec
    
    return distance(point, closest_point)

# ─────────────── TBOX 관련 함수 ───────────────
def get_text_key(txt):
    """
    텍스트 엔티티의 고유 키를 생성
    """
    try:
        handle = get_entity_handle(txt)
        if hasattr(txt.dxf, 'insert'):
            pos = txt.dxf.insert
            return f"{handle}_{pos[0]}_{pos[1]}"
        return handle
    except:
        return str(id(txt))

def create_tbox(txt):
    """
    텍스트에 대한 TBOX를 생성하고 캐시에 저장
    """
    text_key = get_text_key(txt)
    
    # 이미 TBOX가 생성되어 있다면 캐시에서 반환
    if text_key in TBOX_CACHE:
        return TBOX_CACHE[text_key]
    
    # 텍스트 위치
    if hasattr(txt.dxf, 'insert') and txt.dxf.insert is not None:
        txt_pt = to2d(txt.dxf.insert)
    elif hasattr(txt.dxf, 'align_point') and txt.dxf.align_point is not None:
        txt_pt = to2d(txt.dxf.align_point)
    else:
        return None
    
    # 텍스트 크기
    text_length, text_height = get_text_dimensions(txt)
    
    # TBOX 생성 (원래 위치 기준)
    tbox_left = txt_pt[0]
    tbox_right = txt_pt[0] + text_length
    tbox_bottom = txt_pt[1]
    tbox_top = txt_pt[1] + text_height
    
    # TBOX를 +X 방향으로 X값/2 만큼 이동
    move_x = text_length / 2.0
    tbox_left += move_x
    tbox_right += move_x
    
    # 이동된 TBOX의 4개 코너점
    tbox_corners = [
        np.array([tbox_left, tbox_bottom]),   # 좌하
        np.array([tbox_right, tbox_bottom]),  # 우하
        np.array([tbox_right, tbox_top]),     # 우상
        np.array([tbox_left, tbox_top])       # 좌상
    ]
    
    # TBOX 정보를 캐시에 저장
    tbox_info = {
        'corners': tbox_corners,
        'left': tbox_left,
        'right': tbox_right,
        'bottom': tbox_bottom,
        'top': tbox_top,
        'text_length': text_length,
        'text_height': text_height,
        'original_position': txt_pt
    }
    
    TBOX_CACHE[text_key] = tbox_info
    
    return tbox_info

def clear_tbox_cache():
    """
    TBOX 캐시 초기화
    """
    global TBOX_CACHE
    TBOX_CACHE = {}

# ─────────────── DB1, CH1 시스템 함수들 ───────────────
def find_dim_pairs_optimized(all_line_entities):
    """
    DIM1, DIM2 쌍을 찾는 함수 (최적화된 버전 - 미리 필터링된 엔티티 사용)
    """
    two_point_entities = []
    
    for ent in all_line_entities:
        if not ent.dxf.layer.startswith(DIM_LAYER_PREFIXES):
            continue
            
        segments = extract_segments(ent)
        if len(segments) != 1:
            continue
            
        p0, p1 = segments[0]
        v0, v1 = to2d(p0), to2d(p1)
        length = distance(v0, v1)
        
        if 1.5 <= length <= 12:
            two_point_entities.append((ent, v0, v1, length))
    
    dim_pairs = []
    overlapped_entities = []
    close_tolerance = 0.2
    far_threshold = 3.0
    tolerance_len = 0.5
    
    for i in range(len(two_point_entities)):
        for j in range(i + 1, len(two_point_entities)):
            ent1, v0_1, v1_1, len1 = two_point_entities[i]
            ent2, v0_2, v1_2, len2 = two_point_entities[j]
            
            length_diff = abs(len1 - len2)
            if length_diff > tolerance_len:
                continue
            
            connection_cases = [
                (v0_1, v0_2, v1_1, v1_2, "v0_1-v0_2"),
                (v0_1, v1_2, v1_1, v0_2, "v0_1-v1_2"),
                (v1_1, v0_2, v0_1, v1_2, "v1_1-v0_2"),
                (v1_1, v1_2, v0_1, v0_2, "v1_1-v1_2"),
            ]
            
            valid_pair_found = False
            overlap_found = False
            
            for close_pt1, close_pt2, far_pt1, far_pt2, case_name in connection_cases:
                close_dist = distance(close_pt1, close_pt2)
                far_dist = distance(far_pt1, far_pt2)
                
                if close_dist <= close_tolerance:
                    if far_dist <= close_tolerance:
                        if ent1 not in overlapped_entities:
                            ent1.dxf.color = 3
                            overlapped_entities.append(ent1)
                        if ent2 not in overlapped_entities:
                            ent2.dxf.color = 3
                            overlapped_entities.append(ent2)
                        overlap_found = True
                        break
                    elif far_dist >= far_threshold:
                        if case_name == "v0_1-v0_2":
                            vec1 = v1_1 - v0_1
                            vec2 = v1_2 - v0_2
                            dim1_common, dim1_opposite = v0_1, v1_1
                            dim2_common, dim2_opposite = v0_2, v1_2
                        elif case_name == "v0_1-v1_2":
                            vec1 = v1_1 - v0_1
                            vec2 = v0_2 - v1_2
                            dim1_common, dim1_opposite = v0_1, v1_1
                            dim2_common, dim2_opposite = v1_2, v0_2
                        elif case_name == "v1_1-v0_2":
                            vec1 = v0_1 - v1_1
                            vec2 = v1_2 - v0_2
                            dim1_common, dim1_opposite = v1_1, v0_1
                            dim2_common, dim2_opposite = v0_2, v1_2
                        else:
                            vec1 = v0_1 - v1_1
                            vec2 = v0_2 - v1_2
                            dim1_common, dim1_opposite = v1_1, v0_1
                            dim2_common, dim2_opposite = v1_2, v0_2
                        
                        dot_product = np.dot(vec1, vec2)
                        
                        if dot_product < 0:
                            if ent1 not in overlapped_entities and ent2 not in overlapped_entities:
                                dim_pairs.append({
                                    'DIM1': ent1, 'DIM1_common': dim1_common, 'DIM1_opposite': dim1_opposite,
                                    'DIM2': ent2, 'DIM2_common': dim2_common, 'DIM2_opposite': dim2_opposite,
                                    'common_point': (close_pt1 + close_pt2) / 2,
                                    'length': (len1 + len2) / 2
                                })
                                valid_pair_found = True
                                break
                
                if valid_pair_found or overlap_found:
                    break
            
            if not overlap_found and not valid_pair_found:
                reverse_dist1 = distance(v0_1, v1_2)
                reverse_dist2 = distance(v1_1, v0_2)
                
                if reverse_dist1 <= close_tolerance and reverse_dist2 <= close_tolerance:
                    if ent1 not in overlapped_entities:
                        ent1.dxf.color = 3
                        overlapped_entities.append(ent1)
                    if ent2 not in overlapped_entities:
                        ent2.dxf.color = 3
                        overlapped_entities.append(ent2)
                    overlap_found = True
    
    return dim_pairs, overlapped_entities

def find_arrow_entities_optimized(all_line_entities, point, tolerance=0.5):
    """
    최적화된 버전 - 미리 필터링된 엔티티에서 3점 폴리라인 찾기
    AD1, AD2 전용 - DIM_LAYER_PREFIXES 레이어에서만 찾음
    """
    arrows = []
    
    for ent in all_line_entities:
        # AD1, AD2는 DIM_LAYER_PREFIXES로 시작하는 레이어에서만 찾음
        if not ent.dxf.layer.startswith(DIM_LAYER_PREFIXES):
            continue
            
        try:
            if isinstance(ent, LWPolyline):
                points = list(ent.get_points("xy"))
            elif isinstance(ent, Polyline):
                points = [v.dxf.location for v in ent.vertices]
            else:
                continue
            
            if len(points) != 3:
                continue
            
            pts = [to2d(p) for p in points]
            min_dist_to_point = min(distance(pt, point) for pt in pts)
            
            if min_dist_to_point <= tolerance:
                arrows.append(ent)
        except Exception as e:
            continue
    
    return arrows

def find_ad3_entities_optimized(all_line_entities, dim_pair, ad1_entities, ad2_entities, tolerance=0.5):
    """
    최적화된 버전 - 미리 필터링된 엔티티에서 AD3 찾기
    수정: ARROW 레이어도 포함, DIM1/DIM2 끝점 근처 엔티티는 제외
    CP(공통점) 근처의 3점 ARROW 폴리라인도 AD3로 분류
    """
    ad3_candidates = []
    common_point = dim_pair['common_point']
    
    # DIM1, DIM2의 양끝점 수집 (AD1, AD2 보호를 위해)
    dim1_common = dim_pair['DIM1_common']
    dim1_opposite = dim_pair['DIM1_opposite']
    dim2_common = dim_pair['DIM2_common']
    dim2_opposite = dim_pair['DIM2_opposite']
    
    # DIM 끝점들 (AD1, AD2가 위치하는 곳)
    dim_far_endpoints = [dim1_opposite, dim2_opposite]  # AD1, AD2 위치
    
    # AD1, AD2의 핸들 수집
    excluded_handles = set()
    for ad1 in ad1_entities:
        excluded_handles.add(get_entity_handle(ad1))
    for ad2 in ad2_entities:
        excluded_handles.add(get_entity_handle(ad2))
    
    for ent in all_line_entities:
        # DIM_LAYER_PREFIXES 또는 ARROW 레이어 체크
        if not (ent.dxf.layer.startswith(DIM_LAYER_PREFIXES) or ent.dxf.layer.upper() == "ARROW"):
            continue
            
        # 이미 제외된 핸들인지 확인
        if get_entity_handle(ent) in excluded_handles:
            continue
            
        try:
            if isinstance(ent, LWPolyline):
                points = list(ent.get_points("xy"))
            elif isinstance(ent, Polyline):
                points = [v.dxf.location for v in ent.vertices]
            else:
                continue
            
            if len(points) != 3:
                continue
            
            pts = [to2d(p) for p in points]
            
            # ARROW 레이어인 경우, DIM의 반대편 끝점(AD1, AD2 위치) 근처에 있는지 확인
            if ent.dxf.layer.upper() == "ARROW":
                is_near_far_endpoint = False
                for pt in pts:
                    for far_endpoint in dim_far_endpoints:
                        if distance(pt, far_endpoint) <= 0.5:  # AD1, AD2 위치에서 0.5mm 이내
                            is_near_far_endpoint = True
                            break
                    if is_near_far_endpoint:
                        break
                
                # AD1, AD2 위치 근처의 ARROW는 제외
                if is_near_far_endpoint:
                    continue
            
            # 공통점(CP)과의 거리 확인
            min_dist_to_cp = min(distance(pt, common_point) for pt in pts)
            
            if min_dist_to_cp <= tolerance:
                ad3_candidates.append((ent, min_dist_to_cp))
        except Exception as e:
            continue
    
    if ad3_candidates:
        ad3_candidates.sort(key=lambda x: x[1])
        return [ad3_candidates[0][0]]
    
    return []

def find_ad3_touching_dims(all_line_entities, dim1_ent, dim2_ent, ad1_entities, ad2_entities, tolerance=0.2):
    """
    DIM1이나 DIM2 선분에 접하는 AD3 엔티티들을 찾는 함수 (AD1, AD2 제외)
    수정: ARROW 레이어만 대상으로, 0.2mm 이내 접촉, DIM 끝점 근처 제외
    """
    touching_ad3 = []
    
    # DIM1, DIM2 선분 정보 추출
    dim1_segments = extract_segments(dim1_ent)
    dim2_segments = extract_segments(dim2_ent)
    
    if not dim1_segments or not dim2_segments:
        return []
    
    dim1_start, dim1_end = to2d(dim1_segments[0][0]), to2d(dim1_segments[0][1])
    dim2_start, dim2_end = to2d(dim2_segments[0][0]), to2d(dim2_segments[0][1])
    
    # DIM 끝점들 (AD1, AD2 보호용)
    dim_endpoints = [dim1_start, dim1_end, dim2_start, dim2_end]
    
    # DIM1, DIM2, AD1, AD2 제외
    excluded_handles = {get_entity_handle(dim1_ent), get_entity_handle(dim2_ent)}
    
    # AD1, AD2 핸들 추가하여 삭제 대상에서 제외
    for ad1 in ad1_entities:
        excluded_handles.add(get_entity_handle(ad1))
    for ad2 in ad2_entities:
        excluded_handles.add(get_entity_handle(ad2))
    
    for ent in all_line_entities:
        # ARROW 레이어만 체크 (DIM 선분에 접하는 AD3는 주로 ARROW 레이어)
        if ent.dxf.layer.upper() != "GT_1":
            continue
            
        if get_entity_handle(ent) in excluded_handles:
            continue
            
        try:
            # 3점 폴리라인인지 확인
            if isinstance(ent, LWPolyline):
                points = list(ent.get_points("xy"))
            elif isinstance(ent, Polyline):
                points = [v.dxf.location for v in ent.vertices]
            else:
                continue
            
            if len(points) != 3:
                continue
            
            pts = [to2d(p) for p in points]
            
            # DIM 끝점 근처에 있는지 확인 (AD1, AD2 보호)
            is_near_endpoint = False
            for pt in pts:
                for endpoint in dim_endpoints:
                    if distance(pt, endpoint) <= 0.5:  # DIM 끝점에서 0.5mm 이내
                        is_near_endpoint = True
                        break
                if is_near_endpoint:
                    break
            
            # DIM 끝점 근처의 ARROW는 AD1 또는 AD2일 가능성이 높으므로 제외
            if is_near_endpoint:
                continue
            
            # AD3의 각 점이 DIM1 또는 DIM2 선분에 접하는지 확인
            is_touching = False
            
            for pt in pts:
                # DIM1 선분까지의 거리
                dist_to_dim1 = point_to_line_distance(pt, dim1_start, dim1_end)
                # DIM2 선분까지의 거리
                dist_to_dim2 = point_to_line_distance(pt, dim2_start, dim2_end)
                
                # 0.2mm 이내로 접촉하는지 확인
                if dist_to_dim1 <= tolerance or dist_to_dim2 <= tolerance:
                    is_touching = True
                    break
            
            if is_touching:
                touching_ad3.append(ent)
        except Exception as e:
            continue
    
    return touching_ad3

def find_arrow_lines_touching_ad3(all_line_entities, ad3_entities, tolerance=0.1):
    """
    삭제될 AD3 엔티티의 점에 접하고, ARROW 레이어이며, 1mm 이하인 LINE을 찾는 함수
    """
    arrow_lines_to_delete = []
    
    # AD3 엔티티들의 모든 점 수집
    ad3_points = []
    for ad3 in ad3_entities:
        try:
            if isinstance(ad3, LWPolyline):
                points = list(ad3.get_points("xy"))
            elif isinstance(ad3, Polyline):
                points = [v.dxf.location for v in ad3.vertices]
            else:
                continue
            
            for p in points:
                ad3_points.append(to2d(p))
        except Exception as e:
            continue
    
    # ARROW 레이어의 LINE 엔티티 검색
    for ent in all_line_entities:
        if not isinstance(ent, Line):
            continue
        
        if ent.dxf.layer.upper() != "ARROW":
            continue
        
        try:
            # LINE의 길이 계산
            segments = extract_segments(ent)
            if not segments:
                continue
            
            p0, p1 = segments[0]
            v0, v1 = to2d(p0), to2d(p1)
            line_length = distance(v0, v1)
            
            # 1mm 이하인지 확인
            if line_length > 1.0:
                continue
            
            # AD3 점들과의 거리 확인
            is_touching_ad3 = False
            for ad3_pt in ad3_points:
                # LINE의 양 끝점이 AD3 점에 접하는지 확인
                if distance(v0, ad3_pt) <= tolerance or distance(v1, ad3_pt) <= tolerance:
                    is_touching_ad3 = True
                    break
            
            if is_touching_ad3:
                arrow_lines_to_delete.append(ent)
        except Exception as e:
            continue
    
    return arrow_lines_to_delete

def find_g1_entities_optimized_with_all_dims(all_line_entities, dim1_ent, dim2_ent, dim_pair, all_used_dim_handles, tolerance=0.2):
    """
    최적화된 버전 - 미리 필터링된 엔티티에서 G1 찾기
    모든 DIM으로 사용된 엔티티들을 제외
    """
    g1_candidates = []
    
    dim1_segments = extract_segments(dim1_ent)
    dim2_segments = extract_segments(dim2_ent)
    
    if not dim1_segments or not dim2_segments:
        return []
    
    dim1_start, dim1_end = to2d(dim1_segments[0][0]), to2d(dim1_segments[0][1])
    dim2_start, dim2_end = to2d(dim2_segments[0][0]), to2d(dim2_segments[0][1])
    
    common_point = dim_pair['common_point']
    dim1_common = dim_pair['DIM1_common']
    dim1_opposite = dim_pair['DIM1_opposite']
    dim2_common = dim_pair['DIM2_common'] 
    dim2_opposite = dim_pair['DIM2_opposite']
    
    for ent in all_line_entities:
        if not ent.dxf.layer.startswith(DIM_LAYER_PREFIXES):
            continue
        
        # 🔴 모든 DIM으로 사용된 엔티티 제외 (현재 DIM 쌍뿐만 아니라 모든 DIM)
        if get_entity_handle(ent) in all_used_dim_handles:
            continue
            
        segments = extract_segments(ent)
        if len(segments) != 1:
            continue
        
        p0, p1 = segments[0]
        v0, v1 = to2d(p0), to2d(p1)
        
        min_dist_to_far_ends = min(
            distance(v0, dim1_opposite), distance(v1, dim1_opposite),
            distance(v0, dim2_opposite), distance(v1, dim2_opposite)
        )
        
        far_end_exclusion_distance = 0.5
        if min_dist_to_far_ends <= far_end_exclusion_distance:
            continue
        
        min_dist_to_valid_area = float('inf')
        
        for g1_pt in [v0, v1]:
            dist_to_common = distance(g1_pt, common_point)
            if dist_to_common < min_dist_to_valid_area:
                min_dist_to_valid_area = dist_to_common
        
        for g1_pt in [v0, v1]:
            dist_to_dim1_common = distance(g1_pt, dim1_common)
            dist_to_dim1_line = point_to_line_distance(g1_pt, dim1_start, dim1_end)
            min_dist_dim1 = min(dist_to_dim1_common, dist_to_dim1_line)
            
            if min_dist_dim1 < min_dist_to_valid_area:
                min_dist_to_valid_area = min_dist_dim1
        
        for g1_pt in [v0, v1]:
            dist_to_dim2_common = distance(g1_pt, dim2_common)
            dist_to_dim2_line = point_to_line_distance(g1_pt, dim2_start, dim2_end)
            min_dist_dim2 = min(dist_to_dim2_common, dist_to_dim2_line)
            
            if min_dist_dim2 < min_dist_to_valid_area:
                min_dist_to_valid_area = min_dist_dim2
        
        if min_dist_to_valid_area <= tolerance:
            g1_candidates.append((ent, v0, v1, min_dist_to_valid_area))
    
    if g1_candidates:
        g1_candidates.sort(key=lambda x: x[3])
        closest_g1 = g1_candidates[0]
        return [(closest_g1[0], closest_g1[1], closest_g1[2])]
    
    return []

def find_ct_texts(msp, g1_entities, text_entities, dim_pair, search_radius=10.0):
    """
    G1 끝점에서 50mm 내에서 기울기 0이고 50보다 큰 숫자 TEXT를 찾아
    TBOX를 만들고 +X로 TBOX X값/2 만큼 이동한 후
    CP에서 먼 G1 점이 TBOX의 4점 중 가장 가까운 TBOX 안의 TEXT를 CT로 선택
    """
    ct_texts = []
    
    common_point = dim_pair['common_point']
    
    for g1_ent, v0, v1 in g1_entities:
        # CP에서 더 먼 G1 끝점 찾기
        dist_to_common_v0 = distance(v0, common_point)
        dist_to_common_v1 = distance(v1, common_point)
        
        if dist_to_common_v0 > dist_to_common_v1:
            search_point = v0
        else:
            search_point = v1
        
        candidates = []
        
        for txt in text_entities:
            try:
                # RED 텍스트 제외
                if hasattr(txt.dxf, 'color') and txt.dxf.color == 1:
                    continue
                
                # WDNO 레이어 제외
                if hasattr(txt.dxf, 'layer') and 'WDNO' in txt.dxf.layer.upper():
                    continue
                
                # 텍스트 위치 가져오기
                if hasattr(txt.dxf, 'insert') and txt.dxf.insert is not None:
                    txt_pt = to2d(txt.dxf.insert)
                elif (hasattr(txt.dxf, 'align_point') and txt.dxf.align_point is not None):
                    txt_pt = to2d(txt.dxf.align_point)
                else:
                    continue
            except:
                continue
            
            # G1 끝점에서 50mm 이내인지 확인
            dist = distance(txt_pt, search_point)
            if dist > search_radius:  # 50mm
                continue
            
            # 회전각이 0인지 확인
            rotation = float(getattr(txt.dxf, "rotation", 0.0))
            if abs(rotation) > 0.1:
                continue
            
            # 텍스트 값 가져오기
            text_val = txt.plain_text() if hasattr(txt, "plain_text") else txt.dxf.text
            
            # 숫자인지 확인
            if not text_val.isdigit():
                continue
            
            # 10보다 큰 숫자인지 확인
            try:
                text_numeric_value = int(text_val)
                if text_numeric_value <= 10:
                    continue
            except:
                continue
            
            # 닫힌 영역 내부에 있는지 확인
            if is_enclosed(txt_pt, msp):
                continue
            
            # TBOX 생성 (중복 생성 방지)
            tbox_info = create_tbox(txt)
            if tbox_info is None:
                continue
            
            # G1 끝점(search_point)에서 TBOX 4개 코너까지의 최소 거리
            min_dist_to_tbox = min(distance(search_point, corner) for corner in tbox_info['corners'])
            
            candidates.append((min_dist_to_tbox, txt, text_numeric_value, tbox_info))
        
        if candidates:
            # TBOX까지의 거리가 가장 가까운 텍스트 선택
            candidates.sort(key=lambda x: x[0])  # 거리순 정렬
            selected_candidate = candidates[0]
            
            closest_txt = selected_candidate[1]
            ct_texts.append(closest_txt)
            
            # 디버깅 정보 출력 (선택사항)
            print(f"CT 선택: 텍스트={closest_txt.dxf.text}, "
                  f"TBOX까지 거리={selected_candidate[0]:.2f}mm, "
                  f"텍스트 크기={selected_candidate[3]['text_length']:.2f}x{selected_candidate[3]['text_height']:.2f}")
            
            break
    
    return ct_texts

def get_text_dimensions(txt):
    """
    텍스트의 크기 정보를 계산하는 함수 (길이, 높이)
    """
    try:
        if txt.dxftype() == "TEXT":
            # TEXT 엔티티의 경우
            text_val = txt.dxf.text
            height = float(txt.dxf.height)
            # 대략적인 문자 폭 계산 (높이의 0.6배로 추정)
            char_width = height * 0.6
            text_length = len(text_val) * char_width
            return text_length, height
            
        elif txt.dxftype() == "MTEXT":
            # MTEXT 엔티티의 경우
            text_val = txt.plain_text() if hasattr(txt, "plain_text") else txt.dxf.text
            height = float(txt.dxf.char_height) if hasattr(txt.dxf, 'char_height') else 1.0
            # 대략적인 문자 폭 계산
            char_width = height * 0.6
            text_length = len(text_val) * char_width
            return text_length, height
            
    except Exception as e:
        return 0.0, 0.0
    
    return 0.0, 0.0

def check_ct_dim_interference(ct_position, text_length, text_height, dim1_start, dim1_end, dim2_start, dim2_end):
    """
    CT와 DIM1, DIM2 선분 간의 간섭을 체크하는 함수
    """
    # 텍스트 높이의 60%를 간섭 임계값으로 사용
    interference_threshold = text_height * 0.6
    
    # DIM1, DIM2 선분과의 거리 계산
    dist_to_dim1 = point_to_line_distance(ct_position, dim1_start, dim1_end)
    dist_to_dim2 = point_to_line_distance(ct_position, dim2_start, dim2_end)
    
    # 간섭 여부 판단
    dim1_interference = dist_to_dim1 < interference_threshold
    dim2_interference = dist_to_dim2 < interference_threshold
    
    return dim1_interference or dim2_interference, dist_to_dim1, dist_to_dim2

def calculate_chain_direction(dim1_ent, dim2_ent):
    """
    DIM1, DIM2로부터 체인 방향을 계산하는 함수
    """
    # DIM1의 방향을 기준으로 체인 방향 계산
    dim1_segments = extract_segments(dim1_ent)
    if dim1_segments:
        p0, p1 = dim1_segments[0]
        v0, v1 = to2d(p0), to2d(p1)
        chain_dir = angle_deg(v0, v1)
        return chain_dir
    return 0.0

def calculate_text_angle(chain_dir):
    """
    체인 방향으로부터 텍스트 각도를 계산하는 함수
    """
    angle = chain_dir % 360
    
    # 수직(위/아래) 방향일 때 텍스트 헤드를 왼쪽(90°)으로 고정
    if abs(angle - 90) <= ANGLE_TOLERANCE or abs(angle - 270) <= ANGLE_TOLERANCE:
        angle = 90.0
    else:
        # 텍스트가 뒤집히지 않도록, 90~270° 구간은 +180° 보정
        if 90 < angle < 270:
            angle = (angle + 180) % 360
    
    return angle

def find_parallel_polylines_for_ang(msp, dim_pair, tolerance=0.5):
    """
    CP 반대편 점에서 2점을 가진 폴리라인을 찾아 ANG 각도 계산 (DIM1, DIM2 제외)
    최적화: 전체 스캔 대신 필요시에만 호출
    """
    dim1_opposite = dim_pair['DIM1_opposite']
    dim2_opposite = dim_pair['DIM2_opposite']
    
    # DIM1, DIM2 제외 목록 추가
    excluded_handles = {
        get_entity_handle(dim_pair['DIM1']),
        get_entity_handle(dim_pair['DIM2'])
    }
    
    # DIM1과 DIM2 반대편 점들 근처에서 폴리라인 찾기
    search_points = [dim1_opposite, dim2_opposite]
    found_polylines = []
    
    # 필요시에만 쿼리 실행 (ANG 각도 계산시에만)
    for search_point in search_points:
        for ent in msp.query("LWPOLYLINE POLYLINE"):
            if not ent.dxf.layer.startswith(DIM_LAYER_PREFIXES):
                continue
            
            # DIM1, DIM2 제외
            if get_entity_handle(ent) in excluded_handles:
                continue
            
            # 폴리라인의 점들 추출
            if isinstance(ent, LWPolyline):
                points = list(ent.get_points("xy"))
            else:
                points = [v.dxf.location for v in ent.vertices]
            
            if len(points) != 2:  # 정확히 2개의 점만 검색
                continue
            
            # 폴리라인의 각 점이 검색 점 근처에 있는지 확인
            pts = [to2d(p) for p in points]
            min_distance = min(distance(pt, search_point) for pt in pts)
            
            if min_distance <= tolerance:
                # 폴리라인의 방향 각도 계산 (첫 번째와 두 번째 점 기준)
                polyline_angle = angle_deg(pts[0], pts[1])
                found_polylines.append((ent, polyline_angle, min_distance, search_point))
    
    # 가장 가까운 폴리라인의 각도를 ANG로 사용
    if found_polylines:
        # 거리순으로 정렬하여 가장 가까운 것 선택
        found_polylines.sort(key=lambda x: x[2])
        closest_polyline = found_polylines[0]
        ang_angle = closest_polyline[1]
        return ang_angle
    else:
        return 0.0

def find_and_color_ct1_polylines(msp, dim_pair, tolerance=0.5):
    """
    DIM1 양끝에서 2점을 가진 폴리라인을 찾아 흰색으로 변경하는 함수
    """
    dim1_common = dim_pair['DIM1_common']
    dim1_opposite = dim_pair['DIM1_opposite']
    
    # DIM1, DIM2 제외 목록 추가
    excluded_handles = {
        get_entity_handle(dim_pair['DIM1']),
        get_entity_handle(dim_pair['DIM2'])
    }
    
    # DIM1 양끝에서 폴리라인 찾기
    search_points = [dim1_common, dim1_opposite]
    found_polylines = []
    
    for search_point in search_points:
        for ent in msp.query("LWPOLYLINE POLYLINE"):
            if not ent.dxf.layer.startswith(DIM_LAYER_PREFIXES):
                continue
            
            # DIM1, DIM2 제외
            if get_entity_handle(ent) in excluded_handles:
                continue
            
            # 폴리라인의 점들 추출
            if isinstance(ent, LWPolyline):
                points = list(ent.get_points("xy"))
            else:
                points = [v.dxf.location for v in ent.vertices]
            
            if len(points) != 2:  # 정확히 2개의 점만 검색
                continue
            
            # 폴리라인의 각 점이 검색 점 근처에 있는지 확인
            pts = [to2d(p) for p in points]
            min_distance = min(distance(pt, search_point) for pt in pts)
            
            if min_distance <= tolerance:
                found_polylines.append((ent, min_distance))
    
    # 가장 가까운 폴리라인을 흰색으로 변경
    if found_polylines:
        # 거리순으로 정렬하여 가장 가까운 것 선택
        found_polylines.sort(key=lambda x: x[1])
        closest_polyline = found_polylines[0][0]
        # 흰색으로 변경 (색상 코드 7)
        closest_polyline.dxf.color = 7

def process_ct_text_with_enhanced_interference_check(txt, g1_ent, v0, v1, text_angle, common_point, dim_pair, msp):
    """
    강화된 CT 텍스트 이동 및 간섭 검사 처리
    수정사항: 
    - CT1 조건: 1.2 <= dim_length <= 1.5 (회전 없음, 폴리라인 흰색으로 변경)
    - ANG 사용 조건: 1.5 <= dim_length <= 2.0
    """
    try:
        # 현재 텍스트 위치 확인
        if hasattr(txt.dxf, 'insert') and txt.dxf.insert is not None:
            current_pos = to2d(txt.dxf.insert)
        elif (hasattr(txt.dxf, 'align_point') and txt.dxf.align_point is not None):
            current_pos = to2d(txt.dxf.align_point)
        else:
            return
    except:
        return
    
    # DIM1, DIM2 선분 정보 추출
    dim1_ent = dim_pair['DIM1']
    dim2_ent = dim_pair['DIM2']
    
    dim1_segments = extract_segments(dim1_ent)
    dim2_segments = extract_segments(dim2_ent)
    
    if not dim1_segments or not dim2_segments:
        return
    
    dim1_start, dim1_end = to2d(dim1_segments[0][0]), to2d(dim1_segments[0][1])
    dim2_start, dim2_end = to2d(dim2_segments[0][0]), to2d(dim2_segments[0][1])
    
    # DIM1, DIM2 길이 확인
    dim_length = dim_pair['length']
    is_ct1 = 1.2 <= dim_length <= 1.5  # 수정된 조건
    
    # 회전 각도 결정
    if is_ct1:
        # CT1의 경우: 회전 각도를 0으로 설정하고 관련 폴리라인을 흰색으로 변경
        final_angle = 0.0
        find_and_color_ct1_polylines(msp, dim_pair)
    else:
        # CT의 경우: 기존 로직 사용
        use_ang_angle = 1.5 <= dim_length <= 2.0  # 수정된 조건
        if use_ang_angle:
            # ANG 각도 계산
            ang_angle = find_parallel_polylines_for_ang(msp, dim_pair)
            final_angle = ang_angle
        else:
            # 기존 text_angle 사용
            final_angle = text_angle
    
    # 텍스트 길이 및 높이 계산
    text_length, text_height = get_text_dimensions(txt)
    text_half_length = text_length / 2.0
    
    # 텍스트 방향 단위벡터 계산 (final_angle 기준)
    text_angle_rad = math.radians(final_angle)
    text_direction = np.array([math.cos(text_angle_rad), math.sin(text_angle_rad)])
    
    # 텍스트 수직 방향 계산 (좌우 이동용)
    text_perpendicular = np.array([-math.sin(text_angle_rad), math.cos(text_angle_rad)])
    
    # 1단계: CT 중심을 CP로 맞추기
    cp_centered_point = common_point - text_direction * text_half_length
    
    # 2단계: CP에서 TEXT 중심 방향으로 0.6mm 이동
    # CP에서 현재 텍스트 중심점으로의 방향 벡터 계산
    current_text_center = cp_centered_point + text_direction * text_half_length  # CP 정렬된 상태의 텍스트 중심
    cp_to_text_center_vec = current_text_center - common_point
    cp_to_text_center_distance = np.linalg.norm(cp_to_text_center_vec)
    
    if cp_to_text_center_distance > 0:
        # CP에서 텍스트 중심점 방향 단위벡터
        cp_to_text_center_direction = cp_to_text_center_vec / cp_to_text_center_distance
        # 0.6mm 이동
        move_0_6mm = cp_to_text_center_direction * 0.6
        intermediate_point = cp_centered_point + move_0_6mm
    else:
        # CP와 텍스트 중심점이 같으면 텍스트 방향으로 0.6mm 이동
        move_0_6mm = text_direction * 0.6
        intermediate_point = cp_centered_point + move_0_6mm
    
    # 3단계: 간섭 검사
    interference_detected, _, _ = check_ct_dim_interference(
        intermediate_point, text_length, text_height, dim1_start, dim1_end, dim2_start, dim2_end
    )
    
    final_position = intermediate_point
    
    if interference_detected:
        # 4단계: 간섭 발생시 반대방향으로 1.2mm 이동
        if cp_to_text_center_distance > 0:
            # 0.6mm 이동 반대방향으로 1.2mm
            interference_avoid_move = -cp_to_text_center_direction * 1.2
            candidate_position = intermediate_point + interference_avoid_move
        else:
            # 텍스트 방향 반대로 1.2mm
            interference_avoid_move = -text_direction * 1.2
            candidate_position = intermediate_point + interference_avoid_move
        
        # 반대방향 이동 후 간섭 재검사
        interference_still_detected, _, _ = check_ct_dim_interference(
            candidate_position, text_length, text_height, dim1_start, dim1_end, dim2_start, dim2_end
        )
        
        if not interference_still_detected:
            # 간섭 해결됨
            final_position = candidate_position
        else:
            # 5단계: 여전히 간섭 시 좌우, 위아래로 1mm씩 최대 4번 이동
            positions_to_try = []
            
            # 좌우 이동 위치들 생성 (우선순위: 좌우)
            for offset in [1.0, -1.0, 2.0, -2.0, 3.0, -3.0, 4.0, -4.0]:
                side_move = text_perpendicular * offset
                test_position = candidate_position + side_move
                positions_to_try.append(test_position)
            
            # 위아래 이동 위치들 생성 (차순위: 위아래)
            for offset in [1.0, -1.0, 2.0, -2.0, 3.0, -3.0, 4.0, -4.0]:
                vertical_move = text_direction * offset
                test_position = candidate_position + vertical_move
                positions_to_try.append(test_position)
            
            # 각 위치에서 간섭 검사
            best_position = candidate_position  # 기본값
            
            for test_pos in positions_to_try:
                test_interference, _, _ = check_ct_dim_interference(
                    test_pos, text_length, text_height, dim1_start, dim1_end, dim2_start, dim2_end
                )
                
                if not test_interference:
                    # 간섭 없는 첫 번째 위치 선택
                    best_position = test_pos
                    break
            
            final_position = best_position
    
    # 6단계: 최종 위치에서 CP 방향으로 2mm 추가 이동
    # final_position에서 common_point 방향으로의 단위벡터 계산
    final_to_cp_vec = common_point - final_position
    final_to_cp_distance = np.linalg.norm(final_to_cp_vec)
    
    if final_to_cp_distance > 0:
        # CP 방향 단위벡터
        final_to_cp_direction = final_to_cp_vec / final_to_cp_distance
        # CP 방향으로 2mm 이동
        cp_move_2mm = final_to_cp_direction * 2.0
        final_position = final_position + cp_move_2mm
    
    # 🔴 변경: DIM1 기울기로 평행하게 CP 방향으로 1.2mm 이동
    move_distance = -2 # mm
    
    # DIM1 선분 정보
    dim1_segments = extract_segments(dim_pair['DIM1'])
    if dim1_segments:
        dim1_start, dim1_end = to2d(dim1_segments[0][0]), to2d(dim1_segments[0][1])
        
        # DIM1의 방향 벡터
        dim1_vec = dim1_end - dim1_start
        dim1_length = np.linalg.norm(dim1_vec)
        
        if dim1_length > 0:
            # DIM1의 단위 방향 벡터
            dim1_unit = dim1_vec / dim1_length
            
            # 현재 위치에서 CP로의 방향 벡터
            to_cp_vec = common_point - final_position
            
            # CP 방향을 DIM1 방향에 투영
            projection_length = np.dot(to_cp_vec, dim1_unit)
            
            # CP 방향이 DIM1과 같은 방향인지 반대 방향인지 확인
            if projection_length > 0:
                move_direction = dim1_unit  # DIM1과 같은 방향
            else:
                move_direction = -dim1_unit  # DIM1과 반대 방향
            
            # 1.2mm 이동
            final_position = final_position + move_direction * move_distance
    # 7단계: 텍스트 이동 및 회전 처리
    if txt.dxftype() == "TEXT":
        old_z = float(txt.dxf.insert[2]) if len(txt.dxf.insert) > 2 else 0.0
        txt.dxf.insert = (float(final_position[0]), float(final_position[1]), old_z)
        txt.dxf.halign = 0
        txt.dxf.valign = 0
        try:
            if hasattr(txt.dxf, 'align_point'):
                delattr(txt.dxf, 'align_point')
        except:
            pass
        txt.dxf.rotation = float(final_angle)
        
    elif txt.dxftype() == "MTEXT":
        old_z = float(txt.dxf.insert[2]) if len(txt.dxf.insert) > 2 else 0.0
        txt.dxf.insert = (float(final_position[0]), float(final_position[1]), old_z)
        txt.dxf.attachment_point = 1
        txt.dxf.rotation = float(final_angle)
    
    # CT1 변수로 처리되었음을 리턴 (디버깅용)
    return is_ct1
def process_dimension_system(msp, text_entities):
    """
    DB1, CH1 치수선 시스템 처리 (쿼리 최적화 적용 + 강화된 AD3 삭제, AD1/AD2 보호)
    DIM1, DIM2, AD1, AD2는 절대 삭제되지 않음을 보장
    CP(공통점)의 3점 ARROW 레이어와 DIM 선분에 접하는 ARROW 레이어 AD3 삭제
    """
    # 🚀 쿼리 최적화: 한 번만 스캔 후 분류
    all_line_entities = list(msp.query("LINE LWPOLYLINE POLYLINE"))
    
    # find_dim_pairs 함수에 미리 스캔된 엔티티 전달
    dim_pairs, overlapped_entities = find_dim_pairs_optimized(all_line_entities)
    
    all_processed_entities = []
    all_ct_texts = []
    all_ct1_texts = []  # CT1 텍스트 별도 추적
    g1_entities_to_delete = []
    ad3_entities_to_delete = []
    arrow_lines_to_delete = []  # 추가된 ARROW LINE 삭제 목록
    
    # 보호할 엔티티 목록 (절대 삭제되면 안 됨)
    protected_entities = set()
    protected_entities_list = []  # 리스트로도 관리
    
    # AD1, AD2를 저장할 리스트 (전체 프로세스에서 보호용)
    all_ad1_ad2_entities = []
    
    # DIM의 반대편 끝점들을 저장 (AD1, AD2 위치)
    all_dim_far_endpoints = []
    
    # 🔴 모든 DIM으로 사용된 엔티티들의 핸들 수집 (G1 제외용)
    all_used_dim_handles = set()
    for dim_pair in dim_pairs:
        all_used_dim_handles.add(get_entity_handle(dim_pair['DIM1']))
        all_used_dim_handles.add(get_entity_handle(dim_pair['DIM2']))
    
    all_processed_entities.extend(overlapped_entities)
    
    for i, dim_pair in enumerate(dim_pairs):
        dim1 = dim_pair['DIM1']
        dim2 = dim_pair['DIM2']
        dim1_opposite = dim_pair['DIM1_opposite']
        dim2_opposite = dim_pair['DIM2_opposite']
        dim1_common = dim_pair['DIM1_common']
        dim2_common = dim_pair['DIM2_common']
        
        # DIM의 반대편 끝점들 저장 (AD1, AD2가 위치하는 곳)
        all_dim_far_endpoints.extend([dim1_opposite, dim2_opposite])
        
        # DIM1, DIM2를 보호 목록에 추가
        protected_entities.add(get_entity_handle(dim1))
        protected_entities.add(get_entity_handle(dim2))
        protected_entities_list.append(dim1)
        protected_entities_list.append(dim2)
        
        # 체인 방향 계산
        chain_dir = calculate_chain_direction(dim1, dim2)
        text_angle = calculate_text_angle(chain_dir)
        
        # DIM1, DIM2를 GREEN으로 표시
        dim1.dxf.color = 3
        dim2.dxf.color = 3
        all_processed_entities.extend([dim1, dim2])
        
        # AD1, AD2 찾기 (최적화된 버전) - DIM_LAYER_PREFIXES에서만 찾음
        ad1_entities = find_arrow_entities_optimized(all_line_entities, dim1_opposite)
        ad2_entities = find_arrow_entities_optimized(all_line_entities, dim2_opposite)
        
        # AD1, AD2를 보호 목록에 추가
        for ad1 in ad1_entities:
            protected_entities.add(get_entity_handle(ad1))
            protected_entities_list.append(ad1)
            all_ad1_ad2_entities.append(ad1)
        for ad2 in ad2_entities:
            protected_entities.add(get_entity_handle(ad2))
            protected_entities_list.append(ad2)
            all_ad1_ad2_entities.append(ad2)
        
        # AD1, AD2를 YELLOW로 표시
        for ad1 in ad1_entities:
            ad1.dxf.color = 2
            all_processed_entities.append(ad1)
        
        for ad2 in ad2_entities:
            ad2.dxf.color = 2
            all_processed_entities.append(ad2)
        
        # AD3 찾기 (최적화된 버전) - CP 근처의 3점 폴리라인 (ARROW 레이어 포함)
        ad3_entities = find_ad3_entities_optimized(all_line_entities, dim_pair, ad1_entities, ad2_entities)
        
        # 🔴 G1 찾기 - 모든 DIM 핸들 전달하여 제외
        g1_entities = find_g1_entities_optimized_with_all_dims(
            all_line_entities, dim1, dim2, dim_pair, all_used_dim_handles
        )
        
        # CT 찾기 및 처리
        ct_found = False
        for g1_ent, v0, v1 in g1_entities:
            g1_ent.dxf.color = 1
            all_processed_entities.append(g1_ent)
            g1_entities_to_delete.append(g1_ent)
            
            # CT 찾기
            ct_texts = find_ct_texts(msp, [(g1_ent, v0, v1)], text_entities, dim_pair)
            
            if ct_texts:
                ct_found = True
                for ct in ct_texts:
                    ct.dxf.color = 2
                    
                    # 강화된 텍스트 이동 및 간섭 검사
                    is_ct1 = process_ct_text_with_enhanced_interference_check(
                        ct, g1_ent, v0, v1, text_angle, dim_pair['common_point'], dim_pair, msp
                    )
                    
                    # CT1 변수인지 CT 변수인지 구분하여 저장
                    if is_ct1:
                        all_ct1_texts.append(ct)
                    else:
                        all_ct_texts.append(ct)
        
        # ... 나머지 코드는 동일 ...
        
        # CT를 찾았을 때만 AD3 삭제 (CP 근처의 3점 ARROW 포함)
        if ct_found:
            for ad3 in ad3_entities:
                # 보호된 엔티티가 아닌 경우만 삭제 목록에 추가
                if (get_entity_handle(ad3) not in protected_entities and 
                    ad3 not in all_ad1_ad2_entities and
                    ad3 not in protected_entities_list):
                    ad3.dxf.color = 4
                    all_processed_entities.append(ad3)
                    ad3_entities_to_delete.append(ad3)
                else:
                    # 보호된 엔티티는 색상만 변경
                    ad3.dxf.color = 2
                    all_processed_entities.append(ad3)
        else:
            for ad3 in ad3_entities:
                ad3.dxf.color = 2
                all_processed_entities.append(ad3)
        
        # DIM1, DIM2 선분에 접하는 AD3 찾기 (ARROW 레이어, 0.2mm 이내)
        touching_ad3 = find_ad3_touching_dims(all_line_entities, dim1, dim2, ad1_entities, ad2_entities)
        for touching_ad3_ent in touching_ad3:
            # 보호된 엔티티가 아니고 이미 삭제 목록에 없는 경우만 추가
            if (get_entity_handle(touching_ad3_ent) not in protected_entities and 
                touching_ad3_ent not in ad3_entities_to_delete and
                touching_ad3_ent not in all_ad1_ad2_entities and
                touching_ad3_ent not in protected_entities_list):  # : 추가됨
                touching_ad3_ent.dxf.color = 4  # 삭제 예정 표시
                all_processed_entities.append(touching_ad3_ent)
                ad3_entities_to_delete.append(touching_ad3_ent)
    # DIM의 반대편 끝점 근처의 ARROW 레이어 보호 (AD1, AD2 보호)
    for ent in all_line_entities:
        if ent.dxf.layer.upper() == "ARROW":
            try:
                if isinstance(ent, LWPolyline):
                    points = list(ent.get_points("xy"))
                elif isinstance(ent, Polyline):
                    points = [v.dxf.location for v in ent.vertices]
                else:
                    continue
                
                pts = [to2d(p) for p in points]
                
                # DIM의 반대편 끝점 근처에 있는지 확인 (AD1, AD2 위치)
                for pt in pts:
                    for far_endpoint in all_dim_far_endpoints:
                        if distance(pt, far_endpoint) <= 0.5:  # 반대편 끝점에서 0.5mm 이내
                            protected_entities.add(get_entity_handle(ent))
                            break
            except:
                continue

    # 삭제될 AD3 점에 접하는 ARROW 레이어의 1mm 이하 LINE 찾기
    arrow_lines = find_arrow_lines_touching_ad3(all_line_entities, ad3_entities_to_delete)
    for arrow_line in arrow_lines:
        # 보호된 엔티티가 아닌 경우만 삭제 목록에 추가
        if (get_entity_handle(arrow_line) not in protected_entities and
            arrow_line not in protected_entities_list):
            arrow_line.dxf.color = 4  # 삭제 예정 표시
            all_processed_entities.append(arrow_line)
            arrow_lines_to_delete.append(arrow_line)

    # 삭제 전 최종 검증: AD1, AD2가 삭제 목록에 있는지 확인
    ad3_entities_to_delete_final = []
    for ad3_ent in ad3_entities_to_delete:
        if (ad3_ent not in all_ad1_ad2_entities and 
            ad3_ent not in protected_entities_list and
            get_entity_handle(ad3_ent) not in protected_entities):
            ad3_entities_to_delete_final.append(ad3_ent)

    arrow_lines_to_delete_final = []
    for arrow_line in arrow_lines_to_delete:
        if (arrow_line not in all_ad1_ad2_entities and
            arrow_line not in protected_entities_list and
            get_entity_handle(arrow_line) not in protected_entities):
            arrow_lines_to_delete_final.append(arrow_line)

    # 엔티티 삭제 (보호된 엔티티 제외)
    deleted_count = 0
    for ad3_ent in ad3_entities_to_delete_final:
        try:
            # 삭제 직전 최종 확인
            if (get_entity_handle(ad3_ent) not in protected_entities and
                ad3_ent not in protected_entities_list and
                ad3_ent not in all_ad1_ad2_entities):
                msp.delete_entity(ad3_ent)
                deleted_count += 1
        except:
            pass

    for g1_ent in g1_entities_to_delete:
        try:
            # G1은 보호 대상이 아니므로 삭제
            if get_entity_handle(g1_ent) not in protected_entities:
                msp.delete_entity(g1_ent)
        except:
            pass

    # ARROW LINE 삭제
    for arrow_line in arrow_lines_to_delete_final:
        try:
            # 삭제 직전 최종 확인
            if (get_entity_handle(arrow_line) not in protected_entities and
                arrow_line not in protected_entities_list):
                msp.delete_entity(arrow_line)
        except:
            pass

    return all_processed_entities, all_ct_texts, all_ct1_texts


    # ─────────────── 메인 파이프라인 ───────────────
def auto_align_dxf(input_dxf, output_dxf):
    """
    DB1, CH1만 처리하는 단일 DXF 파일 처리 함수 (로그 최소화)
    """
    if not os.path.isfile(input_dxf):
        return False
    
    try:
        # TBOX 캐시 초기화
        clear_tbox_cache()
        
        doc = ezdxf.readfile(input_dxf)
        msp = doc.modelspace()

        # 텍스트 엔티티 수집
        text_entities = list(msp.query("TEXT MTEXT"))
        
        # DB1, CH1 치수선 시스템 처리
        processed_entities, ct_texts, ct1_texts = process_dimension_system(msp, text_entities)

        # 저장
        doc.saveas(output_dxf)
        
        # 처리 완료 후 TBOX 캐시 초기화
        clear_tbox_cache()
        
        return True
        
    except Exception as e:
        # 에러 발생 시에도 TBOX 캐시 초기화
        clear_tbox_cache()
        return False

def process_multiple_files():
    """
    여러 DXF 파일을 처리하는 메인 함수 (로그 최소화)
    """
    selected_files = select_dxf_files()
    
    if not selected_files:
        return
    
    progress_window, progress_var, file_label, progress_text = show_progress_window(len(selected_files))
    
    success_count = 0
    failed_files = []
    
    try:
        for i, input_file in enumerate(selected_files):
            update_progress(progress_window, progress_var, file_label, progress_text, 
                          i, len(selected_files), input_file)
            
            file_dir = os.path.dirname(input_file)
            file_name = os.path.splitext(os.path.basename(input_file))[0]
            output_file = os.path.join(file_dir, f"{file_name}_DIM.dxf")
            
            if auto_align_dxf(input_file, output_file):
                success_count += 1
            else:
                failed_files.append(os.path.basename(input_file))
        
        update_progress(progress_window, progress_var, file_label, progress_text, 
                      len(selected_files), len(selected_files), "완료")
        
    finally:
        close_progress_window(progress_window)
    
    # 최종 결과 출력
    print(f"✅ 성공: {success_count}개 파일")
    if failed_files:
        print(f"❌ 실패: {len(failed_files)}개 파일")
        for file_name in failed_files:
            print(f"  - {file_name}")
    
    print("프로그램이 완료되었습니다.")


if __name__ == "__main__":
    if len(sys.argv) == 3:
        auto_align_dxf(sys.argv[1], sys.argv[2])
    else:
        process_multiple_files()