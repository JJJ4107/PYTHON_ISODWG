import ezdxf
import tkinter as tk
from tkinter import filedialog
import math
import os
import traceback
import sys

CYAN = 4
RED = 1
YELLOW = 2
BLUE = 5
MAGENTA = 6
WHITE = 7
SL1_LENGTH = 3.5  # S1 평균 길이 (3~4mm의 중간값)
HALF_SL1 = 0.25  # 원의 반지름을 0.25mm로 변경 (직경 0.5mm)
LINE_LENGTH = 7.0  # 선의 길이 7mm로 변경
LINE_WIDTH = 0.6  # 선 두께 0.6
NODENO_RADIUS = 5.25  # NODENO 원의 반지름 10.5mm/2 = 5.25mm
NODENO_OFFSET_Y = 12.25  # Y방향 이동 거리 12.25mm로 변경
ROTATION_ANGLE = 30  # 회전 각도 (도)
TEXT_HEIGHT = 3.0  # 텍스트 높이 3mm
TEXT_VALUE = '0000'  # 텍스트 값

def calc_distance(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

def extract_points(ent):
    try:
        if not ent or not hasattr(ent, 'dxf') or ent.dxf is None:
            return []
        t = ent.dxftype()
        if t == 'LINE':
            return [(ent.dxf.start.x, ent.dxf.start.y), (ent.dxf.end.x, ent.dxf.end.y)]
        if t == 'LWPOLYLINE':
            return [tuple(pt[:2]) for pt in ent.get_points()]
        if t == 'POLYLINE':
            return [(v.dxf.location.x, v.dxf.location.y) for v in ent.vertices]
    except:
        pass
    return []

def has_curve(ent):
    t = ent.dxftype()
    if t == 'LWPOLYLINE':
        for pt in ent.get_points():
            if len(pt) > 4 and abs(pt[4]) > 1e-3:
                return True
    if t == 'POLYLINE':
        for v in ent.vertices:
            if hasattr(v.dxf, 'bulge') and abs(v.dxf.bulge) > 1e-3:
                return True
    return False

def polyline_length(pts):
    return sum(calc_distance(pts[i], pts[i+1]) for i in range(len(pts)-1))

def midpoint(pts):
    return (sum(p[0] for p in pts)/len(pts), sum(p[1] for p in pts)/len(pts))

def is_valid_s1(ent):
    if has_curve(ent): return False
    pts = extract_points(ent)
    if len(pts) != 2: return False
    L = polyline_length(pts)
    return 3.0 <= L <= 4.0  # S1 길이 조건 변경: 3.0~4.0mm

def point_at_distance(origin, target, dist):
    dx, dy = target[0] - origin[0], target[1] - origin[1]
    length = math.hypot(dx, dy)
    if length == 0:
        return origin
    ux, uy = dx / length, dy / length
    return (origin[0] + ux * dist, origin[1] + uy * dist)

def find_arrow_lines(msp, a1_points):
    """A1의 끝점에 접하는 ARROW 레이어의 1mm 이하 LINE 찾기"""
    arrow_lines = []
    for e in msp:
        if e.dxftype() == 'LINE' and e.dxf.layer == 'ARROW':
            line_pts = extract_points(e)
            if len(line_pts) == 2:
                line_length = calc_distance(line_pts[0], line_pts[1])
                if line_length <= 1.0:  # 1mm 이하
                    # A1의 각 끝점과 LINE의 끝점 간 거리 확인
                    for a1_pt in [a1_points[0], a1_points[-1]]:  # A1의 첫점과 끝점
                        for line_pt in line_pts:
                            if calc_distance(a1_pt, line_pt) <= 0.1:  # 0.1mm 이내면 접촉
                                arrow_lines.append(e)
                                break
    return arrow_lines

def get_pipe_angle(pts1, pts2):
    """두 S1 폴리라인에서 파이프의 주 방향 각도를 계산"""
    # 각 폴리라인의 방향 벡터 계산
    dir1 = (pts1[1][0] - pts1[0][0], pts1[1][1] - pts1[0][1])
    dir2 = (pts2[1][0] - pts2[0][0], pts2[1][1] - pts2[0][1])
    
    # 벡터의 크기 계산
    mag1 = math.hypot(dir1[0], dir1[1])
    mag2 = math.hypot(dir2[0], dir2[1])
    
    # 정규화된 벡터
    if mag1 > 0:
        norm1 = (dir1[0]/mag1, dir1[1]/mag1)
    else:
        norm1 = (0, 0)
        
    if mag2 > 0:
        norm2 = (dir2[0]/mag2, dir2[1]/mag2)
    else:
        norm2 = (0, 0)
    
    # 두 벡터의 내적을 계산하여 같은 방향인지 확인
    dot_product = norm1[0]*norm2[0] + norm1[1]*norm2[1]
    
    # 반대 방향이면 dir2를 반전
    if dot_product < -0.5:  # 대략 120도 이상 차이나면 반대 방향
        dir2 = (-dir2[0], -dir2[1])
    
    # 평균 방향 계산
    avg_dir = ((dir1[0] + dir2[0])/2, (dir1[1] + dir2[1])/2)
    
    # 평균 벡터가 영벡터인 경우 첫 번째 벡터 사용
    if abs(avg_dir[0]) < 0.01 and abs(avg_dir[1]) < 0.01:
        avg_dir = dir1
    
    # 각도 계산 (라디안)
    angle = math.atan2(avg_dir[1], avg_dir[0])
    
    return angle

def create_triangle_arrow(center, direction_angle, side_length, base_width, msp, color=CYAN, layer='SUPP', scale=1.0):
    """이등변 삼각형 화살표를 생성
    side_length: 양쪽 변의 길이 (2.8mm)
    base_width: 밑변의 길이 (1mm)
    scale: 중심점 기준 스케일 (0~1)
    """
    # 방향 각도를 라디안으로 변환
    angle_rad = math.radians(direction_angle)
    
    # 이등변 삼각형의 높이 계산
    # h = sqrt(side_length^2 - (base_width/2)^2)
    height = math.sqrt(side_length**2 - (base_width/2)**2)
    
    # 삼각형의 무게중심 계산 (꼭지점에서 높이의 2/3 지점)
    centroid_distance = height * 2/3
    centroid_x = center[0] + centroid_distance * math.cos(angle_rad)
    centroid_y = center[1] + centroid_distance * math.sin(angle_rad)
    centroid = (centroid_x, centroid_y)
    
    # 삼각형의 세 꼭지점 계산
    # 첫 번째 점: center (꼭지점)
    p1 = center
    
    # 두 번째 점: 왼쪽 밑변
    p2_x = center[0] - base_width/2 * math.cos(angle_rad + math.pi/2) + height * math.cos(angle_rad)
    p2_y = center[1] - base_width/2 * math.sin(angle_rad + math.pi/2) + height * math.sin(angle_rad)
    p2 = (p2_x, p2_y)
    
    # 세 번째 점: 오른쪽 밑변
    p3_x = center[0] + base_width/2 * math.cos(angle_rad + math.pi/2) + height * math.cos(angle_rad)
    p3_y = center[1] + base_width/2 * math.sin(angle_rad + math.pi/2) + height * math.sin(angle_rad)
    p3 = (p3_x, p3_y)
    
    # 스케일 적용 (무게중심 기준)
    if scale < 1.0:
        p1 = (centroid[0] + (p1[0] - centroid[0]) * scale,
              centroid[1] + (p1[1] - centroid[1]) * scale)
        p2 = (centroid[0] + (p2[0] - centroid[0]) * scale,
              centroid[1] + (p2[1] - centroid[1]) * scale)
        p3 = (centroid[0] + (p3[0] - centroid[0]) * scale,
              centroid[1] + (p3[1] - centroid[1]) * scale)
    
    # 삼각형 그리기 (닫힌 폴리라인)
    triangle_points = [p1, p2, p3, p1]
    
    try:
        msp.add_lwpolyline(
            triangle_points,
            dxfattribs={'color': color, 'layer': layer}
        )
    except:
        # 폴리라인이 실패하면 개별 선으로 그리기
        msp.add_line(p1, p2, dxfattribs={'color': color, 'layer': layer})
        msp.add_line(p2, p3, dxfattribs={'color': color, 'layer': layer})
        msp.add_line(p3, p1, dxfattribs={'color': color, 'layer': layer})

def create_iso_orthogonal_lines(center, pipe_angle, length, msp):
    """ISO 도면 기준으로 파이프에 직교하는 4개 방향으로 선을 생성"""
    lines = []
    line_angles = []  # 생성된 선의 각도를 저장
    
    # 파이프 각도를 도 단위로 변환
    pipe_angle_deg = math.degrees(pipe_angle) % 360
    
    # 파이프 각도를 30도 단위로 반올림하여 표준화
    normalized_angle = round(pipe_angle_deg / 30) * 30 % 360
    
    # 수직 파이프의 경우 약간의 오차 허용 (±5도)
    if 85 <= pipe_angle_deg <= 95 or 265 <= pipe_angle_deg <= 275:
        normalized_angle = 90 if pipe_angle_deg < 180 else 270
    
    # ISO 도면 표준에 따른 직교선 각도 결정
    if normalized_angle == 0 or normalized_angle == 180:  # 수평 파이프
        angles = [90, 270, 30, 210]
        
    elif normalized_angle == 90 or normalized_angle == 270:  # 수직 파이프
        angles = [30, 150, 210, 330]
        
    elif normalized_angle == 30 or normalized_angle == 210:  # 30도 경사 파이프
        angles = [90, 270, 150, 330]
        
    elif normalized_angle == 60 or normalized_angle == 240:  # 60도 경사 파이프
        angles = [90, 270, 180, 0]
        
    elif normalized_angle == 120 or normalized_angle == 300:  # 120도 경사 파이프
        angles = [90, 270, 60, 240]
        
    elif normalized_angle == 150 or normalized_angle == 330:  # 150도 경사 파이프
        angles = [90, 270, 30, 210]
        
    else:
        # 기타 각도: 파이프에 직교하는 방향 + ISO 표준 각도
        orth_angle = (pipe_angle_deg + 90) % 360
        orth_angle_normalized = round(orth_angle / 30) * 30
        
        angles = [
            orth_angle_normalized % 360,
            (orth_angle_normalized + 180) % 360,
            (orth_angle_normalized + 60) % 360,
            (orth_angle_normalized + 240) % 360
        ]
    
    # 각 방향으로 선 그리기
    for i, angle_deg in enumerate(angles[:4]):
        angle_rad = math.radians(angle_deg)
        
        # 원과의 교차점 계산 (trim을 위해)
        # cyan 원의 반지름은 HALF_SL1 = 0.25mm
        trim_start_x = center[0] + HALF_SL1 * math.cos(angle_rad)
        trim_start_y = center[1] + HALF_SL1 * math.sin(angle_rad)
        trim_start = (trim_start_x, trim_start_y)
        
        end_point = (center[0] + length * math.cos(angle_rad),
                     center[1] + length * math.sin(angle_rad))
        
        # Trim된 선 그리기 (원 밖에서부터)
        line = msp.add_line(trim_start, end_point, 
                          dxfattribs={'color': CYAN, 'lineweight': 60, 'layer': 'SUPP'})
        lines.append(line)
        line_angles.append(angle_deg)  # 선의 각도 저장
        
        # 삼각형 화살표 5개 그리기 (같은 위치에서 크기만 다르게)
        arrow_side_length = 4.0  # 양쪽 변의 길이 mm
        arrow_base_width = 1.4   # 밑변의 길이 mm
        
        for j in range(5):
            # 각 삼각형은 20%씩 작아짐
            scale = 1.0 - (j * 0.2)
            if scale <= 0:  # 스케일이 0 이하가 되면 중단
                break
            
            # 모든 삼각형은 cyan 원 중심에서 시작
            arrow_pos = center
            
            # 삼각형 그리기 (중심점 기준 스케일링)
            create_triangle_arrow(arrow_pos, angle_deg, arrow_side_length, arrow_base_width, msp, scale=scale)
    
    return lines, line_angles  # 선들과 각도들을 함께 반환

def rotate_point(point, center, angle_deg):
    """점을 중심점 기준으로 회전"""
    angle_rad = math.radians(angle_deg)
    cos_a = math.cos(angle_rad)
    sin_a = math.sin(angle_rad)
    
    dx = point[0] - center[0]
    dy = point[1] - center[1]
    
    new_x = center[0] + dx * cos_a - dy * sin_a
    new_y = center[1] + dx * sin_a + dy * cos_a
    
    return (new_x, new_y)

def find_best_orthogonal_position_for_special(cp, offset_distance, pipe_angle, msp, exclude_entities):
    """ELBO/TEE용 특별한 NODE 위치 결정 - 30도 단위로 모든 각도를 검사하여 최적 위치 찾기 (수직 제외)"""
    pipe_angle_deg = math.degrees(pipe_angle) % 360
    
    # 모든 가능한 각도 (30도 간격) - 수직(90도, 270도) 제외
    all_angles = [0, 30, 60, 120, 150, 180, 210, 240, 300, 330]
    
    print(f"      특수 노드: 파이프 각도={pipe_angle_deg:.1f}°")
    print(f"      수직 제외한 모든 각도에서 간섭 체크 시작...")
    
    # 각 가능한 방향에서의 간섭 체크
    best_angle = None
    min_interference_count = float('inf')
    no_interference_angles = []  # 간섭이 없는 각도들
    
    for angle in all_angles:
        angle_rad = math.radians(angle)
        test_pos = (cp[0] + offset_distance * math.cos(angle_rad),
                    cp[1] + offset_distance * math.sin(angle_rad))
        
        # 이 위치에서의 간섭 개수 계산
        interference_count = 0
        for ent in msp:
            if ent in exclude_entities:
                continue
                
            ent_type = ent.dxftype()
            if ent_type == 'CIRCLE':
                # 다른 원과의 거리 체크
                other_center = (ent.dxf.center.x, ent.dxf.center.y)
                other_radius = ent.dxf.radius
                dist = calc_distance(test_pos, other_center)
                if dist < (NODENO_RADIUS + other_radius + 1.0):  # 1mm 여유
                    interference_count += 1
            elif ent_type in ['LINE', 'LWPOLYLINE', 'POLYLINE']:
                # 선과의 거리 체크
                pts = extract_points(ent)
                for i in range(len(pts) - 1):
                    dist = point_to_line_distance(test_pos, pts[i], pts[i+1])
                    if dist < NODENO_RADIUS + 1.0:  # 1mm 여유
                        interference_count += 1
                        break
            elif ent_type == 'TEXT' or ent_type == 'MTEXT':
                # 텍스트와의 간섭도 체크
                if ent_type == 'TEXT':
                    text_pos = (ent.dxf.insert.x, ent.dxf.insert.y)
                else:
                    text_pos = (ent.dxf.insert.x, ent.dxf.insert.y)
                dist = calc_distance(test_pos, text_pos)
                if dist < NODENO_RADIUS + 2.0:  # 텍스트와 2mm 여유
                    interference_count += 1
        
        print(f"      {angle}° 방향: 간섭 {interference_count}개")
        
        # 간섭이 없는 각도 저장
        if interference_count == 0:
            no_interference_angles.append(angle)
        
        # 간섭이 가장 적은 방향 선택
        if interference_count < min_interference_count:
            min_interference_count = interference_count
            best_angle = angle
    
    # 간섭이 없는 각도가 있으면 그 중 첫 번째 선택
    if no_interference_angles:
        best_angle = no_interference_angles[0]
        print(f"      → 간섭 없는 각도 발견: {no_interference_angles}")
        print(f"      → 선택된 각도: {best_angle}°")
    else:
        print(f"      → 모든 각도에 간섭 있음. 최소 간섭 각도: {best_angle}° (간섭 {min_interference_count}개)")
    
    if best_angle is not None:
        angle_rad = math.radians(best_angle)
        best_pos = (cp[0] + offset_distance * math.cos(angle_rad),
                    cp[1] + offset_distance * math.sin(angle_rad))
        return best_pos
    
    # 기본값: 0도 방향
    angle_rad = math.radians(0)
    return (cp[0] + offset_distance * math.cos(angle_rad),
            cp[1] + offset_distance * math.sin(angle_rad))

def find_best_orthogonal_position(cp, offset_distance, pipe_angle, msp, exclude_entities, line_angles=None):
    """일반 NODE용 직교선 방향 중 간섭이 가장 적은 위치 찾기 - 수직 위치 제외"""
    pipe_angle_deg = math.degrees(pipe_angle) % 360
    normalized_angle = round(pipe_angle_deg / 30) * 30 % 360
    
    # 수직 파이프의 경우 약간의 오차 허용
    if 85 <= pipe_angle_deg <= 95 or 265 <= pipe_angle_deg <= 275:
        normalized_angle = 90 if pipe_angle_deg < 180 else 270
    
    # 파이프 각도에 따른 직교선 방향 결정
    if normalized_angle == 0 or normalized_angle == 180:  # 수평 파이프
        orthogonal_angles = [90, 270, 30, 210]
    elif normalized_angle == 90 or normalized_angle == 270:  # 수직 파이프
        orthogonal_angles = [30, 150, 210, 330]
    elif normalized_angle == 30 or normalized_angle == 210:  # 30도 경사
        orthogonal_angles = [90, 270, 150, 330]
    elif normalized_angle == 60 or normalized_angle == 240:  # 60도 경사
        orthogonal_angles = [90, 270, 180, 0]
    elif normalized_angle == 120 or normalized_angle == 300:  # 120도 경사
        orthogonal_angles = [90, 270, 60, 240]
    elif normalized_angle == 150 or normalized_angle == 330:  # 150도 경사
        orthogonal_angles = [90, 270, 30, 210]
    else:
        # 기타 각도: 파이프에 직교하는 방향
        orth_angle = (pipe_angle_deg + 90) % 360
        orth_angle_normalized = round(orth_angle / 30) * 30
        orthogonal_angles = [
            orth_angle_normalized % 360,
            (orth_angle_normalized + 180) % 360,
            (orth_angle_normalized + 60) % 360,
            (orth_angle_normalized + 240) % 360
        ]
    
    # 수직 위치(90도, 270도) 제외
    non_vertical_angles = [angle for angle in orthogonal_angles if angle != 90 and angle != 270]
    
    # 수직이 아닌 각도가 없으면 (모두 수직인 경우) 다른 각도 추가
    if not non_vertical_angles:
        non_vertical_angles = [0, 30, 60, 120, 150, 180, 210, 240, 300, 330]
    
    print(f"      가능한 NODE 위치 각도 (수직 제외): {non_vertical_angles}")
    
    # 각 직교선 방향에서의 간섭 체크
    best_angle = None
    min_interference_count = float('inf')
    
    for angle in non_vertical_angles:
        angle_rad = math.radians(angle)
        test_pos = (cp[0] + offset_distance * math.cos(angle_rad),
                    cp[1] + offset_distance * math.sin(angle_rad))
        
        # 이 위치에서의 간섭 개수 계산
        interference_count = 0
        for ent in msp:
            if ent in exclude_entities:
                continue
                
            ent_type = ent.dxftype()
            if ent_type == 'CIRCLE':
                # 다른 원과의 거리 체크
                other_center = (ent.dxf.center.x, ent.dxf.center.y)
                other_radius = ent.dxf.radius
                dist = calc_distance(test_pos, other_center)
                if dist < (NODENO_RADIUS + other_radius + 1.0):  # 1mm 여유
                    interference_count += 1
            elif ent_type in ['LINE', 'LWPOLYLINE', 'POLYLINE']:
                # 선과의 거리 체크
                pts = extract_points(ent)
                for i in range(len(pts) - 1):
                    dist = point_to_line_distance(test_pos, pts[i], pts[i+1])
                    if dist < NODENO_RADIUS + 1.0:  # 1mm 여유
                        interference_count += 1
                        break
        
        print(f"      {angle}° 방향: 간섭 {interference_count}개")
        
        # 간섭이 가장 적은 방향 선택
        if interference_count < min_interference_count:
            min_interference_count = interference_count
            best_angle = angle
    
    if best_angle is not None:
        angle_rad = math.radians(best_angle)
        best_pos = (cp[0] + offset_distance * math.cos(angle_rad),
                    cp[1] + offset_distance * math.sin(angle_rad))
        print(f"      → 최적 방향: {best_angle}° (간섭 {min_interference_count}개)")
        return best_pos, best_angle  # 선택된 각도도 반환
    
    # 기본값: 첫 번째 비수직 각도
    angle_rad = math.radians(non_vertical_angles[0])
    return (cp[0] + offset_distance * math.cos(angle_rad),
            cp[1] + offset_distance * math.sin(angle_rad)), non_vertical_angles[0]

def point_to_line_distance(point, line_start, line_end):
    """점과 선분 사이의 최단 거리 계산"""
    x0, y0 = point
    x1, y1 = line_start
    x2, y2 = line_end
    
    dx = x2 - x1
    dy = y2 - y1
    
    if dx == 0 and dy == 0:
        return calc_distance(point, line_start)
    
    t = ((x0 - x1) * dx + (y0 - y1) * dy) / (dx * dx + dy * dy)
    t = max(0, min(1, t))
    
    closest_point = (x1 + t * dx, y1 + t * dy)
    return calc_distance(point, closest_point)

def find_connected_pipes(elbo_pts, msp):
    """ELBO의 양 끝점에 연결된 PIPE 찾기 - PIPE TEXT가 포함된 레이어 검색"""
    start_point = elbo_pts[0]
    end_point = elbo_pts[-1]
    
    start_pipe = None
    end_pipe = None
    
    # PIPE TEXT가 포함된 레이어의 엔티티 검색
    for e in msp:
        if hasattr(e.dxf, 'layer') and 'PIPE' in e.dxf.layer:
            pts = extract_points(e)
            if len(pts) >= 2:
                # 시작점과 연결된 파이프 찾기
                for pt in pts:
                    if calc_distance(pt, start_point) < 0.5:  # 0.5mm 이내
                        start_pipe = {'entity': e, 'points': pts, 'connection': pt}
                        break
                
                # 끝점과 연결된 파이프 찾기
                for pt in pts:
                    if calc_distance(pt, end_point) < 0.5:  # 0.5mm 이내
                        end_pipe = {'entity': e, 'points': pts, 'connection': pt}
                        break
    
    return start_pipe, end_pipe

def find_line_intersection(p1, v1, p2, v2):
    """두 직선의 교점 찾기
    p1, p2: 각 직선 위의 점
    v1, v2: 각 직선의 방향 벡터
    """
    # 직선 방정식: P = P0 + t*V
    # 교점에서: P1 + t1*V1 = P2 + t2*V2
    
    det = v1[0]*v2[1] - v1[1]*v2[0]
    if abs(det) < 1e-10:  # 평행선
        return None
    
    dp = (p2[0] - p1[0], p2[1] - p1[1])
    t1 = (dp[0]*v2[1] - dp[1]*v2[0]) / det
    
    # 교점 계산
    intersection = (p1[0] + t1*v1[0], p1[1] + t1*v1[1])
    return intersection

def find_elbow_vertices(msp):
    """ELBO 레이어에서 파이프 연장선의 교점(바깥쪽 꼭지점) 찾기"""
    elbow_vertices = []
    elbo_count = 0
    
    for e in msp:
        if hasattr(e.dxf, 'layer') and e.dxf.layer == 'ELBO':
            elbo_count += 1
            pts = extract_points(e)
            print(f"    ELBO 엔티티 발견: {e.dxftype()}, 점 개수: {len(pts)}")
            
            if len(pts) >= 2:
                # ELBO의 양 끝에 연결된 PIPE 찾기
                start_pipe, end_pipe = find_connected_pipes(pts, msp)
                
                if start_pipe and end_pipe:
                    # 각 파이프의 방향 벡터 계산
                    # 시작 파이프의 방향 (ELBO와 연결된 점에서 멀어지는 방향)
                    if calc_distance(start_pipe['points'][0], start_pipe['connection']) < 0.5:
                        v1 = (start_pipe['points'][1][0] - start_pipe['points'][0][0],
                              start_pipe['points'][1][1] - start_pipe['points'][0][1])
                    else:
                        v1 = (start_pipe['points'][-2][0] - start_pipe['points'][-1][0],
                              start_pipe['points'][-2][1] - start_pipe['points'][-1][1])
                    
                    # 끝 파이프의 방향
                    if calc_distance(end_pipe['points'][0], end_pipe['connection']) < 0.5:
                        v2 = (end_pipe['points'][1][0] - end_pipe['points'][0][0],
                              end_pipe['points'][1][1] - end_pipe['points'][0][1])
                    else:
                        v2 = (end_pipe['points'][-2][0] - end_pipe['points'][-1][0],
                              end_pipe['points'][-2][1] - end_pipe['points'][-1][1])
                    
                    # 두 파이프 연장선의 교점 찾기
                    intersection = find_line_intersection(pts[0], v1, pts[-1], v2)
                    
                    if intersection:
                        elbow_vertices.append({
                            'point': intersection,
                            'angle': 90,
                            'entity': e,
                            'direction': (v1, v2)
                        })
                        print(f"      → 파이프 연장선 교점(바깥쪽): ({intersection[0]:.1f}, {intersection[1]:.1f})")
                    else:
                        # 교점을 찾지 못한 경우 중점 사용
                        mid_point = midpoint(pts)
                        elbow_vertices.append({
                            'point': mid_point,
                            'angle': 180,
                            'entity': e,
                            'direction': ((1, 0), (0, 1))
                        })
                        print(f"      → 교점을 찾지 못해 중점 사용")
                else:
                    # PIPE를 찾지 못한 경우 ELBO의 양 끝 방향 벡터로 추정
                    if len(pts) >= 3:
                        # 첫 부분의 방향
                        v1 = (pts[0][0] - pts[1][0], pts[0][1] - pts[1][1])
                        # 끝 부분의 방향
                        v2 = (pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1])
                        
                        # 교점 계산
                        intersection = find_line_intersection(pts[0], v1, pts[-1], v2)
                        
                        if intersection:
                            elbow_vertices.append({
                                'point': intersection,
                                'angle': 90,
                                'entity': e,
                                'direction': (v1, v2)
                            })
                            print(f"      → ELBO 자체 방향으로 교점 계산: ({intersection[0]:.1f}, {intersection[1]:.1f})")
                    else:
                        # 2점만 있는 경우 중점 사용
                        mid_point = midpoint(pts)
                        v1 = (pts[1][0] - pts[0][0], pts[1][1] - pts[0][1])
                        elbow_vertices.append({
                            'point': mid_point,
                            'angle': 180,
                            'entity': e,
                            'direction': (v1, v1)
                        })
                        print(f"      → 2점 LINE의 중점 사용")
    
    print(f"    ELBO 엔티티 총 {elbo_count}개, 꼭지점 {len(elbow_vertices)}개 발견")
    return elbow_vertices

