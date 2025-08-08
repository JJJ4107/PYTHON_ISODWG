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
DIM_LAYER_PREFIX = "GT_"  # 치수선 레이어 접두사


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


# ─────────────── DB1, CH1 시스템 함수들 ───────────────
def find_dim_pairs_optimized(all_line_entities):
    """
    DIM1, DIM2 쌍을 찾는 함수 (최적화된 버전 - 미리 필터링된 엔티티 사용)
    """
    two_point_entities = []
    
    for ent in all_line_entities:
        if not ent.dxf.layer.startswith(DIM_LAYER_PREFIX):
            continue
            
        segments = extract_segments(ent)
        if len(segments) != 1:
            continue
            
        p0, p1 = segments[0]
        v0, v1 = to2d(p0), to2d(p1)
        length = distance(v0, v1)
        
        if 1.5 <= length <= 8.0:
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
    """
    arrows = []
    
    for ent in all_line_entities:
        if not ent.dxf.layer.startswith(DIM_LAYER_PREFIX):
            continue
            
        if isinstance(ent, LWPolyline):
            points = list(ent.get_points("xy"))
        else:
            points = [v.dxf.location for v in ent.vertices]
        
        if len(points) != 3:
            continue
        
        pts = [to2d(p) for p in points]
        min_dist_to_point = min(distance(pt, point) for pt in pts)
        
        if min_dist_to_point <= tolerance:
            arrows.append(ent)
    
    return arrows

def find_ad3_entities_optimized(all_line_entities, dim_pair, ad1_entities, ad2_entities, tolerance=0.5):
    """
    최적화된 버전 - 미리 필터링된 엔티티에서 AD3 찾기
    """
    ad3_candidates = []
    common_point = dim_pair['common_point']
    
    excluded_handles = set()
    for ad1 in ad1_entities:
        excluded_handles.add(get_entity_handle(ad1))
    for ad2 in ad2_entities:
        excluded_handles.add(get_entity_handle(ad2))
    
    for ent in all_line_entities:
        if not ent.dxf.layer.startswith(DIM_LAYER_PREFIX):
            continue
            
        if get_entity_handle(ent) in excluded_handles:
            continue
            
        if isinstance(ent, LWPolyline):
            points = list(ent.get_points("xy"))
        else:
            points = [v.dxf.location for v in ent.vertices]
        
        if len(points) != 3:
            continue
        
        pts = [to2d(p) for p in points]
        min_dist_to_cp = min(distance(pt, common_point) for pt in pts)
        
        if min_dist_to_cp <= tolerance:
            ad3_candidates.append((ent, min_dist_to_cp))
    
    if ad3_candidates:
        ad3_candidates.sort(key=lambda x: x[1])
        return [ad3_candidates[0][0]]
    
    return []

def find_ad3_touching_dims(all_line_entities, dim1_ent, dim2_ent, ad1_entities, ad2_entities, tolerance=0.1):
    """
    DIM1이나 DIM2 선분에 접하는 AD3 엔티티들을 찾는 함수 (AD1, AD2 제외)
    """
    touching_ad3 = []
    
    # DIM1, DIM2 선분 정보 추출
    dim1_segments = extract_segments(dim1_ent)
    dim2_segments = extract_segments(dim2_ent)
    
    if not dim1_segments or not dim2_segments:
        return []
    
    dim1_start, dim1_end = to2d(dim1_segments[0][0]), to2d(dim1_segments[0][1])
    dim2_start, dim2_end = to2d(dim2_segments[0][0]), to2d(dim2_segments[0][1])
    
    # DIM1, DIM2, AD1, AD2 제외
    excluded_handles = {get_entity_handle(dim1_ent), get_entity_handle(dim2_ent)}
    
    # AD1, AD2 핸들 추가하여 삭제 대상에서 제외
    for ad1 in ad1_entities:
        excluded_handles.add(get_entity_handle(ad1))
    for ad2 in ad2_entities:
        excluded_handles.add(get_entity_handle(ad2))
    
    for ent in all_line_entities:
        if not ent.dxf.layer.startswith(DIM_LAYER_PREFIX):
            continue
            
        if get_entity_handle(ent) in excluded_handles:
            continue
            
        # 3점 폴리라인인지 확인
        if isinstance(ent, LWPolyline):
            points = list(ent.get_points("xy"))
        else:
            points = [v.dxf.location for v in ent.vertices]
        
        if len(points) != 3:
            continue
        
        pts = [to2d(p) for p in points]
        
        # AD3의 각 점이 DIM1 또는 DIM2 선분에 접하는지 확인
        is_touching = False
        
        for pt in pts:
            # DIM1 선분까지의 거리
            dist_to_dim1 = point_to_line_distance(pt, dim1_start, dim1_end)
            # DIM2 선분까지의 거리
            dist_to_dim2 = point_to_line_distance(pt, dim2_start, dim2_end)
            
            if dist_to_dim1 <= tolerance or dist_to_dim2 <= tolerance:
                is_touching = True
                break
        
        if is_touching:
            touching_ad3.append(ent)
    
    return touching_ad3

def find_g1_entities_optimized(all_line_entities, dim1_ent, dim2_ent, dim_pair, tolerance=0.2):
    """
    최적화된 버전 - 미리 필터링된 엔티티에서 G1 찾기
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
    
    excluded_handles = {get_entity_handle(dim1_ent), get_entity_handle(dim2_ent)}
    
    for ent in all_line_entities:
        if not ent.dxf.layer.startswith(DIM_LAYER_PREFIX):
            continue
        
        if get_entity_handle(ent) in excluded_handles:
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
    G1 지시선의 DIM1, DIM2 교차점에서 먼 쪽 끝에서 10mm 내에서 가장 가까운 회전이 0인 숫자 치수 텍스트 찾기
    RED 텍스트나 WDNO 레이어는 제외하고, 2개 이상이면 큰 값을 선택 (로그 최소화)
    """
    ct_texts = []
    
    common_point = dim_pair['common_point']
    
    for g1_ent, v0, v1 in g1_entities:
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
                
                if hasattr(txt.dxf, 'insert') and txt.dxf.insert is not None:
                    txt_pt = to2d(txt.dxf.insert)
                elif (hasattr(txt.dxf, 'align_point') and txt.dxf.align_point is not None):
                    txt_pt = to2d(txt.dxf.align_point)
                else:
                    continue
            except:
                continue
            
            dist = distance(txt_pt, search_point)
            if dist > search_radius:
                continue
            
            text_val = txt.plain_text() if hasattr(txt, "plain_text") else txt.dxf.text
            
            if not text_val.isdigit():
                continue
            
            rotation = float(getattr(txt.dxf, "rotation", 0.0))
            if abs(rotation) > 0.1:
                continue
            
            if is_enclosed(txt_pt, msp):
                continue
            
            try:
                text_numeric_value = int(text_val)
                candidates.append((dist, txt, text_numeric_value))
            except:
                continue
        
        if candidates:
            if len(candidates) > 1:
                # 큰 값 우선, 같은 값이면 가까운 거리 우선
                candidates.sort(key=lambda x: (-x[2], x[0]))
                selected_candidate = candidates[0]
            else:
                candidates.sort(key=lambda x: x[0])
                selected_candidate = candidates[0]
            
            closest_txt = selected_candidate[1]
            ct_texts.append(closest_txt)
            break
    
    return ct_texts

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
            if not ent.dxf.layer.startswith(DIM_LAYER_PREFIX):
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

def get_text_dimensions(txt):
    """
    텍스트의 크기 정보를 계산하는 함수 (길이만 반환)
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

