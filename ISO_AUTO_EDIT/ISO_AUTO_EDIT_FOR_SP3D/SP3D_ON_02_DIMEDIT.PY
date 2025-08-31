import os
import sys
import ezdxf
import math
import numpy as np
from ezdxf.entities import Line, LWPolyline, Polyline, Text, Hatch

# ─────────────── 설정 값 ───────────────
ANGLE_TOLERANCE = 5.0  # 각도 허용 오차 (°)

# TBOX 캐시를 위한 전역 딕셔너리
TBOX_CACHE = {}

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
            return str(id(entity))
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

# ─────────────── 최적화된 엔티티 수집 함수 ───────────────
def collect_dim_entities(msp):
    """
    DIM 또는 ISO가 포함된 레이어의 엔티티만 수집하는 최적화된 함수
    """
    dim_line_entities = []
    dim_text_entities = []
    
    # 모든 레이어 이름 수집
    dim_layers = set()
    for layer in msp.doc.layers:
        layer_name_upper = layer.dxf.name.upper()
        if 'DIM' in layer_name_upper or 'ISO' in layer_name_upper:
            dim_layers.add(layer.dxf.name)
    
    # DIM 또는 ISO 레이어의 LINE 엔티티만 수집
    for entity in msp.query("LINE LWPOLYLINE POLYLINE"):
        layer_upper = entity.dxf.layer.upper()
        if entity.dxf.layer in dim_layers or 'DIM' in layer_upper or 'ISO' in layer_upper:
            dim_line_entities.append(entity)
    
    # DIM 또는 ISO 레이어의 TEXT 엔티티만 수집
    for entity in msp.query("TEXT MTEXT"):
        layer_upper = entity.dxf.layer.upper()
        if entity.dxf.layer in dim_layers or 'DIM' in layer_upper or 'ISO' in layer_upper:
            dim_text_entities.append(entity)
    
    return dim_line_entities, dim_text_entities

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

# ─────────────── 새로운 엔티티 찾기 함수들 ───────────────
def find_dl_entities(dim_line_entities):
    """
    DL 엔티티 찾기: 레이어가 DIMLINES인 LINE, 선가중치 0.3mm, 색상 흰색, 길이 3.5mm 초과
    """
    dl_entities = []
    
    for ent in dim_line_entities:
        if not isinstance(ent, Line):
            continue
            
        # 레이어가 DIMLINES인지 확인
        if ent.dxf.layer.upper() != "DIMLINES":
            continue
            
        # 색상이 흰색(7)인지 확인
        if hasattr(ent.dxf, 'color') and ent.dxf.color != 7:
            continue
            
        # 선가중치가 0.3mm (30)인지 확인
        if hasattr(ent.dxf, 'lineweight'):
            if ent.dxf.lineweight != 30:  # 0.3mm = 30
                continue
        
        # 길이가 3.5mm를 초과하는지 확인
        segments = extract_segments(ent)
        if segments:
            p0, p1 = segments[0]
            v0, v1 = to2d(p0), to2d(p1)
            line_length = distance(v0, v1)
            
            if line_length <= 2.5:
                continue
        else:
            continue
        
        dl_entities.append(ent)
    
    return dl_entities