def find_tee_junction_points(msp):
    """TEE TEXT가 포함된 레이어에서 3개 점이 만나는 점 찾기"""
    tee_points = []
    tee_entities = []
    
    # TEE TEXT가 포함된 레이어의 모든 엔티티 수집
    for e in msp:
        if hasattr(e.dxf, 'layer') and 'TEE' in e.dxf.layer:
            if e.dxftype() in ['LWPOLYLINE', 'POLYLINE']:
                pts = extract_points(e)
                if pts:
                    tee_entities.append({'entity': e, 'points': pts})
                    print(f"    TEE 엔티티 발견: 레이어={e.dxf.layer}, 점 개수={len(pts)}")
    
    print(f"    TEE 엔티티 총 {len(tee_entities)}개 발견")
    
    # 모든 점들을 수집하고 중복 점 찾기
    point_count = {}
    point_entities = {}
    
    for item in tee_entities:
        for pt in item['points']:
            # 점을 문자열로 변환하여 키로 사용 (0.1mm 정밀도)
            key = f"{pt[0]:.1f},{pt[1]:.1f}"
            
            if key not in point_count:
                point_count[key] = 0
                point_entities[key] = []
            
            point_count[key] += 1
            point_entities[key].append(item['entity'])
    
    # 3개 이상의 선이 만나는 점 찾기
    for key, count in point_count.items():
        if count >= 3:
            x, y = map(float, key.split(','))
            tee_points.append({
                'point': (x, y),
                'count': count,
                'entities': point_entities[key]
            })
            print(f"      3방향 분기점 발견: ({x:.1f}, {y:.1f}) - {count}개 연결")
    
    print(f"    TEE 분기점 총 {len(tee_points)}개 발견")
    return tee_points

