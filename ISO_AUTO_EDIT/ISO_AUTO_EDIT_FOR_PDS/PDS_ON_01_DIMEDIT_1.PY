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
    시간복잡도: O(n + m) where n = 레이어 수, m = 엔티티 수
    """
    dim_line_entities = []
    dim_text_entities = []
    
    # 모든 레이어 이름을 미리 수집하여 조회 시간 최적화
    dim_layers = set()
    for layer in msp.doc.layers:
        layer_name_upper = layer.dxf.name.upper()
        if 'DIM' in layer_name_upper or 'ISO' in layer_name_upper:
            dim_layers.add(layer.dxf.name)
    
    # 단일 쿼리로 필요한 엔티티 타입만 조회
    for entity in msp.query("LINE LWPOLYLINE POLYLINE"):
        layer_upper = entity.dxf.layer.upper()
        if entity.dxf.layer in dim_layers or 'DIM' in layer_upper or 'ISO' in layer_upper:
            dim_line_entities.append(entity)
    
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

# ─────────────── 수정된 엔티티 찾기 함수들 ───────────────
def find_dl_entities(msp):
    """
    DL 엔티티 찾기: DIM 또는 G1 레이어에서 길이가 3.5mm 초과하는 LINE
    시간복잡도: O(n) where n = LINE 엔티티 수
    """
    dl_entities = []
    
    for ent in msp.query("LINE"):
        # DIM 또는 G1 레이어인지 확인
        layer_upper = ent.dxf.layer.upper()
        if 'DIM' not in layer_upper and layer_upper != 'G1':
            continue
            
        # 길이가 3.5mm를 초과하는지 확인
        segments = extract_segments(ent)
        if segments:
            p0, p1 = segments[0]
            v0, v1 = to2d(p0), to2d(p1)
            line_length = distance(v0, v1)
            
            if line_length <= 3.5:
                continue
        else:
            continue
        
        dl_entities.append(ent)
    
    return dl_entities

def find_ad_entities(msp, dl_start, dl_end, used_ad_handles, tolerance=0.5):
    """
    AD1, AD2 찾기: PL4 레이어에서 DL 양끝점에 0.5mm 이내로 접하는 엔티티
    시간복잡도 최적화: 조건을 만족하면 즉시 반환
    """
    ad1_entity = None
    ad2_entity = None
    
    for ent in msp.query("LINE LWPOLYLINE POLYLINE"):
        # 이미 두 개 다 찾았으면 종료
        if ad1_entity and ad2_entity:
            break
            
        # PL4 레이어인지 확인
        if ent.dxf.layer.upper() != "PL4":
            continue
            
        # 이미 사용된 AD인지 확인
        if get_entity_handle(ent) in used_ad_handles:
            continue
            
        segments = extract_segments(ent)
        if not segments:
            continue
            
        # 모든 점들을 확인
        points = []
        for seg in segments:
            points.append(to2d(seg[0]))
            points.append(to2d(seg[1]))
        
        # DL 시작점과의 거리 확인
        for pt in points:
            if distance(pt, dl_start) <= tolerance and ad1_entity is None:
                ad1_entity = ent
                break
            elif distance(pt, dl_end) <= tolerance and ad2_entity is None:
                ad2_entity = ent
                break
    
    return ad1_entity, ad2_entity

def find_g1_entities(msp, dl_ent, tolerance=0.35):
    """
    G1 찾기: G1 또는 DIM 레이어를 가진 LINE 중에서 조건을 만족하는 선
    조건: 길이 2mm 이상, DL 양끝점에서 2.5mm 이상 떨어짐, DL 선분에서 0.35mm 이내 접촉
    시간복잡도 최적화: 첫 번째 조건 만족 시 즉시 반환
    """
    g1_entities = []
    
    # DL의 양끝점 계산
    dl_segments = extract_segments(dl_ent)
    if not dl_segments:
        return []
        
    dl_start, dl_end = to2d(dl_segments[0][0]), to2d(dl_segments[0][1])
    dl_handle = get_entity_handle(dl_ent)
    
    for ent in msp.query("LINE"):
        # G1 또는 DIM 레이어인지 확인
        layer_upper = ent.dxf.layer.upper()
        if layer_upper != "G1" and "DIM" not in layer_upper:
            continue
        
        # DL 자체는 제외
        if get_entity_handle(ent) == dl_handle:
            continue
            
        segments = extract_segments(ent)
        if not segments:
            continue
            
        p0, p1 = segments[0]
        v0, v1 = to2d(p0), to2d(p1)
        
        # 길이가 2mm 이상인지 확인
        line_length = distance(v0, v1)
        if line_length < 2.0:
            continue
        
        # DL 양끝점에서 2.5mm 이내에 있는지 확인
        min_dist_to_dl_start = min(distance(v0, dl_start), distance(v1, dl_start))
        min_dist_to_dl_end = min(distance(v0, dl_end), distance(v1, dl_end))
        
        if min_dist_to_dl_start < 2.5 or min_dist_to_dl_end < 2.5:
            continue
        
        # 선분의 끝점들과 DL 선분까지의 거리 계산
        dist_v0_to_dl = point_to_line_distance(v0, dl_start, dl_end)
        dist_v1_to_dl = point_to_line_distance(v1, dl_start, dl_end)
        
        # 어느 한점이 0.35mm 이내에 접하는지 확인
        if dist_v0_to_dl <= tolerance or dist_v1_to_dl <= tolerance:
            # AP1, AP2 결정 (DL에 가까운 점이 AP1, 먼 점이 AP2)
            if dist_v0_to_dl < dist_v1_to_dl:
                ap1, ap2 = v0, v1
            else:
                ap1, ap2 = v1, v0
            
            g1_entities.append((ent, v0, v1, ap1, ap2))
            break  # 첫 번째로 찾은 G1만 반환
    
    return g1_entities

def find_del1_entities(msp, ap1_point, tolerance=0.5):
    """
    DEL1 찾기: AP1 점에서 0.5mm 내에서 점이 접하는 PL4 1개, PL3 3개
    시간복잡도 최적화: 필요한 개수를 다 찾으면 즉시 종료
    """
    del1_entities = []
    pl4_count = 0
    pl3_count = 0
    
    for ent in msp.query("LINE LWPOLYLINE POLYLINE"):
        # 이미 필요한 개수를 다 찾았으면 종료
        if pl4_count >= 1 and pl3_count >= 3:
            break
            
        layer = ent.dxf.layer.upper()
        
        # PL4 또는 PL3 레이어만 확인
        if layer not in ["PL4", "PL3"]:
            continue
        
        # 이미 충분히 찾았으면 해당 레이어 스킵
        if layer == "PL4" and pl4_count >= 1:
            continue
        if layer == "PL3" and pl3_count >= 3:
            continue
        
        segments = extract_segments(ent)
        if not segments:
            continue
        
        # 모든 점들을 확인
        found = False
        for seg in segments:
            if found:
                break
            v0, v1 = to2d(seg[0]), to2d(seg[1])
            
            # AP1과의 거리 확인
            if distance(v0, ap1_point) <= tolerance or distance(v1, ap1_point) <= tolerance:
                found = True
        
        if found:
            if layer == "PL4" and pl4_count < 1:
                del1_entities.append(ent)
                pl4_count += 1
            elif layer == "PL3" and pl3_count < 3:
                del1_entities.append(ent)
                pl3_count += 1
    
    return del1_entities

def find_cp_text(msp, ap2_point, search_radius=25.0):
    """
    CP 찾기: AP2에서 25mm 내에서 숫자 값이 10 이상인 CP 레이어의 TEXT
    시간복잡도 최적화: 가장 가까운 것을 찾으면 계속 업데이트하되, 거리 기준으로 조기 종료 가능
    """
    closest_cp = None
    min_distance = float('inf')
    
    # CP 레이어 텍스트만 미리 필터링
    cp_texts = [txt for txt in msp.query("TEXT MTEXT") if txt.dxf.layer.upper() == "CP"]
    
    for txt in cp_texts:
        # 텍스트 위치 가져오기
        try:
            if hasattr(txt.dxf, 'insert') and txt.dxf.insert is not None:
                txt_pt = to2d(txt.dxf.insert)
            elif hasattr(txt.dxf, 'align_point') and txt.dxf.align_point is not None:
                txt_pt = to2d(txt.dxf.align_point)
            else:
                continue
        except:
            continue
        
        # AP2와의 거리 계산
        dist = distance(txt_pt, ap2_point)
        
        # 25mm 이내인지 확인
        if dist > search_radius:
            continue
        
        # 텍스트 값 가져오기
        text_val = txt.plain_text() if hasattr(txt, "plain_text") else txt.dxf.text
        
        # 숫자인지 확인하고 10 이상인지 확인
        try:
            text_numeric_value = float(text_val)
            if text_numeric_value < 10:
                continue
        except:
            continue
        
        # 가장 가까운 CP 업데이트
        if dist < min_distance:
            min_distance = dist
            closest_cp = txt
    
    return closest_cp

def find_connected_g1_lines(dim_line_entities, g1_ent, v0, v1, tolerance=0.01):
    """
    G1 끝점에서 0.01mm 내 접점에 또다른 LINE이 붙어 있는지 찾기
    """
    connected_lines = []
    g1_handle = get_entity_handle(g1_ent)
    
    for ent in dim_line_entities:
        if not isinstance(ent, Line):
            continue
            
        # G1 자체는 제외
        if get_entity_handle(ent) == g1_handle:
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
    수정된 치수선 시스템 처리
    전체 시간복잡도: O(n*m) where n = DL 엔티티 수, m = 평균 검색 대상 엔티티 수
    """
    # DL 찾기
    dl_entities = find_dl_entities(msp)
    
    all_processed_entities = []
    all_cp_texts = []
    
    # 삭제할 엔티티들을 별도로 추적 (CP 처리가 완료된 경우만)
    entities_to_delete = []
    
    # 사용된 AD 엔티티 추적
    used_ad_handles = set()
    
    for dl_ent in dl_entities:
        # DL 정보 추출
        dl_segments = extract_segments(dl_ent)
        if not dl_segments:
            continue
            
        dl_start, dl_end = to2d(dl_segments[0][0]), to2d(dl_segments[0][1])
        dl_center = (dl_start + dl_end) / 2.0
        
        # AD1, AD2 찾기 (PL4 레이어에서)
        ad1_entity, ad2_entity = find_ad_entities(msp, dl_start, dl_end, used_ad_handles)
        
        # AD1과 AD2가 모두 있는 경우만 DL로 처리
        if ad1_entity is None or ad2_entity is None:
            continue
        
        # DL 레이어 및 색상 변경
        dl_ent.dxf.layer = "DL"
        dl_ent.dxf.color = 4  # CYAN
        all_processed_entities.append(dl_ent)
        
        # AD1 처리
        if ad1_entity:
            ad1_entity.dxf.layer = "AD1"
            ad1_entity.dxf.color = 4  # CYAN
            all_processed_entities.append(ad1_entity)
            used_ad_handles.add(get_entity_handle(ad1_entity))
        
        # AD2 처리
        if ad2_entity:
            ad2_entity.dxf.layer = "AD2"
            ad2_entity.dxf.color = 4  # CYAN
            all_processed_entities.append(ad2_entity)
            used_ad_handles.add(get_entity_handle(ad2_entity))
        
        # G1 찾기 (AP1, AP2 정보 포함)
        g1_entities = find_g1_entities(msp, dl_ent)
        
        # DL당 G1 1개만 처리 (첫 번째 것만)
        if g1_entities:
            g1_ent, v0, v1, ap1, ap2 = g1_entities[0]  # 첫 번째 G1만 선택
            g1_ent.dxf.layer = "G1"
            g1_ent.dxf.color = 1  # RED
            all_processed_entities.append(g1_ent)
            # G1은 나중에 CP 처리 여부에 따라 삭제 결정
            
            # G1에 연결된 추가 LINE 찾기 및 처리
            connected_lines = find_connected_g1_lines(dim_line_entities, g1_ent, v0, v1)
            connected_g1_lines = []  # CP 처리 여부에 따라 삭제 결정
            for conn_ent, _, _, _ in connected_lines:
                conn_ent.dxf.layer = "G1"
                conn_ent.dxf.color = 1  # RED
                all_processed_entities.append(conn_ent)
                connected_g1_lines.append(conn_ent)
            
            # DEL1 찾기 (AP1 기준, PL4 1개 + PL3 3개)
            del1_entities = find_del1_entities(msp, ap1)
            
            for del1 in del1_entities:
                del1.dxf.layer = "DEL1"
                del1.dxf.color = 4  # CYAN
                all_processed_entities.append(del1)
                # DEL1도 나중에 CP 처리 여부에 따라 삭제 결정
            
            # CP 찾기 (AP2에서 25mm 내에서 숫자 값이 10 이상인 CP 레이어 TEXT)
            cp = find_cp_text(msp, ap2)
            
            if cp:
                # CP 색상을 CYAN으로 변경
                cp.dxf.color = 4  # CYAN
                
                # 텍스트 각도 계산
                text_angle = calculate_text_angle(dl_ent)
                
                # CT 텍스트 이동 처리 (AP1로 이동)
                process_ct_text_with_enhanced_interference_check(
                    cp, ap1, text_angle, dl_ent, msp
                )
                
                all_cp_texts.append(cp)
                
                # CT 처리가 완료된 경우에만 G1과 DEL1 삭제
                entities_to_delete.append(g1_ent)
                entities_to_delete.extend(connected_g1_lines)
                entities_to_delete.extend(del1_entities)
    
    return all_processed_entities, all_cp_texts, entities_to_delete