def find_ad_entities(dim_line_entities, dl_start, dl_end, used_ad_handles, tolerance=0.1):
    """
    AD1, AD2 찾기: DL 양끝점에서 0.1mm 이내로 접하는 1.8~2mm 길이의 LINE
    이미 사용된 AD는 제외
    """
    ad1_entities = []
    ad2_entities = []
    
    for ent in dim_line_entities:
        if not isinstance(ent, Line):
            continue
        
        # 이미 사용된 AD인지 확인
        if get_entity_handle(ent) in used_ad_handles:
            continue
            
        segments = extract_segments(ent)
        if not segments:
            continue
            
        p0, p1 = segments[0]
        v0, v1 = to2d(p0), to2d(p1)
        line_length = distance(v0, v1)
        
        # 1.8~2mm 길이 확인
        if not (1.8 <= line_length <= 2.0):
            continue
            
        # DL 시작점과의 거리 확인
        dist_to_start_v0 = distance(v0, dl_start)
        dist_to_start_v1 = distance(v1, dl_start)
        min_dist_to_start = min(dist_to_start_v0, dist_to_start_v1)
        
        # DL 끝점과의 거리 확인
        dist_to_end_v0 = distance(v0, dl_end)
        dist_to_end_v1 = distance(v1, dl_end)
        min_dist_to_end = min(dist_to_end_v0, dist_to_end_v1)
        
        # AD1 (DL 시작점 근처)
        if min_dist_to_start <= tolerance:
            ad1_entities.append(ent)
        # AD2 (DL 끝점 근처)
        elif min_dist_to_end <= tolerance:
            ad2_entities.append(ent)
    
    # 각 끝점에서 정확히 2개씩만 선택
    if len(ad1_entities) > 2:
        ad1_entities = ad1_entities[:2]
    if len(ad2_entities) > 2:
        ad2_entities = ad2_entities[:2]
    
    return ad1_entities, ad2_entities

def find_g1_entities(dim_line_entities, dl_ent, tolerance=0.3):
    """
    G1 찾기: DL 선분에 0.3mm 이내로 접하는 점이 있는 LINE
    PIPE 레이어나 DL은 제외, 길이가 2mm 이하인 라인도 제외
    DL 양끝점에서 2.5mm 이내에 있는 LINE도 제외
    """
    g1_entities = []
    
    # DL의 양끝점 계산
    dl_segments = extract_segments(dl_ent)
    if not dl_segments:
        return []
        
    dl_start, dl_end = to2d(dl_segments[0][0]), to2d(dl_segments[0][1])
    
    for ent in dim_line_entities:
        if not isinstance(ent, Line):
            continue
            
        # DL 자체는 제외
        if get_entity_handle(ent) == get_entity_handle(dl_ent):
            continue
        
        # PIPE 레이어 제외
        if ent.dxf.layer.upper() == "PIPE":
            continue
        
        # DL 레이어 제외
        if ent.dxf.layer.upper() == "DL":
            continue
            
        segments = extract_segments(ent)
        if not segments:
            continue
            
        p0, p1 = segments[0]
        v0, v1 = to2d(p0), to2d(p1)
        
        # 길이가 2mm 이하인 라인 제외
        line_length = distance(v0, v1)
        if line_length <= 2.0:
            continue
        
        # DL 양끝점에서 2.5mm 이내에 있는지 확인
        min_dist_to_dl_start = min(distance(v0, dl_start), distance(v1, dl_start))
        min_dist_to_dl_end = min(distance(v0, dl_end), distance(v1, dl_end))
        
        if min_dist_to_dl_start <= 2.5 or min_dist_to_dl_end <= 2.5:
            continue
        
        # 선분의 끝점들과 DL 선분까지의 거리 계산
        dist_v0_to_dl = point_to_line_distance(v0, dl_start, dl_end)
        dist_v1_to_dl = point_to_line_distance(v1, dl_start, dl_end)
        
        # 둘 중 하나라도 0.3mm 이내라면 G1 후보
        if dist_v0_to_dl <= tolerance or dist_v1_to_dl <= tolerance:
            # AP1, AP2 결정 (DL에 가까운 점이 AP1, 먼 점이 AP2)
            if dist_v0_to_dl < dist_v1_to_dl:
                ap1, ap2 = v0, v1
            else:
                ap1, ap2 = v1, v0
            
            g1_entities.append((ent, v0, v1, ap1, ap2))
    
    return g1_entities