def add_text_to_node(msp, center, text_value, height, color, layer, doc=None):
    """NODE에 텍스트 추가 - (0,0)에 생성 후 NODE 중심으로 이동"""
    try:
        print(f"\n      === 텍스트 추가 시작 ===")
        print(f"      목표 NODE 중심: ({center[0]:.2f}, {center[1]:.2f})")
        
        # ARIAL 스타일이 없으면 생성
        if doc and "ARIAL" not in doc.styles:
            try:
                doc.styles.new("ARIAL", dxfattribs={"font": "arial.ttf"})
            except:
                pass
        
        # 1단계: (0, 0) 위치에 TEXT 생성
        text = msp.add_text(
            text_value,
            dxfattribs={
                'height': 3.5,  # 3.5mm 높이
                'color': MAGENTA,  # MAGENTA 색상
                'layer': layer,
                'insert': (0, 0, 0),  # (0, 0) 위치에 생성
                'halign': 4,  # CENTER
                'valign': 2,  # MIDDLE
                'style': 'ARIAL' if doc else 'Standard',
                'width': 0.85
            }
        )
        print(f"      [1단계] 텍스트 '0000' (0,0)에 생성 완료")
        
        # 2단계: transform을 사용하여 이동
        try:
            from ezdxf.math import Matrix44
            # 이동 변환 행렬 생성
            transform = Matrix44.translate(center[0], center[1], 0)
            # 텍스트에 변환 적용
            text.transform(transform)
            print(f"      [2단계] transform으로 ({center[0]:.2f}, {center[1]:.2f})로 이동 완료")
            
            # 이동 확인
            new_pos = text.dxf.insert
            if hasattr(new_pos, 'x'):
                print(f"      → 이동 후 실제 위치: ({new_pos.x:.2f}, {new_pos.y:.2f})")
            else:
                print(f"      → 이동 후 실제 위치: ({new_pos[0]:.2f}, {new_pos[1]:.2f})")
            
            return text
            
        except Exception as e:
            print(f"      → transform 실패: {e}")
            
            # transform이 실패하면 삭제 후 재생성
            print(f"      → 삭제 후 재생성 시도")
            try:
                msp.delete_entity(text)
                print(f"      → (0,0)의 텍스트 삭제됨")
            except:
                print(f"      → 삭제 실패, 그래도 계속 진행")
            
            # NODE 중심에 새로 생성
            new_text = msp.add_text(
                text_value,
                dxfattribs={
                    'height': 3.5,
                    'color': MAGENTA,
                    'layer': layer,
                    'insert': (center[0], center[1], 0),
                    'halign': 4,
                    'valign': 2,
                    'style': 'ARIAL' if doc else 'Standard',
                    'width': 0.85
                }
            )
            print(f"      [재생성] NODE 중심 ({center[0]:.2f}, {center[1]:.2f})에 텍스트 생성 완료")
            return new_text
        
    except Exception as e:
        print(f"      ❌ 전체 프로세스 실패: {e}")
        import traceback
        traceback.print_exc()
        
        # 최후의 시도: NODE 중심에 직접 생성
        try:
            text = msp.add_text(
                text_value,
                dxfattribs={
                    'height': 3.5,
                    'color': MAGENTA,
                    'layer': layer,
                    'insert': (center[0], center[1], 0),
                    'halign': 4,
                    'valign': 2,
                    'style': 'Standard'
                }
            )
            print(f"      [최종] NODE 중심에 직접 생성")
            return text
        except Exception as e2:
            print(f"      ❌ 최종 생성도 실패: {e2}")
            return None

