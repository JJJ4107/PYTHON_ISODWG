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
SL1_LENGTH = 4.4
HALF_SL1 = 0.7  # 원의 반지름을 0.7mm로 변경
LINE_LENGTH = 3.5  # 선의 길이 3.5mm
LINE_WIDTH = 0.6  # 선 두께 0.6
NODENO_RADIUS = 2.9  # NODENO 원의 반지름 (지름 5.8mm)
NODENO_OFFSET_Y = 7.3  # Y방향 이동 거리
ROTATION_ANGLE = 30  # 회전 각도 (도)
TEXT_HEIGHT = 2.0  # 텍스트 높이

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
    return 3.4 <= L <= 3.6  # S1 길이 조건 변경: 3.4~3.6

def is_ps_candidate(pts):
    return len(pts) == 7 and any(calc_distance(pts[i], pts[i+1]) >= 3.0 for i in range(6))

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
    
    # 평균 방향 계산
    avg_dir = ((dir1[0] + dir2[0])/2, (dir1[1] + dir2[1])/2)
    
    # 각도 계산 (라디안)
    angle = math.atan2(avg_dir[1], avg_dir[0])
    
    return angle

def create_iso_orthogonal_lines(center, pipe_angle, length, msp):
    """ISO 도면 기준으로 파이프에 직교하는 4개 방향으로 선을 생성"""
    lines = []
    
    # 파이프 각도를 도 단위로 변환
    pipe_angle_deg = math.degrees(pipe_angle) % 360
    
    # ISO 도면의 표준 각도들 (30도 간격)
    # 파이프 방향별로 직교하는 ISO 표준 각도 선택
    
    if abs(pipe_angle_deg - 90) < 5 or abs(pipe_angle_deg - 270) < 5:
        # 수직 파이프 (90도): 직교는 수평 방향들
        # ISO 수평: 30도, 150도와 그 반대
        angles = [30, 210, 150, 330]  # 30+180=210, 150+180=330
        
    elif abs(pipe_angle_deg - 30) < 5 or abs(pipe_angle_deg - 210) < 5:
        # 30도 파이프: 직교는 120도, 300도
        angles = [120, 300]  # 이미 서로 180도 차이
        # ISO 도면에서는 보통 90도(수직)도 포함
        angles.extend([90, 270])
        
    elif abs(pipe_angle_deg - 150) < 5 or abs(pipe_angle_deg - 330) < 5:
        # 150도 파이프: 직교는 60도, 240도
        angles = [60, 240]  # 이미 서로 180도 차이
        # ISO 도면에서는 보통 90도(수직)도 포함
        angles.extend([90, 270])
        
    elif abs(pipe_angle_deg - 0) < 5 or abs(pipe_angle_deg - 180) < 5:
        # 수평 파이프 (0도/180도): 직교는 90도, 270도
        angles = [90, 270]
        # ISO 각도 추가
        angles.extend([60, 240])  # 또는 [120, 300]
        
    else:
        # 기타 각도: 가장 가까운 ISO 표준 각도로 맞춤
        # 직교 각도 계산 후 가장 가까운 30도 배수로 반올림
        orth1 = pipe_angle_deg + 90
        orth2 = pipe_angle_deg - 90
        
        # 30도 단위로 반올림
        orth1_iso = round(orth1 / 30) * 30
        orth2_iso = round(orth2 / 30) * 30
        
        angles = [orth1_iso % 360, (orth1_iso + 180) % 360,
                  orth2_iso % 360, (orth2_iso + 180) % 360]
    
    # 중복 제거
    unique_angles = list(dict.fromkeys(angles))
    
    # 각 방향으로 3.5mm 선 그리기 (최대 4개)
    for angle_deg in unique_angles[:4]:
        angle_rad = math.radians(angle_deg)
        end_point = (center[0] + length * math.cos(angle_rad),
                     center[1] + length * math.sin(angle_rad))
        
        line = msp.add_line(center, end_point, 
                          dxfattribs={'color': BLUE, 'lineweight': 60})
        lines.append(line)
    
    return lines

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

def check_circle_interference(circle_center, radius, msp, exclude_entities=[]):
    """원과 다른 엔티티들 간의 간섭 체크"""
    for ent in msp:
        if ent in exclude_entities:
            continue
            
        ent_type = ent.dxftype()
        if ent_type in ['LINE', 'LWPOLYLINE', 'POLYLINE']:
            pts = extract_points(ent)
            if len(pts) >= 2:
                # 각 선분과 원의 간섭 체크
                for i in range(len(pts) - 1):
                    p1, p2 = pts[i], pts[i+1]
                    # 선분과 원의 최단 거리 계산
                    dist = point_to_line_distance(circle_center, p1, p2)
                    if dist < radius:
                        return True
    return False

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