def find_connected_g1_lines(dim_line_entities, g1_ent, v0, v1, tolerance=0.01):
    """
    G1 끝점에서 0.01mm 내 접점에 또다른 LINE이 붙어 있는지 찾기
    """
    connected_lines = []
    
    for ent in dim_line_entities:
        if not isinstance(ent, Line):
            continue
            
        # G1 자체는 제외
        if get_entity_handle(ent) == get_entity_handle(g1_ent):
            continue
            
        segments = extract_segments(ent)
        if not segments:
            continue
            
        p0, p1 = segments[0]
        line_v0, line_v1 = to2d(p0), to2d(p1)
        
        # G1의 양끝점과 이 라인의 양끝점 거리 확인
        connections = []
        
        # G1의 v0과 연결되는지 확인
        if distance(v0, line_v0) <= tolerance:
            connections.append(('v0', line_v0, line_v1))
        elif distance(v0, line_v1) <= tolerance:
            connections.append(('v0', line_v1, line_v0))
            
        # G1의 v1과 연결되는지 확인  
        if distance(v1, line_v0) <= tolerance:
            connections.append(('v1', line_v0, line_v1))
        elif distance(v1, line_v1) <= tolerance:
            connections.append(('v1', line_v1, line_v0))
        
        if connections:
            # 연결점과 반대쪽 끝점 정보 저장
            for conn_point, near_pt, far_pt in connections:
                connected_lines.append((ent, near_pt, far_pt, conn_point))
    
    return connected_lines

def find_del1_entities(dim_line_entities, g1_entities, dl_center, tolerance=0.3):
    """
    DEL1 찾기: DL에 가까운 G1점(AP1)의 0.3mm 내에 있는 1.8~2mm 길이의 LINE 2개
    """
    del1_entities = []
    
    for g1_ent, v0, v1, ap1, ap2 in g1_entities:
        # AP1 점 근처의 LINE 찾기
        candidates = []
        for ent in dim_line_entities:
            if not isinstance(ent, Line):
                continue
                
            # G1 자체는 제외
            if get_entity_handle(ent) == get_entity_handle(g1_ent):
                continue
                
            segments = extract_segments(ent)
            if not segments:
                continue
                
            p0, p1 = segments[0]
            v0, v1 = to2d(p0), to2d(p1)
            line_length = distance(v0, v1)
            
            # 1.8~2mm 길이 확인
            if not (1.8 <= line_length <= 2.0):
                continue
                
            # AP1 점과의 거리 확인
            min_dist = min(distance(v0, ap1), distance(v1, ap1))
            
            if min_dist <= tolerance:
                candidates.append((ent, min_dist))
        
        # 거리순으로 정렬하여 가장 가까운 2개 선택
        candidates.sort(key=lambda x: x[1])
        for i, (ent, _) in enumerate(candidates[:2]):
            del1_entities.append(ent)
    
    return del1_entities

def find_del2_entities(dim_line_entities, del1_entities, tolerance=0.3):
    """
    DEL2 찾기: DEL1의 한쪽 끝점에 0.3mm 내에서 길이가 1mm 이하인 LINE
    """
    del2_entities = []
    
    for del1_ent in del1_entities:
        del1_segments = extract_segments(del1_ent)
        if not del1_segments:
            continue
            
        del1_start, del1_end = to2d(del1_segments[0][0]), to2d(del1_segments[0][1])
        
        for ent in dim_line_entities:
            if not isinstance(ent, Line):
                continue
                
            segments = extract_segments(ent)
            if not segments:
                continue
                
            p0, p1 = segments[0]
            v0, v1 = to2d(p0), to2d(p1)
            line_length = distance(v0, v1)
            
            # 길이가 1mm 이하인지 확인
            if line_length > 1.0:
                continue
                
            # DEL1 끝점과의 거리 확인
            min_dist_to_start = min(distance(v0, del1_start), distance(v1, del1_start))
            min_dist_to_end = min(distance(v0, del1_end), distance(v1, del1_end))
            min_dist = min(min_dist_to_start, min_dist_to_end)
            
            if min_dist <= tolerance:
                del2_entities.append(ent)
    
    return del2_entities