def process_special_nodes(msp, doc):
    """ELBO와 TEE TEXT 레이어의 특수 노드 처리"""
    processed_count = 0
    texts_to_add = []  # 텍스트 추가를 위한 리스트
    
    # ELBO 처리
    # ELBO 레이어의 모든 엔티티를 CYAN으로 변경
    elbo_count = 0
    for e in msp:
        if hasattr(e.dxf, 'layer') and e.dxf.layer == 'ELBO':
            e.dxf.color = CYAN
            elbo_count += 1
    if elbo_count > 0:
        print(f"  ELBO 레이어 {elbo_count}개 엔티티 색상을 CYAN으로 변경")
    
    elbow_vertices = find_elbow_vertices(msp)
    for elbow in elbow_vertices:
        center_point = elbow['point']
        
        # 파이프 방향 추정 (엘보의 두 방향 벡터의 평균)
        v1, v2 = elbow['direction']
        avg_dir = ((v1[0] + v2[0])/2, (v1[1] + v2[1])/2)
        pipe_angle = math.atan2(avg_dir[1], avg_dir[0])
        
        # NODENO 원 위치 결정 (30도 단위로 회전하며 간섭 체크)
        nodeno_pos = find_best_orthogonal_position_for_special(
            center_point, NODENO_OFFSET_Y, pipe_angle, msp, []
        )
        
        # NODENO 원 그리기
        nodeno_circle = msp.add_circle(
            center=nodeno_pos, 
            radius=NODENO_RADIUS, 
            dxfattribs={'color': MAGENTA, 'layer': 'NODE'}
        )
        
        # center_point와 NODENO 중심을 잇는 선 (NODE 원에서 trim)
        dx = nodeno_pos[0] - center_point[0]
        dy = nodeno_pos[1] - center_point[1]
        distance = math.hypot(dx, dy)
        
        if distance > 0:
            ux = dx / distance
            uy = dy / distance
            trim_end_x = nodeno_pos[0] - ux * NODENO_RADIUS
            trim_end_y = nodeno_pos[1] - uy * NODENO_RADIUS
            
            msp.add_line(
                center_point, 
                (trim_end_x, trim_end_y), 
                dxfattribs={'color': WHITE, 'layer': 'NODE'}
            )
        
        # 텍스트 추가를 위해 저장
        texts_to_add.append(nodeno_pos)
        
        processed_count += 1
        print(f"  ELBO 노드 처리: ({center_point[0]:.2f}, {center_point[1]:.2f})")
    
    # TEE TEXT 처리
    tee_points = find_tee_junction_points(msp)
    
    # TEE가 포함된 모든 엔티티의 색상을 CYAN으로 변경
    tee_layer_count = 0
    for e in msp:
        if hasattr(e.dxf, 'layer') and 'TEE' in e.dxf.layer:
            e.dxf.color = CYAN
            tee_layer_count += 1
    if tee_layer_count > 0:
        print(f"  TEE 레이어 {tee_layer_count}개 엔티티 색상을 CYAN으로 변경")
    
    for tee in tee_points:
        center_point = tee['point']
        
        # TEE의 경우 연결된 파이프 방향을 추정
        # 3개 이상의 선이 만나므로 가장 긴 두 선의 방향 평균 사용
        pipe_angle = 0  # 기본값
        
        # 연결된 엔티티들에서 방향 추정 시도
        if tee['entities']:
            directions = []
            for ent in tee['entities'][:2]:  # 처음 2개만 사용
                pts = extract_points(ent)
                if len(pts) >= 2:
                    # 중심점에 가장 가까운 두 점을 찾아 방향 계산
                    for i in range(len(pts)-1):
                        if calc_distance(pts[i], center_point) < 1.0:
                            dir_vec = (pts[i+1][0] - pts[i][0], pts[i+1][1] - pts[i][1])
                            directions.append(dir_vec)
                            break
                        elif calc_distance(pts[i+1], center_point) < 1.0:
                            dir_vec = (pts[i][0] - pts[i+1][0], pts[i][1] - pts[i+1][1])
                            directions.append(dir_vec)
                            break
            
            if directions:
                avg_dir = (sum(d[0] for d in directions)/len(directions), 
                          sum(d[1] for d in directions)/len(directions))
                if abs(avg_dir[0]) > 0.01 or abs(avg_dir[1]) > 0.01:
                    pipe_angle = math.atan2(avg_dir[1], avg_dir[0])
        
        # NODENO 원 위치 결정 (30도 단위로 회전하며 간섭 체크)
        nodeno_pos = find_best_orthogonal_position_for_special(
            center_point, NODENO_OFFSET_Y, pipe_angle, msp, []
        )
        
        # NODENO 원 그리기
        nodeno_circle = msp.add_circle(
            center=nodeno_pos, 
            radius=NODENO_RADIUS, 
            dxfattribs={'color': MAGENTA, 'layer': 'NODE'}
        )
        
        # center_point와 NODENO 중심을 잇는 선 (NODE 원에서 trim)
        dx = nodeno_pos[0] - center_point[0]
        dy = nodeno_pos[1] - center_point[1]
        distance = math.hypot(dx, dy)
        
        if distance > 0:
            ux = dx / distance
            uy = dy / distance
            trim_end_x = nodeno_pos[0] - ux * NODENO_RADIUS
            trim_end_y = nodeno_pos[1] - uy * NODENO_RADIUS
            
            msp.add_line(
                center_point, 
                (trim_end_x, trim_end_y), 
                dxfattribs={'color': WHITE, 'layer': 'NODE'}
            )
        
        # 텍스트 추가를 위해 저장
        texts_to_add.append(nodeno_pos)
        
        processed_count += 1
        print(f"  TEE 노드 처리: ({center_point[0]:.2f}, {center_point[1]:.2f}) - {tee['count']}개 연결")
    
    # 모든 그래픽 요소 처리 후 텍스트 추가
    for text_pos in texts_to_add:
        add_text_to_node(msp, text_pos, TEXT_VALUE, TEXT_HEIGHT, YELLOW, 'NODE', doc)
    
    return processed_count

