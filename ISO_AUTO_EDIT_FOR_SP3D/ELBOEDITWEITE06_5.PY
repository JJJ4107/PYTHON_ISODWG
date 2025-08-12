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

def is_elbo(e):
    pts = extract_polyline_points(e)
    if len(pts) != 2:
        return False
    bulge = pts[0][4] if len(pts[0]) > 4 else 0
    if bulge == 0:
        return False
    p1 = (pts[0][0], pts[0][1])
    p2 = (pts[1][0], pts[1][1])
    radius = calculate_radius(p1, p2, bulge)
    return radius is not None and 0.5 <= radius <= 20

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

def print_elbo_info(e):
    pts = extract_polyline_points(e)
    p1 = (pts[0][0], pts[0][1])
    p2 = (pts[1][0], pts[1][1])
    bulge = pts[0][4] if len(pts[0]) > 4 else 0
    radius = calculate_radius(p1, p2, bulge)
    print("="*40)
    print("ELBO Detected!")
    print(f" - Start Point: {p1}")
    print(f" - End Point  : {p2}")
    print(f" - Bulge      : {bulge}")
    print(f" - Radius     : {radius:.4f}" if radius else " - Radius     : None")
    print("="*40)

def extract_line_points(e):
    # LINE 타입에서 (start, end) 반환
    return [(e.dxf.start[0], e.dxf.start[1]), (e.dxf.end[0], e.dxf.end[1])]

def set_line_points(e, new_start, new_end):
    e.dxf.start = new_start
    e.dxf.end = new_end

def find_pipe_text_entities(msp):
    """PIPE TEXT를 포함하는 TEXT 엔티티들을 찾아 반환"""
    pipe_text_entities = []
    for e in msp:
        if e.dxftype() in ["TEXT", "MTEXT"]:
            text_content = e.dxf.text if hasattr(e.dxf, 'text') else ""
            if "PIPE TEXT" in text_content.upper():
                pipe_text_entities.append(e)
                print(f"Found PIPE TEXT: '{text_content}' at {e.dxf.insert}")
    return pipe_text_entities

def find_nearby_entities(msp, text_entity, search_radius=10.0):
    """TEXT 엔티티 근처의 LINE, POLYLINE을 찾아 반환"""
    nearby_entities = []
    text_pos = (text_entity.dxf.insert[0], text_entity.dxf.insert[1])
    
    for e in msp:
        if e.dxftype() in ["LINE", "LWPOLYLINE", "POLYLINE"]:
            # LINE의 경우
            if e.dxftype() == "LINE":
                start = (e.dxf.start[0], e.dxf.start[1])
                end = (e.dxf.end[0], e.dxf.end[1])
                if distance(text_pos, start) <= search_radius or distance(text_pos, end) <= search_radius:
                    nearby_entities.append(e)
            # POLYLINE의 경우
            else:
                pts = extract_polyline_points(e)
                for pt in pts:
                    if distance(text_pos, pt[:2]) <= search_radius:
                        nearby_entities.append(e)
                        break
    
    return nearby_entities

def process_file(filepath):
    try:
        doc = ezdxf.readfile(filepath)
        msp = doc.modelspace()
        modified = False
        elbos = []
        
        # PIPE TEXT 엔티티들 찾기
        pipe_text_entities = find_pipe_text_entities(msp)
        print(f"Found {len(pipe_text_entities)} PIPE TEXT entities")
        
        # PIPE TEXT 근처의 엔티티들을 저장
        pipe_related_entities = set()
        for text_entity in pipe_text_entities:
            nearby = find_nearby_entities(msp, text_entity)
            pipe_related_entities.update(nearby)

        # 1. ELBO 찾기 (GREEN)
        for e in msp:
            if is_elbo(e):
                e.dxf.color = 3  # GREEN
                print_elbo_info(e)
                pts = extract_polyline_points(e)
                ep1 = (pts[0][0], pts[0][1])
                ep2 = (pts[1][0], pts[1][1])
                elbos.append((e, ep1, ep2))
                modified = True

        # 2. ELBO 양쪽에 붙은 L1, L2 찾아서 교점 연장 처리
        for elbo, ep1, ep2 in elbos:
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
            
            # 2차: PIPE TEXT 근처의 LINE (못 찾았을 때)
            if l1 is None or l2 is None:
                for line in pipe_related_entities:
                    if line.dxftype() == "LINE":
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
                    else:  # LINE
                        s, e = extract_line_points(l1)
                        if distance(s, inter) < distance(e, inter):
                            set_line_points(l1, inter, e)
                        else:
                            set_line_points(l1, s, inter)
                        l1.dxf.color = 3   # GREEN

                    # L2 끝점 이동
                    if l2_type == "PLINE":
                        if distance(l2_pts[0][:2], inter) < distance(l2_pts[-1][:2], inter):
                            l2_pts[0] = (inter[0], inter[1], 0, 0, 0)
                        else:
                            l2_pts[-1] = (inter[0], inter[1], 0, 0, 0)
                        set_poly_points(l2, l2_pts)
                        l2.dxf.color = 7
                    else:  # LINE
                        s, e = extract_line_points(l2)
                        if distance(s, inter) < distance(e, inter):
                            set_line_points(l2, inter, e)
                        else:
                            set_line_points(l2, s, inter)
                        l2.dxf.color = 7

                    # ELBO 삭제
                    msp.delete_entity(elbo)
                    modified = True

                    # 교차점에 원 3개 추가
                    for r in [0.1, 0.2, 0.3]:
                        msp.add_circle(center=inter, radius=r, dxfattribs={"color": 7})

        # 3. 모든 LWPOLYLINE, POLYLINE 일괄 WHITE 처리 (ELBO로 남아있는 경우 제외)
        for e in msp:
            if e.dxftype() in ["LWPOLYLINE", "POLYLINE"]:
                if not is_elbo(e):
                    e.dxf.color = 7
                modified = True

        # 4. PIPE TEXT 근처의 POLYLINE/LWPOLYLINE 처리: DP → P1,P2 연결선 그리기 → 삭제
        for pl in list(pipe_related_entities):
            if pl.dxftype() in ["LWPOLYLINE", "POLYLINE"]:
                pts = extract_polyline_points(pl)
                if len(pts) >= 2:
                    p1 = (pts[0][0], pts[0][1])
                    p2 = (pts[1][0], pts[1][1])
                    # 녹색선 (GREEN=3) 추가
                    msp.add_line(p1, p2, dxfattribs={'color': 3})
                    # 원본 DP 삭제
                    try:
                        msp.delete_entity(pl)
                        modified = True
                    except:
                        pass

        # PIPE TEXT 근처의 모든 엔티티들을 GREEN 처리
        for e in pipe_related_entities:
            if e.dxftype() in ["LINE", "LWPOLYLINE", "POLYLINE"]:
                try:
                    e.dxf.color = 3
                    modified = True
                except:
                    pass

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