def get_hatch_area(hatch):
    """
    HATCH의 면적을 계산하는 함수
    """
    try:
        # ezdxf의 내장 기능 사용 시도
        if hasattr(hatch, 'area'):
            return float(hatch.area)
        
        # 경계 점들을 수집하여 면적 계산
        all_points = []
        
        # paths를 통해 경계 점들 수집
        if hasattr(hatch, 'paths'):
            for path in hatch.paths:
                if hasattr(path, 'control_points'):
                    # PolylinePath의 경우
                    for point in path.control_points:
                        all_points.append(to2d(point))
                elif hasattr(path, 'vertices'):
                    # 다른 경로 타입의 경우
                    for vertex in path.vertices:
                        all_points.append(to2d(vertex))
                elif hasattr(path, 'edges'):
                    # EdgePath의 경우
                    for edge in path.edges:
                        if hasattr(edge, 'start'):
                            all_points.append(to2d(edge.start))
        
        # 경계 패스가 없으면 paths_to_entities 메서드 시도
        if not all_points and hasattr(hatch, 'paths_to_entities'):
            try:
                entities = list(hatch.paths_to_entities())
                for entity in entities:
                    segments = extract_segments(entity)
                    for segment in segments:
                        all_points.append(to2d(segment[0]))
            except:
                pass
        
        # 점이 3개 이상 있어야 면적 계산 가능
        if len(all_points) >= 3:
            # 중복 점 제거
            unique_points = []
            for point in all_points:
                is_duplicate = False
                for unique_point in unique_points:
                    if distance(point, unique_point) < 0.001:
                        is_duplicate = True
                        break
                if not is_duplicate:
                    unique_points.append(point)
            
            if len(unique_points) >= 3:
                # Shoelace formula를 사용하여 면적 계산
                area = 0.0
                n = len(unique_points)
                for i in range(n):
                    j = (i + 1) % n
                    area += unique_points[i][0] * unique_points[j][1]
                    area -= unique_points[j][0] * unique_points[i][1]
                return abs(area) / 2.0
    except Exception as e:
        pass
    
    return 0.0

def get_hatch_center(hatch):
    """
    HATCH의 중심점을 계산하는 함수
    """
    try:
        all_points = []
        
        # paths를 통해 경계 점들 수집
        if hasattr(hatch, 'paths'):
            for path in hatch.paths:
                if hasattr(path, 'control_points'):
                    # PolylinePath의 경우
                    for point in path.control_points:
                        all_points.append(to2d(point))
                elif hasattr(path, 'vertices'):
                    for vertex in path.vertices:
                        all_points.append(to2d(vertex))
                elif hasattr(path, 'edges'):
                    for edge in path.edges:
                        if hasattr(edge, 'start'):
                            all_points.append(to2d(edge.start))
        
        # 경계 패스가 없으면 paths_to_entities 메서드 시도
        if not all_points and hasattr(hatch, 'paths_to_entities'):
            try:
                entities = list(hatch.paths_to_entities())
                for entity in entities:
                    segments = extract_segments(entity)
                    for segment in segments:
                        all_points.append(to2d(segment[0]))
            except:
                pass
        
        if all_points:
            # 중복 점 제거
            unique_points = []
            for point in all_points:
                is_duplicate = False
                for unique_point in unique_points:
                    if distance(point, unique_point) < 0.001:
                        is_duplicate = True
                        break
                if not is_duplicate:
                    unique_points.append(point)
            
            if unique_points:
                center_x = sum(p[0] for p in unique_points) / len(unique_points)
                center_y = sum(p[1] for p in unique_points) / len(unique_points)
                return np.array([center_x, center_y])
        
        # seed_points가 있으면 첫 번째 seed point 사용
        if hasattr(hatch, 'seed_points') and hatch.seed_points:
            return np.array([hatch.seed_points[0][0], hatch.seed_points[0][1]])
    except Exception as e:
        pass
    
    return None