def find_texts_with_hyphen(msp, center_point, radius):
    """중심점에서 반경 내의 '-'가 포함된 TEXT 엔티티 찾기"""
    texts = []
    for e in msp:
        if e.dxftype() == 'TEXT' or e.dxftype() == 'MTEXT':
            text_content = ""
            text_pos = None
            
            if e.dxftype() == 'TEXT':
                text_content = e.dxf.text
                text_pos = (e.dxf.insert.x, e.dxf.insert.y)
            elif e.dxftype() == 'MTEXT':
                text_content = e.text
                text_pos = (e.dxf.insert.x, e.dxf.insert.y)
            
            if text_pos and '-' in text_content:
                dist = calc_distance(center_point, text_pos)
                if dist <= radius:
                    texts.append({
                        'entity': e,
                        'content': text_content,
                        'position': text_pos,
                        'distance': dist
                    })
    
    return texts

def get_text_bounding_box(text_entity):
    """TEXT 엔티티의 바운딩 박스 계산"""
    if text_entity.dxftype() == 'TEXT':
        # 간단한 추정 (정확하지 않을 수 있음)
        text_height = text_entity.dxf.height
        text_content = text_entity.dxf.text
        text_width = len(text_content) * text_height * 0.6  # 추정값
        
        pos = (text_entity.dxf.insert.x, text_entity.dxf.insert.y)
        
        # 4개의 모서리 점
        corners = [
            pos,  # 좌하
            (pos[0] + text_width, pos[1]),  # 우하
            (pos[0] + text_width, pos[1] + text_height),  # 우상
            (pos[0], pos[1] + text_height)  # 좌상
        ]
        
        return corners
    
    elif text_entity.dxftype() == 'MTEXT':
        # MTEXT의 경우
        pos = (text_entity.dxf.insert.x, text_entity.dxf.insert.y)
        height = text_entity.dxf.char_height
        
        # 텍스트 내용에서 실제 텍스트만 추출
        text_content = text_entity.text
        # MTEXT 포맷 코드 제거 (간단한 방법)
        import re
        clean_text = re.sub(r'\\[^;]+;', '', text_content)
        
        width = len(clean_text) * height * 0.6  # 추정값
        
        corners = [
            (pos[0] - width/2, pos[1] - height/2),  # 좌하
            (pos[0] + width/2, pos[1] - height/2),  # 우하
            (pos[0] + width/2, pos[1] + height/2),  # 우상
            (pos[0] - width/2, pos[1] + height/2)   # 좌상
        ]
        
        return corners
    
    return []