def find_non_interfering_position(cp, initial_offset_y, rotation_step, radius, msp, exclude_entities):
    """간섭이 없는 위치를 찾기"""
    # 초기 위치
    initial_pos = (cp[0], cp[1] + initial_offset_y)
    
    # 0도부터 360도까지 rotation_step 간격으로 체크
    for angle in range(0, 360, rotation_step):
        test_pos = rotate_point(initial_pos, cp, angle)
        
        if not check_circle_interference(test_pos, radius, msp, exclude_entities):
            return test_pos
    
    # 간섭이 없는 위치를 찾지 못한 경우 초기 위치 반환
    return initial_pos

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
            
            # NODE 레이어가 없으면 생성
            if 'NODE' not in doc.layers:
                doc.layers.new('NODE')

            s1_list = []
            for e in msp:
                if is_valid_s1(e):
                    pts = extract_points(e)
                    if pts and len(pts) == 2:
                        s1_list.append({'ent': e, 'pts': pts})

            croschk = []
            for rec1 in s1_list:
                for rec2 in s1_list:
                    if rec1 is rec2:
                        continue
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
                    
                    # 두 폴리라인의 점들이 0.2mm 범위에서 같은 위치에 있으면 PASS (평행해야 하고 만나면 안됨)
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
                    center1 = midpoint(rec1['pts'])

                    A1 = next(({'ent':e,'pts':extract_points(e)} for e in msp if len(extract_points(e))==3 and any(calc_distance(p,center1)<=1 for p in extract_points(e))), None)
                    if not A1: continue
                    mid_p2 = A1['pts'][1]
                    A2 = next(({'ent':e,'pts':extract_points(e)} for e in msp if e is not A1['ent'] and len(extract_points(e)) in (2,3) and any(calc_distance(p,mid_p2)<=0.3 for p in extract_points(e))), None)
                    if not A2:
                        # A2를 찾지 못한 경우 - 아무것도 삭제하지 않음
                        continue
                    A2['ent'].dxf.color = RED
                    farpt = max(A2['pts'], key=lambda p: calc_distance(p, center1))
                    PS = next(({'ent':e,'pts':extract_points(e)} for e in msp if is_ps_candidate(extract_points(e)) and any(calc_distance(p,farpt)<=7 for p in extract_points(e))), None)
                    if not PS:
                        # PS를 찾지 못한 경우 - 아무것도 삭제하지 않음
                        continue
                    PS['ent'].dxf.color = CYAN
                    ps_point = min(PS['pts'], key=lambda p: calc_distance(p, center1))
                    line = msp.add_line(center1, ps_point, dxfattribs={'color': CYAN})
                    croschk.append({'s1': rec1['ent'], 's2': rec2['ent'], 'line': line, 'ps': ps_point})
                    
                    # 전체 작업이 성공한 경우에만 A1, A2 삭제
                    # A1 삭제 시 ARROW 레이어의 1mm 이하 LINE도 함께 삭제
                    arrow_lines = find_arrow_lines(msp, A1['pts'])
                    for arrow_line in arrow_lines:
                        msp.delete_entity(arrow_line)
                        print(f"  ARROW 레이어 LINE 삭제됨 (길이: {polyline_length(extract_points(arrow_line)):.3f}mm)")
                    
                    msp.delete_entity(A1['ent'])
                    msp.delete_entity(A2['ent'])
                    break

            supptag = []
            created_circles = []  # 생성된 원들을 추적
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
                    orthogonal_lines = create_iso_orthogonal_lines(center_sl1, pipe_angle, LINE_LENGTH, msp)
                    
                    # NODENO 원 위치 결정
                    nodeno_pos = find_non_interfering_position(
                        center_sl1, NODENO_OFFSET_Y, ROTATION_ANGLE, 
                        NODENO_RADIUS, msp, [cp_circle] + orthogonal_lines
                    )
                    
                    # NODENO 원 그리기
                    nodeno_circle = msp.add_circle(
                        center=nodeno_pos, 
                        radius=NODENO_RADIUS, 
                        dxfattribs={'color': MAGENTA, 'layer': 'NODE'}
                    )
                    
                    # 텍스트 '0' 추가
                    text = msp.add_text(
                        '0',
                        dxfattribs={
                            'height': TEXT_HEIGHT,
                            'color': YELLOW,
                            'layer': 'NODE',
                            'insert': nodeno_pos,
                            'halign': 4,  # CENTER
                            'valign': 2   # MIDDLE
                        }
                    )
                    
                    # CP와 NODENO 중심을 잇는 선
                    msp.add_line(
                        center_sl1, 
                        nodeno_pos, 
                        dxfattribs={'color': WHITE, 'layer': 'NODE'}
                    )
                    
                    msp.delete_entity(rec1['ent']); msp.delete_entity(rec2['ent'])
                    supptag.append({'s1': rec1['ent'], 's2': rec2['ent'], 'center': center_sl1})
                    break

            for rec in croschk:
                match = next((x for x in supptag if x['s1']==rec['s1'] and x['s2']==rec['s2']), None)
                if not match: continue
                ln = rec['line']
                ln.dxf.start = rec['ps']
                ln.dxf.end = (*match['center'], 0)
                msp.delete_entity(rec['s1']); msp.delete_entity(rec['s2'])

            # ===== 추가된 코드: PS-원 중심 연결선 재확인 및 조정 =====
            print("\n📐 PS-원 중심 연결선 재확인 시작...")
            
            # 모든 원(반지름 0.7mm) 찾기
            circles = []
            for e in msp:
                if e.dxftype() == 'CIRCLE' and abs(e.dxf.radius - HALF_SL1) < 0.01:
                    circles.append({'ent': e, 'center': (e.dxf.center.x, e.dxf.center.y)})
            
            # 모든 7점 폴리라인(PS) 찾기
            ps_entities = []
            for e in msp:
                pts = extract_points(e)
                if is_ps_candidate(pts):
                    ps_entities.append({'ent': e, 'pts': pts})
            
            # 모든 CYAN 색상의 LINE 검사
            adjustment_count = 0
            for e in msp:
                if e.dxftype() == 'LINE' and hasattr(e.dxf, 'color') and e.dxf.color == CYAN:
                    line_start = (e.dxf.start.x, e.dxf.start.y)
                    line_end = (e.dxf.end.x, e.dxf.end.y)
                    
                    # 이 선이 PS와 연결되어 있는지 확인
                    connected_to_ps = False
                    for ps in ps_entities:
                        for pt in ps['pts']:
                            if calc_distance(line_start, pt) < 0.1 or calc_distance(line_end, pt) < 0.1:
                                connected_to_ps = True
                                break
                        if connected_to_ps:
                            break
                    
                    if connected_to_ps:
                        # 가장 가까운 원 찾기
                        closest_circle = None
                        min_dist = float('inf')
                        
                        for circle in circles:
                            dist_start = calc_distance(line_start, circle['center'])
                            dist_end = calc_distance(line_end, circle['center'])
                            
                            if dist_start < min_dist:
                                min_dist = dist_start
                                closest_circle = circle
                                is_start_closer = True
                            if dist_end < min_dist:
                                min_dist = dist_end
                                closest_circle = circle
                                is_start_closer = False
                        
                        # 원에 가까운 끝점을 원의 중심으로 조정
                        if closest_circle and min_dist < 5.0:  # 5mm 이내에 원이 있으면
                            if is_start_closer:
                                old_point = line_start
                                e.dxf.start = (*closest_circle['center'], 0)
                            else:
                                old_point = line_end
                                e.dxf.end = (*closest_circle['center'], 0)
                            
                            adjustment_count += 1
                            print(f"  선 조정 #{adjustment_count}: "
                                  f"({old_point[0]:.3f}, {old_point[1]:.3f}) → "
                                  f"({closest_circle['center'][0]:.3f}, {closest_circle['center'][1]:.3f})")
            
            print(f"✅ PS-원 중심 연결선 재조정 완료: {adjustment_count}개 선 조정됨")
            # ===== 추가 코드 끝 =====

            out_path = os.path.splitext(filepath)[0] + '_SUPP.dxf'
            doc.saveas(out_path)
            print(f"✅ 저장됨: {out_path}")

        except Exception as e:
            print(f"❌ 오류 발생 @ {filepath}")
            traceback.print_exc(file=sys.stdout)

    print("🎉 전체 작업 완료")

if __name__ == '__main__':
    main()