def find_del3_hatches(msp, ap1_point):
    """
    AP1에서 가장 가까운 면적이 0.6~0.9인 HATCH를 찾아 DEL3로 처리
    """
    del3_entities = []
    candidates = []
    
    # 모든 HATCH 엔티티 검색
    for hatch in msp.query("HATCH"):
        # HATCH의 면적 계산
        area = get_hatch_area(hatch)
        
        # 면적이 0.6~0.9 범위인지 확인
        if 0.6 <= area <= 0.9:
            # HATCH의 중심점 계산
            center = get_hatch_center(hatch)
            if center is not None:
                # AP1에서 HATCH 중심까지의 거리 계산
                dist = distance(ap1_point, center)
                candidates.append((dist, hatch))
    
    # 거리순으로 정렬하여 가장 가까운 1개 선택
    if candidates:
        candidates.sort(key=lambda x: x[0])
        closest_hatch = candidates[0][1]
        
        # DEL3 레이어로 설정하고 흰색으로 변경
        closest_hatch.dxf.layer = "DEL3"
        closest_hatch.dxf.color = 7  # WHITE
        del3_entities.append(closest_hatch)
    
    return del3_entities

def find_cp_texts(msp, g1_entities, dim_text_entities, used_cp_handles, dim_line_entities, search_radius=15.0):
    """
    CP 찾기: AP2 점에서 15mm 범위에서 가장 가까운 10 이상의 숫자 중에서 기울기가 0인 TEXT
    G1에 연결된 추가 LINE이 있으면 그 LINE의 반대쪽 끝점에서 찾기
    이미 사용된 CP는 제외
    """
    cp_texts = []
    
    for g1_ent, v0, v1, ap1, ap2 in g1_entities:
        # G1에 연결된 추가 LINE 찾기
        connected_lines = find_connected_g1_lines(dim_line_entities, g1_ent, v0, v1)
        
        # CP 검색 지점 결정
        search_points = []
        
        if connected_lines:
            # 연결된 LINE이 있으면 그 LINE의 반대쪽 끝점에서 검색
            for conn_ent, near_pt, far_pt, conn_point in connected_lines:
                # AP2와 연결된 LINE인지 확인
                if distance(near_pt, ap2) <= 0.01:
                    search_points.append(far_pt)
        
        # 연결된 LINE이 없거나 AP2와 연결되지 않았으면 AP2에서 검색
        if not search_points:
            search_points.append(ap2)
        
        # 각 검색 지점에서 CP 찾기
        for search_point in search_points:
            candidates = []
            
            for txt in dim_text_entities:
                try:
                    # 이미 사용된 CP인지 확인
                    if get_entity_handle(txt) in used_cp_handles:
                        continue
                    
                    # 레이어가 DIMTEXT인지 확인
                    if hasattr(txt.dxf, 'layer') and txt.dxf.layer.upper() != "DIMTEXT":
                        continue
                    
                    # 텍스트 위치 가져오기
                    if hasattr(txt.dxf, 'insert') and txt.dxf.insert is not None:
                        txt_pt = to2d(txt.dxf.insert)
                    elif hasattr(txt.dxf, 'align_point') and txt.dxf.align_point is not None:
                        txt_pt = to2d(txt.dxf.align_point)
                    else:
                        continue
                except:
                    continue
                
                # 검색 지점에서 15mm 이내인지 확인
                dist = distance(txt_pt, search_point)
                if dist > search_radius:
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
                
                # TBOX 생성
                tbox_info = create_tbox(txt)
                if tbox_info is None:
                    continue
                
                # 검색 지점에서 TBOX 4개 코너까지의 최소 거리
                min_dist_to_tbox = min(distance(search_point, corner) for corner in tbox_info['corners'])
                
                candidates.append((min_dist_to_tbox, txt, text_numeric_value, tbox_info, ap1))
            
            if candidates:
                # TBOX까지의 거리가 가장 가까운 텍스트 선택
                candidates.sort(key=lambda x: x[0])
                selected_candidate = candidates[0]
                
                closest_txt = selected_candidate[1]
                ap1_point = selected_candidate[4]
                cp_texts.append((closest_txt, ap1_point))
                
                # G1당 하나의 텍스트만 선택하므로 바로 종료
                break
    
    return cp_texts