def process_ct_text_positioning(txt, g1_ent, v0, v1, text_angle, common_point, dim_pair, msp):
    """
    CT 텍스트 위치 계산 및 이동 처리
    CP점에서 텍스트 박스 중심까지의 직선 거리가 2mm가 되도록 배치
    """
    try:
        # DIM1, DIM2 길이 확인
        dim_length = dim_pair['length']
        use_ang_angle = 1.5 <= dim_length <= 2.0
        
        if use_ang_angle:
            # ANG 각도 계산
            ang_angle = find_parallel_polylines_for_ang(msp, dim_pair)
            final_angle = ang_angle
        else:
            # 기존 text_angle 사용
            final_angle = text_angle
        
        # 텍스트 방향 단위벡터 계산 (final_angle 기준)
        text_angle_rad = math.radians(final_angle)
        text_direction = np.array([math.cos(text_angle_rad), math.sin(text_angle_rad)])
        
        # 텍스트 길이 계산
        text_length = get_text_dimensions(txt)[0]
        text_half_length = text_length / 2.0
        
        # 현재 텍스트 위치에서 텍스트 박스 중심점 계산
        if txt.dxftype() == "TEXT":
            current_text_start = to2d(txt.dxf.insert)
        elif txt.dxftype() == "MTEXT":
            current_text_start = to2d(txt.dxf.insert)
        else:
            current_text_start = to2d(txt.dxf.insert)
        
        # 현재 텍스트 박스의 중심점 계산
        current_text_center = current_text_start + text_direction * text_half_length
        
        # CP에서 현재 텍스트 박스 중심점으로의 방향 벡터
        cp_to_text_center_vec = current_text_center - common_point
        cp_to_text_center_distance = np.linalg.norm(cp_to_text_center_vec)
        
        if cp_to_text_center_distance > 0:
            # CP에서 텍스트 박스 중심점 방향의 단위벡터
            cp_to_text_center_direction = cp_to_text_center_vec / cp_to_text_center_distance
        else:
            # CP와 텍스트 중심점이 같으면 텍스트 방향을 기본 방향으로 사용
            cp_to_text_center_direction = text_direction
        
        # CP에서 정확히 1mm 떨어진 곳에 텍스트 박스 중심 배치
        target_text_center = common_point + cp_to_text_center_direction * 1
        
        # 텍스트 시작점 계산 (박스 중심에서 텍스트 방향 반대로 반 길이만큼)
        final_position = target_text_center - text_direction * text_half_length
        
        # 텍스트 이동 및 회전 처리
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
            
    except Exception as e:
        # 에러 발생 시 기본 처리
        pass

