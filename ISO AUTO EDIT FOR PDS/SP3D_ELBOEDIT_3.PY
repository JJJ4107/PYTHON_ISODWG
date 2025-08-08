import ezdxf
import math
import tkinter as tk
from tkinter import filedialog
import os

def distance(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

def calculate_radius(p1, p2, bulge):
    if bulge == 0:
        return None
    chord = distance(p1, p2)
    sagitta = (bulge * chord) / 2
    try:
        return (chord ** 2) / (8 * abs(sagitta)) + (sagitta / 2)
    except ZeroDivisionError:
        return None

def extract_polyline_points(e):
    if e.dxftype() == 'LWPOLYLINE':
        return list(e.get_points())
    elif e.dxftype() == 'POLYLINE':
        pts = []
        for v in e.vertices:
            x = v.dxf.location.x
            y = v.dxf.location.y
            bulge = v.dxf.bulge if hasattr(v.dxf, 'bulge') else 0
            pts.append((x, y, 0, 0, bulge))
        return pts
    return []

def is_elbo_arc(e):
    """ELBO 레이어의 호(ARC) 엔티티인지 확인"""
    if e.dxftype() != 'ARC':
        return False
    if not hasattr(e.dxf, 'layer'):
        return False
    return 'ELBO' in e.dxf.layer.upper()

def get_arc_endpoints(arc):
    """호(ARC)의 시작점과 끝점 좌표 반환"""
    # 호의 중심점
    center = (arc.dxf.center[0], arc.dxf.center[1])
    radius = arc.dxf.radius
    
    # 시작각과 끝각 (라디안으로 변환)
    start_angle = math.radians(arc.dxf.start_angle)
    end_angle = math.radians(arc.dxf.end_angle)
    
    # 시작점과 끝점 계산
    start_point = (
        center[0] + radius * math.cos(start_angle),
        center[1] + radius * math.sin(start_angle)
    )
    end_point = (
        center[0] + radius * math.cos(end_angle),
        center[1] + radius * math.sin(end_angle)
    )
    
    return start_point, end_point

def line_intersection(p1, p2, p3, p4):
    x1, y1 = p1
    x2, y2 = p2
    x3, y3 = p3
    x4, y4 = p4
    denom = (x1 - x2)*(y3 - y4) - (y1 - y2)*(x3 - x4)
    if denom == 0:
        return None
    px = ((x1*y2 - y1*x2)*(x3 - x4) - (x1 - x2)*(x3*y4 - y3*x4)) / denom
    py = ((x1*y2 - y1*x2)*(y3 - y4) - (y1 - y2)*(x3*y4 - y3*x4)) / denom
    return (px, py)

def set_poly_points(e, points):
    if e.dxftype() == "LWPOLYLINE":
        e.set_points(points)
    elif e.dxftype() == "POLYLINE":
        for v in list(e.vertices):
            e.vertices.remove(v)
        for pt in points:
            e.append_vertex((pt[0], pt[1], 0))

def print_elbo_arc_info(arc):
    """ELBO 호 정보 출력"""
    start_pt, end_pt = get_arc_endpoints(arc)
    print("="*40)
    print("ELBO ARC Detected!")
    print(f" - Layer      : {arc.dxf.layer}")
    print(f" - Center     : ({arc.dxf.center[0]:.4f}, {arc.dxf.center[1]:.4f})")
    print(f" - Radius     : {arc.dxf.radius:.4f}")
    print(f" - Start Angle: {arc.dxf.start_angle:.2f}°")
    print(f" - End Angle  : {arc.dxf.end_angle:.2f}°")
    print(f" - Start Point: ({start_pt[0]:.4f}, {start_pt[1]:.4f})")
    print(f" - End Point  : ({end_pt[0]:.4f}, {end_pt[1]:.4f})")
    print("="*40)

def extract_line_points(e):
    # LINE 타입에서 (start, end) 반환
    return [(e.dxf.start[0], e.dxf.start[1]), (e.dxf.end[0], e.dxf.end[1])]

def set_line_points(e, new_start, new_end):
    e.dxf.start = new_start
    e.dxf.end = new_end

def process_file(filepath):
    try:
        doc = ezdxf.readfile(filepath)
        msp = doc.modelspace()
        modified = False
        elbo_arcs = []

        # 1. ELBO 레이어의 호(ARC) 찾기 (GREEN)
        for e in msp:
            if is_elbo_arc(e):
                e.dxf.color = 3  # GREEN
                print_elbo_arc_info(e)
                ep1, ep2 = get_arc_endpoints(e)
                elbo_arcs.append((e, ep1, ep2))
                modified = True

        # 2. ELBO 호 양쪽에 붙은 L1, L2 찾아서 교점 연장 처리
        for elbo, ep1, ep2 in elbo_arcs:
            # ELBO의 레이어 저장
            elbo_layer = elbo.dxf.layer if hasattr(elbo.dxf, 'layer') else None
            
            l1, l2 = None, None
            l1_type, l2_type = None, None  # 'PLINE' or 'LINE'

            # 1차: POLYLINE/LWPOLYLINE
            for pl in msp:
                if pl == elbo:
                    continue
                if pl.dxftype() in ["LWPOLYLINE", "POLYLINE"]:
                    points = extract_polyline_points(pl)
                    for pt in points:
                        pt_xy = pt[:2]
                        if distance(ep1, pt_xy) <= 0.3 and l1 is None:
                            l1 = pl
                            l1_type = "PLINE"
                        elif distance(ep2, pt_xy) <= 0.3 and l2 is None:
                            l2 = pl
                            l2_type = "PLINE"
            # 2차: PIPE 또는 ELBO를 포함하는 레이어의 LINE (못 찾았을 때)
            if l1 is None or l2 is None:
                for line in msp:
                    if line.dxftype() == "LINE" and hasattr(line, 'dxf') and hasattr(line.dxf, 'layer') and ("PIPE" in line.dxf.layer or "ELBO" in line.dxf.layer):
                        start = (line.dxf.start[0], line.dxf.start[1])
                        end = (line.dxf.end[0], line.dxf.end[1])
                        if l1 is None and (distance(ep1, start) <= 0.3 or distance(ep1, end) <= 0.3):
                            l1 = line
                            l1_type = "LINE"
                        if l2 is None and (distance(ep2, start) <= 0.3 or distance(ep2, end) <= 0.3):
                            l2 = line
                            l2_type = "LINE"

            if l1 and l2 and l1 != l2:
                # 점 추출
                if l1_type == "PLINE":
                    l1_pts = extract_polyline_points(l1)
                    p1, p2 = l1_pts[0][:2], l1_pts[-1][:2]
                else:  # LINE
                    line_pts = extract_line_points(l1)
                    p1, p2 = line_pts[0], line_pts[1]

                if l2_type == "PLINE":
                    l2_pts = extract_polyline_points(l2)
                    p3, p4 = l2_pts[0][:2], l2_pts[-1][:2]
                else:
                    line_pts = extract_line_points(l2)
                    p3, p4 = line_pts[0], line_pts[1]

                inter = line_intersection(p1, p2, p3, p4)
                if inter:
                    # L1 끝점 이동
                    if l1_type == "PLINE":
                        if distance(l1_pts[0][:2], inter) < distance(l1_pts[-1][:2], inter):
                            l1_pts[0] = (inter[0], inter[1], 0, 0, 0)
                        else:
                            l1_pts[-1] = (inter[0], inter[1], 0, 0, 0)
                        set_poly_points(l1, l1_pts)
                        l1.dxf.color = 3   # GREEN
                        if elbo_layer:
                            l1.dxf.layer = elbo_layer  # ELBO 레이어로 변경
                    else:  # LINE
                        s, e = extract_line_points(l1)
                        if distance(s, inter) < distance(e, inter):
                            set_line_points(l1, inter, e)
                        else:
                            set_line_points(l1, s, inter)
                        l1.dxf.color = 3   # GREEN
                        if elbo_layer:
                            l1.dxf.layer = elbo_layer  # ELBO 레이어로 변경

                    # L2 끝점 이동
                    if l2_type == "PLINE":
                        if distance(l2_pts[0][:2], inter) < distance(l2_pts[-1][:2], inter):
                            l2_pts[0] = (inter[0], inter[1], 0, 0, 0)
                        else:
                            l2_pts[-1] = (inter[0], inter[1], 0, 0, 0)
                        set_poly_points(l2, l2_pts)
                        l2.dxf.color = 7
                        if elbo_layer:
                            l2.dxf.layer = elbo_layer  # ELBO 레이어로 변경
                    else:  # LINE
                        s, e = extract_line_points(l2)
                        if distance(s, inter) < distance(e, inter):
                            set_line_points(l2, inter, e)
                        else:
                            set_line_points(l2, s, inter)
                        l2.dxf.color = 7
                        if elbo_layer:
                            l2.dxf.layer = elbo_layer  # ELBO 레이어로 변경

                    # ELBO 호 삭제
                    msp.delete_entity(elbo)
                    modified = True

                    # 교차점에 원 3개 추가
                    for r in [0.1, 0.2, 0.3]:
                        msp.add_circle(center=inter, radius=r, dxfattribs={"color": 7})

        # 3. PIPE 또는 ELBO를 포함하는 레이어의 POLYLINE/LWPOLYLINE 처리: DP → P1,P2 연결선 그리기 → 삭제
        for pl in list(msp):
            if pl.dxftype() in ["LWPOLYLINE", "POLYLINE"] and hasattr(pl, 'dxf') and hasattr(pl.dxf, 'layer') and ("PIPE" in pl.dxf.layer or "ELBO" in pl.dxf.layer):
                pts = extract_polyline_points(pl)
                if len(pts) >= 2:
                    p1 = (pts[0][0], pts[0][1])
                    p2 = (pts[1][0], pts[1][1])
                    # 녹색선 (GREEN=3), 원본과 같은 레이어에 추가
                    msp.add_line(p1, p2, dxfattribs={'color': 3, 'layer': pl.dxf.layer})
                    # 원본 DP 삭제
                    msp.delete_entity(pl)
                    modified = True
                    layer_name = pl.dxf.layer if hasattr(pl, 'dxf') and hasattr(pl.dxf, 'layer') else "Unknown"
                    print(f"✔ PIPE/ELBO 레이어 변환: {layer_name}")

        # PIPE 또는 ELBO를 포함하는 레이어 전체 GREEN 처리
        for e in msp:
            if hasattr(e, 'dxf') and hasattr(e.dxf, 'layer') and ("PIPE" in e.dxf.layer or "ELBO" in e.dxf.layer) and e.dxftype() in ["LINE", "LWPOLYLINE", "POLYLINE"]:
                e.dxf.color = 3

        # 저장
        if modified:
            new_path = os.path.splitext(filepath)[0] + "_elbo.dxf"
            doc.saveas(new_path)
            print(f"✔ 저장 완료: {new_path}")
        else:
            print(f"⚠ 조건 일치 없음: {os.path.basename(filepath)}")

    except Exception as e:
        print(f"❌ 오류 - {filepath}: {e}")

def main():
    root = tk.Tk()
    root.withdraw()
    filepaths = filedialog.askopenfilenames(
        title="DXF 파일 선택",
        filetypes=[("DXF files", "*.dxf")]
    )
    if not filepaths:
        print("❗ DXF 파일을 선택하지 않았습니다.")
        return

    for path in filepaths:
        process_file(path)

if __name__ == "__main__":
    main()