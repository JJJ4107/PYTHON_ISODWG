import ezdxf
import math
import sys
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
    center = (arc.dxf.center[0], arc.dxf.center[1])
    radius = arc.dxf.radius
    
    start_angle = math.radians(arc.dxf.start_angle)
    end_angle = math.radians(arc.dxf.end_angle)
    
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

def extract_line_points(e):
    return [(e.dxf.start[0], e.dxf.start[1]), (e.dxf.end[0], e.dxf.end[1])]

def set_line_points(e, new_start, new_end):
    e.dxf.start = new_start
    e.dxf.end = new_end

def process_doc(doc):
    """
    런너(in-memory) 연동용 process(doc) 엔트리
    ezdxf 문서 객체를 직접 처리하고 수정된 문서를 반환
    """
    msp = doc.modelspace()
    modified = False
    
    # 최적화: 한 번의 순회로 필요한 엔티티들을 분류 (시간복잡도 O(n))
    elbo_arcs = []
    polylines = []
    lines = []
    pipe_elbo_polylines = []
    
    for e in msp:
        if is_elbo_arc(e):
            ep1, ep2 = get_arc_endpoints(e)
            elbo_arcs.append((e, ep1, ep2))
        elif e.dxftype() in ["LWPOLYLINE", "POLYLINE"]:
            if hasattr(e, 'dxf') and hasattr(e.dxf, 'layer') and ("PIPE" in e.dxf.layer or "ELBO" in e.dxf.layer):
                pipe_elbo_polylines.append(e)
            else:
                polylines.append(e)
        elif e.dxftype() == "LINE" and hasattr(e, 'dxf') and hasattr(e.dxf, 'layer') and ("PIPE" in e.dxf.layer or "ELBO" in e.dxf.layer):
            lines.append(e)
    
    if elbo_arcs:
        modified = True

    # ELBO 호 처리 (시간복잡도 O(m*n), m은 ELBO 호 개수, n은 polyline+line 개수)
    for elbo, ep1, ep2 in elbo_arcs:
        elbo_layer = elbo.dxf.layer if hasattr(elbo.dxf, 'layer') else None
        
        l1, l2 = None, None
        l1_type, l2_type = None, None
        
        # POLYLINE/LWPOLYLINE에서 찾기
        for pl in polylines:
            if l1 and l2:
                break
            points = extract_polyline_points(pl)
            for pt in points:
                pt_xy = pt[:2]
                if distance(ep1, pt_xy) <= 0.3 and l1 is None:
                    l1 = pl
                    l1_type = "PLINE"
                elif distance(ep2, pt_xy) <= 0.3 and l2 is None:
                    l2 = pl
                    l2_type = "PLINE"
                if l1 and l2:
                    break
        
        # LINE에서 찾기 (못 찾았을 때)
        if l1 is None or l2 is None:
            for line in lines:
                if l1 and l2:
                    break
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
            else:
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
                    if elbo_layer:
                        l1.dxf.layer = elbo_layer
                else:
                    s, e = extract_line_points(l1)
                    if distance(s, inter) < distance(e, inter):
                        set_line_points(l1, inter, e)
                    else:
                        set_line_points(l1, s, inter)
                    if elbo_layer:
                        l1.dxf.layer = elbo_layer

                # L2 끝점 이동
                if l2_type == "PLINE":
                    if distance(l2_pts[0][:2], inter) < distance(l2_pts[-1][:2], inter):
                        l2_pts[0] = (inter[0], inter[1], 0, 0, 0)
                    else:
                        l2_pts[-1] = (inter[0], inter[1], 0, 0, 0)
                    set_poly_points(l2, l2_pts)
                    if elbo_layer:
                        l2.dxf.layer = elbo_layer
                else:
                    s, e = extract_line_points(l2)
                    if distance(s, inter) < distance(e, inter):
                        set_line_points(l2, inter, e)
                    else:
                        set_line_points(l2, s, inter)
                    if elbo_layer:
                        l2.dxf.layer = elbo_layer

                # ELBO 호 삭제
                msp.delete_entity(elbo)
                modified = True

                # 교차점에 원 3개 추가
                for r in [0.1, 0.2, 0.3]:
                    msp.add_circle(center=inter, radius=r, dxfattribs={"color": 7})

    # PIPE/ELBO 레이어 POLYLINE 처리 (시간복잡도 O(k), k는 PIPE/ELBO polyline 개수)
    for pl in pipe_elbo_polylines:
        pts = extract_polyline_points(pl)
        if len(pts) >= 2:
            p1 = (pts[0][0], pts[0][1])
            p2 = (pts[1][0], pts[1][1])
            msp.add_line(p1, p2, dxfattribs={'layer': pl.dxf.layer})
            msp.delete_entity(pl)
            modified = True

    return doc, modified

def process_file(filepath):
    """
    파일 기반 처리 함수
    """
    try:
        doc = ezdxf.readfile(filepath)
        doc, modified = process_doc(doc)
        
        # 무조건 저장
        new_path = os.path.splitext(filepath)[0] + "_elbo.dxf"
        doc.saveas(new_path)
        
        return new_path, modified
        
    except Exception as e:
        return None, False

def main():
    """
    메인 함수 - 커맨드 라인 인자 처리
    사용법: python PLTONEWLINE.py A.dxf B.dxf C.dxf ...
    """
    if len(sys.argv) < 2:
        sys.exit(1)
    
    # 커맨드 라인에서 DXF 파일들 처리
    for filepath in sys.argv[1:]:
        if not filepath.lower().endswith('.dxf'):
            continue
            
        if not os.path.exists(filepath):
            continue
            
        new_path, modified = process_file(filepath)

if __name__ == "__main__":
    main()

# 시간복잡도 분석:
# - 전체 시간복잡도: O(n + m*n + k)
#   - n: 전체 엔티티 개수
#   - m: ELBO 호 개수 (일반적으로 n보다 훨씬 작음)
#   - k: PIPE/ELBO 레이어 polyline 개수
# - 최적화 포인트:
#   1. 한 번의 순회로 엔티티 분류 (기존 여러 번 순회 → 1번 순회)
#   2. 필요한 엔티티만 저장하여 메모리 효율성 증대
#   3. 조건 검사 최소화
# - 메모리 복잡도: O(n) (분류된 엔티티 저장)