def get_text_dimensions(txt):
    """
    텍스트의 크기 정보를 계산하는 함수 (길이, 높이)
    """
    try:
        if txt.dxftype() == "TEXT":
            text_val = txt.dxf.text
            height = float(txt.dxf.height)
            char_width = height * 0.6
            text_length = len(text_val) * char_width
            return text_length, height
            
        elif txt.dxftype() == "MTEXT":
            text_val = txt.plain_text() if hasattr(txt, "plain_text") else txt.dxf.text
            height = float(txt.dxf.char_height) if hasattr(txt.dxf, 'char_height') else 1.0
            char_width = height * 0.6
            text_length = len(text_val) * char_width
            return text_length, height
            
    except Exception as e:
        return 0.0, 0.0
    
    return 0.0, 0.0

def check_ct_dim_interference(ct_position, text_length, text_height, dl_start, dl_end):
    """
    CT와 DL 선분 간의 간섭을 체크하는 함수
    """
    interference_threshold = text_height * 0.6
    
    dist_to_dl = point_to_line_distance(ct_position, dl_start, dl_end)
    
    dl_interference = dist_to_dl < interference_threshold
    
    return dl_interference, dist_to_dl

def calculate_text_angle(dl_ent):
    """
    DL로부터 텍스트 각도를 계산하는 함수
    """
    dl_segments = extract_segments(dl_ent)
    if dl_segments:
        p0, p1 = dl_segments[0]
        v0, v1 = to2d(p0), to2d(p1)
        chain_dir = angle_deg(v0, v1)
        
        angle = chain_dir % 360
        
        # 수직(위/아래) 방향일 때 텍스트 헤드를 왼쪽(90°)으로 고정
        if abs(angle - 90) <= ANGLE_TOLERANCE or abs(angle - 270) <= ANGLE_TOLERANCE:
            angle = 90.0
        else:
            # 텍스트가 뒤집히지 않도록, 90~270° 구간은 +180° 보정
            if 90 < angle < 270:
                angle = (angle + 180) % 360
        
        return angle
    return 0.0

def process_ct_text_with_enhanced_interference_check(txt, ap1_point, text_angle, dl_ent, msp):
    """
    CT 텍스트 이동 처리
    1. CP를 TEXT와 높이를 기준으로 BOX화하여 CT라 하고, CT의 중심을 AP1로 이동
    2. 이동된 CT를 DL의 직교 + 방향으로 CT 높이의 1/2 - 0.2mm 만큼 이동
    3. CP의 기울기가 325~335도 또는 85~95도이면 우측에서 좌측으로 1.2mm 이동
    """
    try:
        # 현재 텍스트 위치 확인
        if hasattr(txt.dxf, 'insert') and txt.dxf.insert is not None:
            current_pos = to2d(txt.dxf.insert)
        elif hasattr(txt.dxf, 'align_point') and txt.dxf.align_point is not None:
            current_pos = to2d(txt.dxf.align_point)
        else:
            return
    except:
        return
    
    # 텍스트 길이 및 높이 계산
    text_length, text_height = get_text_dimensions(txt)
    text_half_length = text_length / 2.0
    text_half_height = text_height / 2.0
    
    # 텍스트 방향 단위벡터 계산
    text_angle_rad = math.radians(text_angle)
    text_direction = np.array([math.cos(text_angle_rad), math.sin(text_angle_rad)])
    
    # DL의 직교 방향 (텍스트 기준 위쪽 방향)
    # 텍스트가 서있는 기준에서 위쪽은 텍스트 방향의 왼쪽 90도
    text_perpendicular = np.array([-math.sin(text_angle_rad), math.cos(text_angle_rad)])
    
    # 1단계: CT의 중심을 AP1로 이동
    # 텍스트 BOX의 중심이 AP1에 오도록 위치 계산
    ct_center_at_ap1 = ap1_point - text_direction * text_half_length
    
    # 2단계: DL의 직교 방향으로 (텍스트 높이/2 - 0.2mm) 이동
    move_distance = text_half_height - 0.2
    final_position = ct_center_at_ap1 + text_perpendicular * move_distance
    
    # 3단계: CP의 기울기가 325~335도 또는 85~95도인 경우 추가 이동
    # 텍스트를 위로 보는 기준에서 우측에서 좌측으로 1.2mm 이동
    if (325 <= text_angle <= 335) or (85 <= text_angle <= 95):
        # 텍스트를 위로 보는 기준에서 좌측은 -text_direction 방향
        left_direction = -text_direction
        final_position = final_position + left_direction * 1.2
    
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
        txt.dxf.rotation = float(text_angle)
        
    elif txt.dxftype() == "MTEXT":
        old_z = float(txt.dxf.insert[2]) if len(txt.dxf.insert) > 2 else 0.0
        txt.dxf.insert = (float(final_position[0]), float(final_position[1]), old_z)
        txt.dxf.attachment_point = 1
        txt.dxf.rotation = float(text_angle)