def process_dimension_system(msp, text_entities):
    """
    DB1, CH1 치수선 시스템 처리 (AD1/AD2 보호, 단순 CT 이동)
    """
    # 🚀 쿼리 최적화: 한 번만 스캔 후 분류
    all_line_entities = list(msp.query("LINE LWPOLYLINE POLYLINE"))
    
    # find_dim_pairs 함수에 미리 스캔된 엔티티 전달
    dim_pairs, overlapped_entities = find_dim_pairs_optimized(all_line_entities)
    
    all_processed_entities = []
    all_ct_texts = []
    g1_entities_to_delete = []
    ad3_entities_to_delete = []
    
    all_processed_entities.extend(overlapped_entities)
    
    for i, dim_pair in enumerate(dim_pairs):
        dim1 = dim_pair['DIM1']
        dim2 = dim_pair['DIM2']
        dim1_opposite = dim_pair['DIM1_opposite']
        dim2_opposite = dim_pair['DIM2_opposite']
        
        # 체인 방향 계산
        chain_dir = calculate_chain_direction(dim1, dim2)
        text_angle = calculate_text_angle(chain_dir)
        
        # DIM1, DIM2를 GREEN으로 표시
        dim1.dxf.color = 3
        dim2.dxf.color = 3
        all_processed_entities.extend([dim1, dim2])
        
        # AD1, AD2 찾기 (최적화된 버전)
        ad1_entities = find_arrow_entities_optimized(all_line_entities, dim1_opposite)
        ad2_entities = find_arrow_entities_optimized(all_line_entities, dim2_opposite)
        
        # AD1, AD2를 YELLOW로 표시
        for ad1 in ad1_entities:
            ad1.dxf.color = 2
            all_processed_entities.append(ad1)
        
        for ad2 in ad2_entities:
            ad2.dxf.color = 2
            all_processed_entities.append(ad2)
        
        # AD3 찾기 (최적화된 버전)
        ad3_entities = find_ad3_entities_optimized(all_line_entities, dim_pair, ad1_entities, ad2_entities)
        
        # G1 찾기 (최적화된 버전)
        g1_entities = find_g1_entities_optimized(all_line_entities, dim1, dim2, dim_pair)
        
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
                    all_ct_texts.append(ct)
                    # 단순 텍스트 이동 처리
                    process_ct_text_positioning(
                        ct, g1_ent, v0, v1, text_angle, dim_pair['common_point'], dim_pair, msp
                    )
        
        # CT를 찾았을 때만 AD3 삭제
        if ct_found:
            for ad3 in ad3_entities:
                ad3.dxf.color = 4
                all_processed_entities.append(ad3)
                ad3_entities_to_delete.append(ad3)
        else:
            for ad3 in ad3_entities:
                ad3.dxf.color = 2
                all_processed_entities.append(ad3)
        
        # DIM1, DIM2 선분에 접하는 AD3 찾기 및 삭제 목록에 추가 (AD1, AD2 제외)
        touching_ad3 = find_ad3_touching_dims(all_line_entities, dim1, dim2, ad1_entities, ad2_entities)
        for touching_ad3_ent in touching_ad3:
            if touching_ad3_ent not in ad3_entities_to_delete:
                touching_ad3_ent.dxf.color = 4  # 삭제 예정 표시
                all_processed_entities.append(touching_ad3_ent)
                ad3_entities_to_delete.append(touching_ad3_ent)
    
    # 엔티티 삭제
    for ad3_ent in ad3_entities_to_delete:
        try:
            msp.delete_entity(ad3_ent)
        except:
            pass
    
    for g1_ent in g1_entities_to_delete:
        try:
            msp.delete_entity(g1_ent)
        except:
            pass
    
    return all_processed_entities, all_ct_texts


# ─────────────── 메인 파이프라인 ───────────────
def auto_align_dxf(input_dxf, output_dxf):
    """
    DB1, CH1만 처리하는 단일 DXF 파일 처리 함수 (로그 최소화)
    """
    if not os.path.isfile(input_dxf):
        return False
    
    try:
        doc = ezdxf.readfile(input_dxf)
        msp = doc.modelspace()

        # 텍스트 엔티티 수집
        text_entities = list(msp.query("TEXT MTEXT"))
        
        # DB1, CH1 치수선 시스템 처리
        processed_entities, ct_texts = process_dimension_system(msp, text_entities)

        # 저장
        doc.saveas(output_dxf)
        
        return True
        
    except Exception as e:
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
            output_file = os.path.join(file_dir, f"{file_name}_aligned.dxf")
            
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