def process_type2_support(msp, a1_data, a2_data, ct_entity, cp_center, orthogonal_lines, line_angles, pipe_angle, node_angle):
    """2단계 지원 처리"""
    if not a2_data or not ct_entity:
        return None
    
    # AP1, AP2는 이미 찾았으므로 다시 계산
    a1_center = midpoint(a1_data['pts'])
    a2_pts = a2_data['pts']
    
    ap1 = min(a2_pts, key=lambda p: calc_distance(p, a1_center))
    ap2 = max(a2_pts, key=lambda p: calc_distance(p, a1_center))
    
    print(f"\n  2단계 처리:")
    print(f"    AP1: ({ap1[0]:.2f}, {ap1[1]:.2f})")
    print(f"    AP2: ({ap2[0]:.2f}, {ap2[1]:.2f})")
    
    # CT는 이미 찾았으므로 사용
    if ct_entity.dxftype() == 'TEXT':
        ct_content = ct_entity.dxf.text
    else:  # MTEXT
        ct_content = ct_entity.text
        
    print(f"    CT 내용: '{ct_content}'")
    
    # CT 내용에서 뒤에서 첫번째 '-' 찾고 다음 글자를 STYPE으로
    last_hyphen_idx = ct_content.rfind('-')
    
    if last_hyphen_idx == -1 or last_hyphen_idx == len(ct_content) - 1:
        print("    STYPE을 추출할 수 없음")
        return None
    
    stype = ct_content[last_hyphen_idx + 1]
    print(f"    STYPE: '{stype}'")
    
    # STYPE에 따른 처리
    if stype in ['G', 'A']:
        print("    STYPE이 G 또는 A - 특수 화살표 처리")
        
        # NODE가 없는 각도의 LINE 찾기 (L1)
        l1_angle = None
        for i, angle in enumerate(line_angles):
            if angle != node_angle:  # NODE가 있는 각도가 아닌 것
                l1_angle = angle
                break
        
        if l1_angle is None:
            print("    L1을 찾을 수 없음")
            return None
        
        # PIPE 각도 계산
        pipe_angle_deg = math.degrees(pipe_angle)
        print(f"    L1 각도: {l1_angle}°")
        print(f"    PIPE 각도: {pipe_angle_deg:.1f}°")
        
        # CP점에서 5.5mm 떨어진 지점 계산 (L1 방향)
        angle_rad = math.radians(l1_angle)
        intersection_point = (
            cp_center[0] - 5.5 * math.cos(angle_rad),
            cp_center[1] - 5.5 * math.sin(angle_rad)
        )
        
        # PIPE와 동일한 기울기로 L1 라인 기준 교차하는 양쪽으로 5mm cyan 선 그리기
        perp_angle_rad = math.radians(pipe_angle_deg)
        
        # 양쪽 끝점 계산
        p1 = (
            intersection_point[0] - 5.0 * math.cos(perp_angle_rad),
            intersection_point[1] - 5.0 * math.sin(perp_angle_rad)
        )
        p2 = (
            intersection_point[0] + 5.0 * math.cos(perp_angle_rad),
            intersection_point[1] + 5.0 * math.sin(perp_angle_rad)
        )
        
        # 10mm cyan 선 그리기
        msp.add_line(p1, p2, dxfattribs={'color': CYAN, 'layer': 'SUPP'})
        
        # PIPE 방향으로 양방향 삼각형 그리기
        arrow_side_length = 4.0
        arrow_base_width = 1.4
        
        # 첫 번째 방향 (PIPE 방향)
        for j in range(5):
            scale = 1.0 - (j * 0.2)
            if scale <= 0:
                break
            create_triangle_arrow(intersection_point, pipe_angle_deg, arrow_side_length, arrow_base_width, msp, scale=scale)
        
        # 두 번째 방향 (PIPE 반대 방향)
        opposite_angle = (pipe_angle_deg + 180) % 360
        for j in range(5):
            scale = 1.0 - (j * 0.2)
            if scale <= 0:
                break
            create_triangle_arrow(intersection_point, opposite_angle, arrow_side_length, arrow_base_width, msp, scale=scale)
    
    elif stype in ['C', 'V']:
        print("    STYPE이 C 또는 V - 수직선 처리")
        
        # 수직인 두 선(90도, 270도) 찾기
        vertical_lines = []
        for i, angle in enumerate(line_angles):
            if angle == 90 or angle == 270:
                vertical_lines.append((orthogonal_lines[i], angle))
        
        if len(vertical_lines) < 2:
            print("    수직선을 찾을 수 없음")
            return None
        
        # 각 수직선에 대해 처리
        for line, angle in vertical_lines:
            angle_rad = math.radians(angle)
            
            # 5mm, 6mm, 7mm 떨어진 지점
            distances = [5.0, 6.0, 7.0]
            points = []
            
            for dist in distances:
                point = (
                    cp_center[0] + dist * math.cos(angle_rad),
                    cp_center[1] + dist * math.sin(angle_rad)
                )
                points.append(point)
                
                # PIPE 기울기와 동일하게 교차하는 3mm 흰색 선
                pipe_angle_deg = math.degrees(pipe_angle)
                perp_angle_rad = math.radians(pipe_angle_deg)
                
                p1 = (
                    point[0] - 1.5 * math.cos(perp_angle_rad),
                    point[1] - 1.5 * math.sin(perp_angle_rad)
                )
                p2 = (
                    point[0] + 1.5 * math.cos(perp_angle_rad),
                    point[1] + 1.5 * math.sin(perp_angle_rad)
                )
                
                msp.add_line(p1, p2, dxfattribs={'color': WHITE, 'layer': 'SUPP'})
            
            # 5mm 선의 끝점과 6mm 선의 시작점 연결
            # 여기서는 각 교차선의 끝점을 사용
            pipe_angle_deg = math.degrees(pipe_angle)
            perp_angle_rad = math.radians(pipe_angle_deg)
            
            # 5mm 위치의 끝점
            p5_end = (
                points[0][0] + 1.5 * math.cos(perp_angle_rad),
                points[0][1] + 1.5 * math.sin(perp_angle_rad)
            )
            # 6mm 위치의 시작점
            p6_start = (
                points[1][0] - 1.5 * math.cos(perp_angle_rad),
                points[1][1] - 1.5 * math.sin(perp_angle_rad)
            )
            msp.add_line(p5_end, p6_start, dxfattribs={'color': WHITE, 'layer': 'SUPP'})
            
            # 6mm 선의 끝점과 7mm 선의 시작점 연결
            p6_end = (
                points[1][0] + 1.5 * math.cos(perp_angle_rad),
                points[1][1] + 1.5 * math.sin(perp_angle_rad)
            )
            p7_start = (
                points[2][0] - 1.5 * math.cos(perp_angle_rad),
                points[2][1] - 1.5 * math.sin(perp_angle_rad)
            )
            msp.add_line(p6_end, p7_start, dxfattribs={'color': WHITE, 'layer': 'SUPP'})
    
    return None  # CT는 이미 삭제 목록에 추가됨