def process_dimension_system(msp, dim_text_entities, dim_line_entities):
    """
    새로운 치수선 시스템 처리 - 최적화된 버전
    """
    # DL 찾기
    dl_entities = find_dl_entities(dim_line_entities)
    
    all_processed_entities = []
    all_cp_texts = []
    
    # 삭제할 DEL 및 G1 엔티티들을 별도로 추적
    entities_to_delete = []
    
    # 사용된 AD 엔티티 추적
    used_ad_handles = set()
    
    # 사용된 CP 텍스트 추적
    used_cp_handles = set()
    
    for dl_ent in dl_entities:
        # DL 정보 추출
        dl_segments = extract_segments(dl_ent)
        if not dl_segments:
            continue
            
        dl_start, dl_end = to2d(dl_segments[0][0]), to2d(dl_segments[0][1])
        dl_center = (dl_start + dl_end) / 2.0
        
        # AD1, AD2 찾기 (이미 사용된 AD는 제외)
        ad1_entities, ad2_entities = find_ad_entities(dim_line_entities, dl_start, dl_end, used_ad_handles)
        
        # AD1과 AD2가 모두 2개씩 있는 경우만 DL로 처리
        if len(ad1_entities) != 2 or len(ad2_entities) != 2:
            continue
        
        # DL 레이어 및 색상 변경
        dl_ent.dxf.layer = "DL"
        dl_ent.dxf.color = 4  # CYAN
        all_processed_entities.append(dl_ent)
        
        # AD1 처리 및 사용 표시
        for i, ad1 in enumerate(ad1_entities):
            ad1.dxf.layer = "AD1"
            ad1.dxf.color = 4  # CYAN
            all_processed_entities.append(ad1)
            used_ad_handles.add(get_entity_handle(ad1))
        
        # AD2 처리 및 사용 표시
        for i, ad2 in enumerate(ad2_entities):
            ad2.dxf.layer = "AD2"
            ad2.dxf.color = 4  # CYAN
            all_processed_entities.append(ad2)
            used_ad_handles.add(get_entity_handle(ad2))
        
        # G1 찾기 (AP1, AP2 정보 포함)
        g1_entities = find_g1_entities(dim_line_entities, dl_ent)
        
        # DL당 G1 1개만 처리 (첫 번째 것만)
        if g1_entities:
            g1_ent, v0, v1, ap1, ap2 = g1_entities[0]  # 첫 번째 G1만 선택
            g1_ent.dxf.layer = "G1"
            g1_ent.dxf.color = 1  # RED
            all_processed_entities.append(g1_ent)
            entities_to_delete.append(g1_ent)  # 나중에 삭제하기 위해 추가
            
            # G1에 연결된 추가 LINE 찾기 및 처리
            connected_lines = find_connected_g1_lines(dim_line_entities, g1_ent, v0, v1)
            for conn_ent, _, _, _ in connected_lines:
                conn_ent.dxf.layer = "G1"
                conn_ent.dxf.color = 1  # RED
                all_processed_entities.append(conn_ent)
                entities_to_delete.append(conn_ent)  # 나중에 삭제하기 위해 추가
            
            # DEL1 찾기 (AP1 기준)
            del1_entities = find_del1_entities(dim_line_entities, [(g1_ent, v0, v1, ap1, ap2)], dl_center)
            
            for del1 in del1_entities:
                del1.dxf.layer = "DEL1"
                del1.dxf.color = 1  # RED
                all_processed_entities.append(del1)
                entities_to_delete.append(del1)  # 나중에 삭제하기 위해 추가
            
            # DEL2 찾기
            del2_entities = find_del2_entities(dim_line_entities, del1_entities)
            
            for del2 in del2_entities:
                del2.dxf.layer = "DEL2"
                del2.dxf.color = 1  # RED
                all_processed_entities.append(del2)
                entities_to_delete.append(del2)  # 나중에 삭제하기 위해 추가
            
            # DEL3 (HATCH) 찾기 - AP1에서 가장 가까운 면적 0.6~0.9인 HATCH
            del3_entities = find_del3_hatches(msp, ap1)
            all_processed_entities.extend(del3_entities)
            entities_to_delete.extend(del3_entities)  # 나중에 삭제하기 위해 추가
            
            # CP 찾기 (AP2 기준, 15mm 반경)
            cp_texts_with_ap1 = find_cp_texts(msp, [(g1_ent, v0, v1, ap1, ap2)], dim_text_entities, 
                                              used_cp_handles, dim_line_entities)
            
            if cp_texts_with_ap1:
                for cp, ap1_point in cp_texts_with_ap1:
                    cp.dxf.layer = "CP"
                    cp.dxf.color = 4  # CYAN
                    
                    # 사용된 CP로 표시
                    used_cp_handles.add(get_entity_handle(cp))
                    
                    # 텍스트 각도 계산
                    text_angle = calculate_text_angle(dl_ent)
                    
                    # CT 텍스트 이동 처리 (AP1로 이동)
                    process_ct_text_with_enhanced_interference_check(
                        cp, ap1_point, text_angle, dl_ent, msp
                    )
                    
                    all_cp_texts.append(cp)
    
    return all_processed_entities, all_cp_texts, entities_to_delete

