import ezdxf
import math
import os
import traceback
import sys

CYAN = 4
RED = 1
YELLOW = 2
SL1_LENGTH = 4.4
CIRCLE_RADIUS = 1.75  # 지름 3.5mm의 반지름
HALF_SL1 = CIRCLE_RADIUS  # 기존 HALF_SL1을 CIRCLE_RADIUS로 대체

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

def calc_slope(p1, p2):
    """두 점 사이의 기울기를 계산 (수직선의 경우 float('inf') 반환)"""
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    if abs(dx) < 1e-9:  # 수직선
        return float('inf') if dy > 0 else float('-inf')
    return dy / dx

def are_collinear(p1, p2, p3, p4, tolerance=0.1):
    """네 점이 일직선상에 있는지 확인"""
    # 벡터 외적을 이용한 방법
    # p1-p2 선분과 p3-p4 선분이 같은 직선상에 있는지 확인
    
    # p1에서 p3로 가는 벡터와 p1에서 p2로 가는 벡터의 외적
    v1 = (p2[0] - p1[0], p2[1] - p1[1])
    v2 = (p3[0] - p1[0], p3[1] - p1[1])
    cross1 = abs(v1[0] * v2[1] - v1[1] * v2[0])
    
    # p1에서 p4로 가는 벡터와 p1에서 p2로 가는 벡터의 외적
    v3 = (p4[0] - p1[0], p4[1] - p1[1])
    cross2 = abs(v1[0] * v3[1] - v1[1] * v3[0])
    
    # 두 외적이 모두 0에 가까우면 일직선상에 있음
    return cross1 < tolerance and cross2 < tolerance

def slopes_equal(slope1, slope2, tolerance=0.01):
    """두 기울기가 같은지 확인"""
    if slope1 == float('inf') or slope1 == float('-inf'):
        return slope2 == float('inf') or slope2 == float('-inf')
    if slope2 == float('inf') or slope2 == float('-inf'):
        return False
    return abs(slope1 - slope2) < tolerance

def is_valid_s1(ent):
    if has_curve(ent): return False
    pts = extract_points(ent)
    if len(pts) != 2: return False
    
    # WELDS 또는 NOZZLES 레이어만 선택
    if not hasattr(ent.dxf, 'layer') or ent.dxf.layer not in ['WELDS', 'NOZZLES']:
        return False
    
    # 수평선(기울기 0) 제외 - y좌표가 같으면 제외
    if abs(pts[0][1] - pts[1][1]) < 1e-6:  # 부동소수점 오차 고려
        return False
    
    L = polyline_length(pts)
    return 2.8 <= L <= 4.0  # S1 길이 조건 변경: 3.0~4.0mm

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