# ─────────────── 런너 연동용 함수 ───────────────
def process(doc):
    """
    런너(in-memory) 연동용 프로세스 함수
    매개변수: ezdxf.Document 객체
    반환값: 처리된 ezdxf.Document 객체
    """
    try:
        # TBOX 캐시 초기화
        clear_tbox_cache()
        
        msp = doc.modelspace()

        # DIM 또는 ISO 레이어 엔티티만 수집 (최적화)
        dim_line_entities, dim_text_entities = collect_dim_entities(msp)
        
        # 치수선 시스템 처리
        processed_entities, cp_texts, entities_to_delete = process_dimension_system(msp, dim_text_entities, dim_line_entities)

        # 모든 처리가 완료된 후 삭제 대상 엔티티 삭제 (DEL1과 G1은 제외)
        for entity in entities_to_delete:
            try:
                msp.delete_entity(entity)
            except Exception as e:
                pass  # 조용히 무시
        
        # 처리 완료 후 TBOX 캐시 초기화
        clear_tbox_cache()
        
        return doc
        
    except Exception as e:
        # 에러 발생 시에도 TBOX 캐시 초기화
        clear_tbox_cache()
        return doc

# ─────────────── 메인 파이프라인 ───────────────
def auto_align_dxf(input_dxf, output_dxf):
    """
    단일 DXF 파일 처리 함수
    """
    if not os.path.isfile(input_dxf):
        return False
    
    try:
        # TBOX 캐시 초기화
        clear_tbox_cache()
        
        doc = ezdxf.readfile(input_dxf)
        
        # 런너 연동 함수 사용
        processed_doc = process(doc)
        
        # 저장
        processed_doc.saveas(output_dxf)
        
        return True
        
    except Exception as e:
        # 에러 발생 시에도 TBOX 캐시 초기화
        clear_tbox_cache()
        return False

def process_multiple_files_from_command_line(file_paths):
    """
    명령행에서 받은 여러 DXF 파일을 처리하는 함수
    전체 시간복잡도: O(k * n * m) where k = 파일 수, n = 파일당 DL 엔티티 수, m = 평균 검색 대상 엔티티 수
    """
    success_count = 0
    failed_files = []
    
    for input_file in file_paths:
        if not input_file.lower().endswith('.dxf'):
            continue
            
        if not os.path.isfile(input_file):
            failed_files.append(os.path.basename(input_file))
            continue
        
        file_dir = os.path.dirname(input_file)
        file_name = os.path.splitext(os.path.basename(input_file))[0]
        output_file = os.path.join(file_dir, f"{file_name}_DIM.dxf")
        
        if auto_align_dxf(input_file, output_file):
            success_count += 1
        else:
            failed_files.append(os.path.basename(input_file))
    
    return success_count, failed_files

# ─────────────── 메인 실행부 ───────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    
    # 명령행 인자로 받은 파일들 처리
    input_files = sys.argv[1:]
    success_count, failed_files = process_multiple_files_from_command_line(input_files)