# ─────────────── 런너(In-Memory) 연동용 함수 ───────────────
def process(doc):
    """
    런너(In-Memory) 연동용 process 함수
    ezdxf document 객체를 직접 받아서 처리
    
    Args:
        doc: ezdxf document 객체
        
    Returns:
        처리된 ezdxf document 객체
    """
    try:
        # TBOX 캐시 초기화
        clear_tbox_cache()
        
        msp = doc.modelspace()

        # DIM 또는 ISO 레이어 엔티티만 수집 (최적화)
        dim_line_entities, dim_text_entities = collect_dim_entities(msp)
        
        # 치수선 시스템 처리
        processed_entities, cp_texts, entities_to_delete = process_dimension_system(msp, dim_text_entities, dim_line_entities)

        # 모든 처리가 완료된 후 DEL1, DEL2, DEL3, G1 엔티티 삭제
        for entity in entities_to_delete:
            try:
                msp.delete_entity(entity)
            except Exception as e:
                pass

        # 처리 완료 후 TBOX 캐시 초기화
        clear_tbox_cache()
        
        return doc
        
    except Exception as e:
        # 에러 발생 시에도 TBOX 캐시 초기화
        clear_tbox_cache()
        raise e

# ─────────────── 파일 기반 처리 함수 (기존 유지) ───────────────
def auto_align_dxf(input_dxf, output_dxf):
    """
    단일 DXF 파일 처리 함수
    """
    if not os.path.isfile(input_dxf):
        return False
    
    try:
        # DXF 파일 읽기
        doc = ezdxf.readfile(input_dxf)
        
        # In-Memory 처리 함수 호출
        doc = process(doc)
        
        # 저장
        doc.saveas(output_dxf)
        
        return True
        
    except Exception as e:
        return False

# ─────────────── 메인 파이프라인 ───────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    
    # 첫 번째 인자는 스크립트 이름이므로 제외
    input_files = sys.argv[1:]
    
    for input_file in input_files:
        if not input_file.lower().endswith('.dxf'):
            continue
            
        file_dir = os.path.dirname(input_file)
        file_name = os.path.splitext(os.path.basename(input_file))[0]
        output_file = os.path.join(file_dir, f"{file_name}_DIM.dxf")
        
        auto_align_dxf(input_file, output_file)