def process_file(filepath):
    try:
        doc = ezdxf.readfile(filepath)
        msp = doc.modelspace()

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
                
                # 두 선분의 기울기가 동일해야 함
                slope1 = calc_slope(rec1['pts'][0], rec1['pts'][1])
                slope2 = calc_slope(rec2['pts'][0], rec2['pts'][1])
                if not slopes_equal(slope1, slope2):
                    continue
                
                # 서로 일직선상에 있는 것은 제외
                if are_collinear(rec1['pts'][0], rec1['pts'][1], 
                               rec2['pts'][0], rec2['pts'][1]):
                    continue
                
                # 각 점 간의 거리 계산
                all_distances = [calc_distance(a, b) for a in rec1['pts'] for b in rec2['pts']]
                dmin = min(all_distances)
                dmax = max(all_distances)
                
                # 점 간 거리는 3~7mm 사이여야 함
                if not (3.0 <= dmin <= 7.0 and 3.0 <= dmax <= 7.0):
                    continue
                
                # 두 폴리라인의 점들이 0.2mm 범위에서 같은 위치에 있으면 PASS (평행해야 하고 만나면 안됨)
                if any(calc_distance(p1, p2) <= 0.2 for p1 in rec1['pts'] for p2 in rec2['pts']):
                    continue

                sp1, ep1 = rec1['pts']
                sp2, ep2 = rec2['pts']

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
                line = msp.add_line(center1, ps_point, dxfattribs={'color': CYAN, 'layer': 'SUPP'})
                croschk.append({'s1': rec1['ent'], 's2': rec2['ent'], 'line': line, 'ps': ps_point})
                
                # 전체 작업이 성공한 경우에만 A1, A2 삭제
                # A1 삭제 시 ARROW 레이어의 1mm 이하 LINE도 함께 삭제
                arrow_lines = find_arrow_lines(msp, A1['pts'])
                for arrow_line in arrow_lines:
                    msp.delete_entity(arrow_line)
                
                msp.delete_entity(A1['ent'])
                msp.delete_entity(A2['ent'])
                break

        supptag = []
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
                
                # 두 선분의 기울기가 동일해야 함
                slope1 = calc_slope(rec1['pts'][0], rec1['pts'][1])
                slope2 = calc_slope(rec2['pts'][0], rec2['pts'][1])
                if not slopes_equal(slope1, slope2):
                    continue
                
                # 서로 일직선상에 있는 것은 제외
                if are_collinear(rec1['pts'][0], rec1['pts'][1], 
                               rec2['pts'][0], rec2['pts'][1]):
                    continue
                
                # 각 점 간의 거리 계산
                all_distances = [calc_distance(a, b) for a in rec1['pts'] for b in rec2['pts']]
                dmin = min(all_distances)
                dmax = max(all_distances)
                
                # 점 간 거리는 3~7mm 사이여야 함
                if not (3.0 <= dmin <= 7.0 and 3.0 <= dmax <= 7.0):
                    continue
                
                # 두 폴리라인의 점들이 0.2mm 범위에서 같은 위치에 있으면 PASS
                if any(calc_distance(p1, p2) <= 0.2 for p1 in rec1['pts'] for p2 in rec2['pts']):
                    continue
                pts1, pts2 = rec1['pts'], rec2['pts']
                center_sl1 = midpoint([midpoint(pts1), midpoint(pts2)])
                # 원을 SUPP 레이어에 그리기
                msp.add_circle(center=center_sl1, radius=CIRCLE_RADIUS, dxfattribs={'color': CYAN, 'layer': 'SUPP'})
                pt1_sel = max(pts1, key=lambda p1: max(calc_distance(p1, p2) for p2 in pts2))
                pt2_sel = max(pts2, key=lambda p2: calc_distance(pt1_sel, p2))
                def trim_and_extend(p_start, p_end):
                    # 원의 경계에 맞게 trim하고 길이를 3.5mm로 조정
                    # 먼저 두 점을 원 내부로 제한
                    t_start = p_start if calc_distance(p_start, center_sl1) <= CIRCLE_RADIUS else point_at_distance(center_sl1, p_start, CIRCLE_RADIUS)
                    t_end = p_end if calc_distance(p_end, center_sl1) <= CIRCLE_RADIUS else point_at_distance(center_sl1, p_end, CIRCLE_RADIUS)
                    
                    # 선의 방향 벡터 계산
                    dx = t_end[0] - t_start[0]
                    dy = t_end[1] - t_start[1]
                    current_length = math.hypot(dx, dy)
                    
                    if current_length == 0: 
                        return None, None
                    
                    # 단위 벡터
                    ux, uy = dx / current_length, dy / current_length
                    
                    # 선의 중점을 중심으로 3.5mm 길이로 조정
                    mid_x = (t_start[0] + t_end[0]) / 2.0
                    mid_y = (t_start[1] + t_end[1]) / 2.0
                    half_length = 1.75  # 3.5mm의 절반
                    
                    new_start = (mid_x - ux * half_length, mid_y - uy * half_length)
                    new_end = (mid_x + ux * half_length, mid_y + uy * half_length)
                    
                    # 새로운 점들이 원 내부에 있는지 확인
                    if calc_distance(new_start, center_sl1) <= CIRCLE_RADIUS and calc_distance(new_end, center_sl1) <= CIRCLE_RADIUS:
                        return new_start, new_end
                    else:
                        # 원을 벗어나는 경우 원의 경계에 맞춰 다시 조정
                        return t_start, t_end
                for start, end in [(pt1_sel, pt2_sel), (next(p for p in pts1 if p!=pt1_sel), next(p for p in pts2 if p!=pt2_sel))]:
                    ts, te = trim_and_extend(start, end)
                    if ts and te:
                        # 선을 SUPP 레이어에 그리기
                        msp.add_line(ts, te, dxfattribs={'color': CYAN, 'layer': 'SUPP'})
                msp.delete_entity(rec1['ent']); msp.delete_entity(rec2['ent'])
                supptag.append({'s1': rec1['ent'], 's2': rec2['ent'], 'center': center_sl1})
                break

        for rec in croschk:
            match = next((x for x in supptag if x['s1']==rec['s1'] and x['s2']==rec['s2']), None)
            if not match: continue
            ln = rec['line']
            # PS 점에서 원의 중심 방향으로 원의 경계까지만 연결
            ps_to_center_dist = calc_distance(rec['ps'], match['center'])
            if ps_to_center_dist > CIRCLE_RADIUS:
                # 원의 경계에서 멈추도록 조정
                boundary_point = point_at_distance(rec['ps'], match['center'], ps_to_center_dist - CIRCLE_RADIUS)
                ln.dxf.start = rec['ps']
                ln.dxf.end = (*boundary_point, 0)
            else:
                # PS가 원 내부에 있는 경우 그대로 연결
                ln.dxf.start = rec['ps']
                ln.dxf.end = (*match['center'], 0)
            msp.delete_entity(rec['s1']); msp.delete_entity(rec['s2'])

        # ===== 추가된 코드: PS-원 중심 연결선 재확인 및 조정 =====
        # 모든 원(반지름 1.75mm) 찾기
        circles = []
        for e in msp:
            if e.dxftype() == 'CIRCLE' and abs(e.dxf.radius - CIRCLE_RADIUS) < 0.01 and e.dxf.layer == 'SUPP':
                circles.append({'ent': e, 'center': (e.dxf.center.x, e.dxf.center.y)})
        
        # 모든 7점 폴리라인(PS) 찾기
        ps_entities = []
        for e in msp:
            pts = extract_points(e)
            if is_ps_candidate(pts):
                ps_entities.append({'ent': e, 'pts': pts})
        
        # 모든 SUPP 레이어의 CYAN 색상 LINE 검사
        adjustment_count = 0
        for e in msp:
            if e.dxftype() == 'LINE' and hasattr(e.dxf, 'layer') and e.dxf.layer == 'SUPP' and hasattr(e.dxf, 'color') and e.dxf.color == CYAN:
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
                    
                    # 원에 가까운 끝점을 원의 경계로 조정 (원의 중심이 아닌 원의 경계)
                    if closest_circle and min_dist < 5.0:  # 5mm 이내에 원이 있으면
                        if is_start_closer:
                            old_point = line_start
                            # PS에서 원의 중심 방향으로 원의 경계까지만 연결
                            if calc_distance(line_end, closest_circle['center']) > CIRCLE_RADIUS:
                                new_start = point_at_distance(line_end, closest_circle['center'], 
                                                            calc_distance(line_end, closest_circle['center']) - CIRCLE_RADIUS)
                                e.dxf.start = (*new_start, 0)
                            else:
                                e.dxf.start = (*closest_circle['center'], 0)
                        else:
                            old_point = line_end
                            # PS에서 원의 중심 방향으로 원의 경계까지만 연결
                            if calc_distance(line_start, closest_circle['center']) > CIRCLE_RADIUS:
                                new_end = point_at_distance(line_start, closest_circle['center'], 
                                                          calc_distance(line_start, closest_circle['center']) - CIRCLE_RADIUS)
                                e.dxf.end = (*new_end, 0)
                            else:
                                e.dxf.end = (*closest_circle['center'], 0)
                        
                        adjustment_count += 1
        # ===== 추가 코드 끝 =====

        out_path = os.path.splitext(filepath)[0] + '_SUPP.dxf'
        doc.saveas(out_path)

    except Exception as e:
        pass

if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(1)
    
    # 첫 번째 인자는 스크립트 이름이므로 제외
    input_files = sys.argv[1:]
    
    for input_file in input_files:
        if not input_file.lower().endswith('.dxf'):
            continue
            
        process_file(input_file)