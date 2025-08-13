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
SL1_LENGTH = 4.4
HALF_SL1 = SL1_LENGTH / 2.0

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
    
    # WELDS 레이어만 선택
    if not hasattr(ent.dxf, 'layer') or ent.dxf.layer != 'WELDS':
        return False
    
    # 수평선(기울기 0) 제외 - y좌표가 같으면 제외
    if abs(pts[0][1] - pts[1][1]) < 1e-6:  # 부동소수점 오차 고려
        return False
    
    L = polyline_length(pts)
    return 3.0 <= L <= 3.4  # S1 길이 조건 변경: 3.0~3.4mm

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
                    
                    # 점 간 거리는 3~7mm 사이여야 함
                    if not (3.0 <= dmin <= 7.0 and 3.0 <= dmax <= 7.0):
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
                    
                    # 점 간 거리는 3~7mm 사이여야 함
                    if not (3.0 <= dmin <= 7.0 and 3.0 <= dmax <= 7.0):
                        continue
                    
                    # 두 폴리라인의 점들이 0.2mm 범위에서 같은 위치에 있으면 PASS
                    if any(calc_distance(p1, p2) <= 0.2 for p1 in rec1['pts'] for p2 in rec2['pts']):
                        continue
                    pts1, pts2 = rec1['pts'], rec2['pts']
                    center_sl1 = midpoint([midpoint(pts1), midpoint(pts2)])
                    msp.add_circle(center=center_sl1, radius=HALF_SL1, dxfattribs={'color': CYAN})
                    pt1_sel = max(pts1, key=lambda p1: max(calc_distance(p1, p2) for p2 in pts2))
                    pt2_sel = max(pts2, key=lambda p2: calc_distance(pt1_sel, p2))
                    def trim_and_extend(p_start, p_end):
                        t_start = p_start if calc_distance(p_start, center_sl1) <= HALF_SL1 else point_at_distance(center_sl1, p_start, HALF_SL1)
                        t_end = p_end if calc_distance(p_end, center_sl1) <= HALF_SL1 else point_at_distance(center_sl1, p_end, HALF_SL1)
                        d = calc_distance(t_start, t_end)
                        if d == 0: return None, None
                        if d < SL1_LENGTH:
                            ux, uy = (t_end[0]-t_start[0])/d, (t_end[1]-t_start[1])/d
                            delta = (SL1_LENGTH - d)/2.0
                            t_start = (t_start[0] - ux*delta, t_start[1] - uy*delta)
                            t_end = (t_end[0] + ux*delta, t_end[1] + uy*delta)
                        return t_start, t_end
                    for start, end in [(pt1_sel, pt2_sel), (next(p for p in pts1 if p!=pt1_sel), next(p for p in pts2 if p!=pt2_sel))]:
                        ts, te = trim_and_extend(start, end)
                        if ts and te:
                            msp.add_line(ts, te, dxfattribs={'color': CYAN})
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
            
            # 모든 원(반지름 2.2mm) 찾기
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