def main():
    root = tk.Tk(); root.withdraw()
    files = filedialog.askopenfilenames(title="DXF 파일 선택", filetypes=[("DXF Files", "*.dxf")])
    if not files:
        print("선택된 파일 없음"); return

    for filepath in files:
        print(f"\n🔧 처리중: {filepath}")
        try:
            doc = ezdxf.readfile(filepath)
            msp = doc.modelspace()
            
            # NODE, SUPP, AD1, AD2, AD3 레이어가 없으면 생성
            if 'NODE' not in doc.layers:
                doc.layers.new('NODE')
            if 'SUPP' not in doc.layers:
                doc.layers.new('SUPP')
            if 'AD1' not in doc.layers:
                doc.layers.new('AD1')
            if 'AD2' not in doc.layers:
                doc.layers.new('AD2')
            if 'AD3' not in doc.layers:
                doc.layers.new('AD3')

            s1_list = []
            for e in msp:
                if is_valid_s1(e):
                    pts = extract_points(e)
                    if pts and len(pts) == 2:
                        s1_list.append({'ent': e, 'pts': pts})
            
            print(f"\n✅ 유효한 S1 개수: {len(s1_list)}")

            # 1단계 처리 - AD1, AD2, AD3를 저장하고 나중에 삭제
            entities_to_delete = []  # 삭제할 엔티티들
            ct_entities_to_delete = []  # CT 엔티티들
            
            # 먼저 AD1, AD2, AD3와 관련된 정보를 수집하는 루프
            a1_a2_info = []
            for rec1 in s1_list:
                for rec2 in s1_list:
                    if rec1 is rec2: continue
                    if not hasattr(rec1['ent'], 'dxf') or not hasattr(rec2['ent'], 'dxf'):
                        continue
                    
                    # 두 S1의 길이 차이가 0.2mm 이내여야 함
                    len1 = polyline_length(rec1['pts'])
                    len2 = polyline_length(rec2['pts'])
                    if abs(len1 - len2) > 0.2:
                        continue
                    
                    # 각 점 간의 거리 계산
                    all_distances = [calc_distance(a, b) for a in rec1['pts'] for b in rec2['pts']]
                    dmin = min(all_distances)
                    dmax = max(all_distances)
                    
                    # 점 간 거리는 3.5~7mm 사이여야 함
                    if not (3.5 <= dmin <= 7.0 and 3.5 <= dmax <= 7.0):
                        continue
                    
                    # 두 폴리라인의 점들이 0.2mm 범위에서 같은 위치에 있으면 PASS
                    if any(calc_distance(p1, p2) <= 0.2 for p1 in rec1['pts'] for p2 in rec2['pts']):
                        continue

                    sp1, ep1 = rec1['pts']
                    sp2, ep2 = rec2['pts']
                    print(f"S1-S2 검증: 길이차={abs(len1-len2):.3f}mm")
                    print(f"  거리: sp1-sp2={calc_distance(sp1, sp2):.2f} "
                          f"sp1-ep2={calc_distance(sp1, ep2):.2f} "
                          f"ep1-sp2={calc_distance(ep1, sp2):.2f} "
                          f"ep1-ep2={calc_distance(ep1, ep2):.2f}")

                    rec1['ent'].dxf.color = CYAN
                    rec2['ent'].dxf.color = CYAN
                    
                    # 0.5mm CYAN 원의 중심 (S1 쌍의 중심)
                    center_sl1 = midpoint([midpoint(rec1['pts']), midpoint(rec2['pts'])])
                    
                    # AD1 찾기: CYAN 원 중심에서 4mm 이내, GT_1 레이어, 3점, 길이 5이하
                    AD1 = None
                    for e in msp:
                        if hasattr(e.dxf, 'layer') and e.dxf.layer == 'GT_1':
                            pts = extract_points(e)
                            if len(pts) == 3:
                                # 길이 계산
                                length = polyline_length(pts)
                                if length <= 5.0:
                                    # 중심에서 4mm 이내인지 확인
                                    if any(calc_distance(p, center_sl1) <= 4.0 for p in pts):
                                        AD1 = {'ent': e, 'pts': pts}
                                        break
                    
                    if not AD1: 
                        continue
                    
                    # AD1 레이어와 색상 설정
                    AD1['ent'].dxf.layer = 'AD1'
                    AD1['ent'].dxf.color = RED
                    print(f"  AD1 발견: 3점 폴리라인, 길이={polyline_length(AD1['pts']):.2f}mm")
                    
                    # AD2 찾기: AD1의 점에서 0.1mm 내, ARROW 레이어, 1mm 이하 LINE
                    AD2_list = []
                    for e in msp:
                        if e.dxftype() == 'LINE' and hasattr(e.dxf, 'layer') and e.dxf.layer == 'ARROW':
                            line_pts = extract_points(e)
                            if len(line_pts) == 2:
                                line_length = calc_distance(line_pts[0], line_pts[1])
                                if line_length <= 1.0:
                                    # AD1의 점과 0.1mm 이내인지 확인
                                    for ad1_pt in AD1['pts']:
                                        for line_pt in line_pts:
                                            if calc_distance(ad1_pt, line_pt) <= 0.1:
                                                e.dxf.layer = 'AD2'
                                                e.dxf.color = RED
                                                AD2_list.append(e)
                                                print(f"  AD2 발견: LINE, 길이={line_length:.3f}mm")
                                                break
                                        if e in AD2_list:
                                            break
                    
                    # AD3 찾기: AD1의 점에서 0.1mm 내, PL2 레이어 폴리라인
                    AD3 = None
                    for e in msp:
                        if hasattr(e.dxf, 'layer') and e.dxf.layer == 'PL2':
                            if e.dxftype() in ['LWPOLYLINE', 'POLYLINE']:
                                pts = extract_points(e)
                                if pts:
                                    # AD1의 점과 0.1mm 이내인지 확인
                                    for ad1_pt in AD1['pts']:
                                        for pt in pts:
                                            if calc_distance(ad1_pt, pt) <= 0.1:
                                                AD3 = {'ent': e, 'pts': pts}
                                                e.dxf.layer = 'AD3'
                                                e.dxf.color = RED
                                                print(f"  AD3 발견: {e.dxftype()}, 점 개수={len(pts)}")
                                                break
                                        if AD3:
                                            break
                                if AD3:
                                    break
                    
                    if not AD3:
                        continue
                    
                    # AP1, AP2 찾기
                    ad1_center = midpoint(AD1['pts'])
                    ap1 = min(AD3['pts'], key=lambda p: calc_distance(p, ad1_center))
                    ap2 = max(AD3['pts'], key=lambda p: calc_distance(p, ad1_center))
                    print(f"  AP1: ({ap1[0]:.2f}, {ap1[1]:.2f}), AP2: ({ap2[0]:.2f}, {ap2[1]:.2f})")
                    
                    # CT 찾기: AP2에서 X: -70~+15mm, Y: ±7mm 범위, 기울기 0, '-' 포함 TEXT
                    CT = None
                    for e in msp:
                        if e.dxftype() in ['TEXT', 'MTEXT']:
                            text_content = ""
                            text_pos = None
                            
                            if e.dxftype() == 'TEXT':
                                text_content = e.dxf.text
                                text_pos = (e.dxf.insert.x, e.dxf.insert.y)
                                # 기울기 0 확인 (rotation이 0이거나 없음)
                                if hasattr(e.dxf, 'rotation') and abs(e.dxf.rotation) > 0.1:
                                    continue
                            elif e.dxftype() == 'MTEXT':
                                text_content = e.text
                                text_pos = (e.dxf.insert.x, e.dxf.insert.y)
                            
                            if text_pos and '-' in text_content:
                                # 범위 확인
                                dx = text_pos[0] - ap2[0]
                                dy = text_pos[1] - ap2[1]
                                
                                if -70 <= dx <= 15 and -7 <= dy <= 7:
                                    CT = e
                                    e.dxf.color = RED
                                    print(f"  CT 발견: '{text_content}' at ({text_pos[0]:.2f}, {text_pos[1]:.2f})")
                                    break
                    
                    # AD1, AD2, AD3, CT 정보 저장
                    a1_a2_info.append({
                        's1': rec1,
                        's2': rec2,
                        'a1': AD1,  # AD1으로 사용
                        'a2': AD3,  # AD3를 a2로 사용 (2단계 처리를 위해)
                        'ad2_list': AD2_list,  # AD2 리스트 저장
                        'ct': CT,
                        'center': center_sl1
                    })
                    
                    # 삭제할 엔티티 목록에 추가
                    entities_to_delete.append(AD1['ent'])
                    entities_to_delete.extend(AD2_list)
                    entities_to_delete.append(AD3['ent'])
                    if CT:
                        ct_entities_to_delete.append(CT)
                    
                    break

            # S1 쌍을 찾아 CP 원, 직교선, NODE 생성하는 루프
            supptag = []
            created_circles = []
            texts_to_add = []  # 텍스트 추가를 위한 리스트
            
            for rec1 in list(s1_list):
                for rec2 in list(s1_list):
                    if rec1 is rec2: continue
                    if not hasattr(rec1['ent'], 'dxf') or not hasattr(rec2['ent'], 'dxf'):
                        continue
                    
                    # 두 S1의 길이 차이가 0.2mm 이내여야 함
                    len1 = polyline_length(rec1['pts'])
                    len2 = polyline_length(rec2['pts'])
                    if abs(len1 - len2) > 0.2:
                        continue
                    
                    # 각 점 간의 거리 계산
                    all_distances = [calc_distance(a, b) for a in rec1['pts'] for b in rec2['pts']]
                    dmin = min(all_distances)
                    dmax = max(all_distances)
                    
                    # 점 간 거리는 3.5~7mm 사이여야 함
                    if not (3.5 <= dmin <= 7.0 and 3.5 <= dmax <= 7.0):
                        continue
                    
                    # 두 폴리라인의 점들이 0.2mm 범위에서 같은 위치에 있으면 PASS
                    if any(calc_distance(p1, p2) <= 0.2 for p1 in rec1['pts'] for p2 in rec2['pts']):
                        continue
                    
                    pts1, pts2 = rec1['pts'], rec2['pts']
                    center_sl1 = midpoint([midpoint(pts1), midpoint(pts2)])
                    
                    # CP 원 그리기
                    cp_circle = msp.add_circle(center=center_sl1, radius=HALF_SL1, dxfattribs={'color': CYAN})
                    created_circles.append(cp_circle)
                    
                    # 파이프 방향 계산 및 직교선 생성
                    pipe_angle = get_pipe_angle(pts1, pts2)
                    
                    # 직교선과 각도 함께 받기
                    orthogonal_lines, line_angles = create_iso_orthogonal_lines(center_sl1, pipe_angle, LINE_LENGTH, msp)
                    
                    # NODENO 원 위치 결정 (4개의 직교선 방향 중 최적 선택)
                    nodeno_pos, node_angle = find_best_orthogonal_position(
                        center_sl1, NODENO_OFFSET_Y, pipe_angle, msp, [cp_circle], line_angles
                    )
                    
                    # NODENO 원 그리기
                    nodeno_circle = msp.add_circle(
                        center=nodeno_pos, 
                        radius=NODENO_RADIUS, 
                        dxfattribs={'color': MAGENTA, 'layer': 'NODE'}
                    )
                    
                    # CP와 NODENO 중심을 잇는 선 (NODE 원에서 trim)
                    dx = nodeno_pos[0] - center_sl1[0]
                    dy = nodeno_pos[1] - center_sl1[1]
                    distance = math.hypot(dx, dy)
                    
                    if distance > 0:
                        ux = dx / distance
                        uy = dy / distance
                        trim_end_x = nodeno_pos[0] - ux * NODENO_RADIUS
                        trim_end_y = nodeno_pos[1] - uy * NODENO_RADIUS
                        
                        msp.add_line(
                            center_sl1, 
                            (trim_end_x, trim_end_y), 
                            dxfattribs={'color': WHITE, 'layer': 'NODE'}
                        )
                    
                    # 텍스트 추가를 위해 저장
                    texts_to_add.append(nodeno_pos)
                    
                    # 2단계 처리를 위해 해당하는 A1, A2 정보 찾기
                    matching_info = None
                    for info in a1_a2_info:
                        if (info['s1']['ent'] == rec1['ent'] and info['s2']['ent'] == rec2['ent']) or \
                           (info['s1']['ent'] == rec2['ent'] and info['s2']['ent'] == rec1['ent']):
                            matching_info = info
                            break
                    
                    # 2단계 처리
                    if matching_info:
                        ct_entity = matching_info.get('ct')  # CT 엔티티 가져오기
                        process_type2_support(
                            msp, matching_info['a1'], matching_info['a2'], ct_entity,
                            center_sl1, orthogonal_lines, line_angles, 
                            pipe_angle, node_angle
                        )
                    
                    msp.delete_entity(rec1['ent'])
                    msp.delete_entity(rec2['ent'])
                    supptag.append({'s1': rec1['ent'], 's2': rec2['ent'], 'center': center_sl1})
                    break

            # ===== ELBO와 TEE TEXT 처리 =====
            print("\n🔧 ELBO 및 TEE TEXT 특수 노드 처리 시작...")
            special_nodes_count = process_special_nodes(msp, doc)
            print(f"✅ 특수 노드 처리 완료: {special_nodes_count}개 노드 생성됨")
            
            # 모든 그래픽 요소 처리 후 텍스트 추가
            print("\n📝 텍스트 추가 시작...")
            text_count = 0
            for text_pos in texts_to_add:
                result = add_text_to_node(msp, text_pos, TEXT_VALUE, TEXT_HEIGHT, YELLOW, 'NODE', doc)
                if result:
                    text_count += 1
                else:
                    print(f"      ⚠️ 텍스트 추가 실패: 위치 ({text_pos[0]:.2f}, {text_pos[1]:.2f})")
            print(f"✅ {text_count}/{len(texts_to_add)}개 텍스트 추가 완료")
            
            # 모든 작업 완료 후 AD1, AD2, AD3, CT 삭제
            print("\n🗑️ 엔티티 삭제 시작...")
            deleted_count = 0
            for ent in entities_to_delete:
                try:
                    msp.delete_entity(ent)
                    deleted_count += 1
                except:
                    pass
            
            for ent in ct_entities_to_delete:
                try:
                    msp.delete_entity(ent)
                    deleted_count += 1
                except:
                    pass
            
            print(f"✅ {deleted_count}개 엔티티 삭제 완료")

            out_path = os.path.splitext(filepath)[0] + '_SUPP.dxf'
            doc.saveas(out_path)
            print(f"✅ 저장됨: {out_path}")

        except Exception as e:
            print(f"❌ 오류 발생 @ {filepath}")
            traceback.print_exc(file=sys.stdout)

    print("🎉 전체 작업 완료")

if __name__ == '__main__':
    main()