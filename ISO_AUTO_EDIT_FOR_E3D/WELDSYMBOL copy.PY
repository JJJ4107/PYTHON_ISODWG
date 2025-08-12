import ezdxf
import math
import os
import tkinter as tk
from tkinter import filedialog

def distance(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

def midpoint(points):
    x = sum(p[0] for p in points) / len(points)
    y = sum(p[1] for p in points) / len(points)
    return (x, y)

def polyline_length(pl):
    try:
        if pl.dxftype() == 'LWPOLYLINE':
            points = [p[:2] for p in pl.get_points()]
        elif pl.dxftype() == 'POLYLINE':
            points = []
            for v in pl.vertices:
                if hasattr(v.dxf, 'location'):
                    pt = (v.dxf.location.x, v.dxf.location.y)
                    points.append(pt)
            if not points:
                return 0
        else:
            return 0
        return sum(distance(points[i], points[i+1]) for i in range(len(points)-1))
    except Exception:
        return 0

def get_poly_points(pl):
    try:
        if pl.dxftype() == 'LWPOLYLINE':
            points = list(pl.get_points())
            points = [pt for pt in points if abs(pt[0]) > 1e-8 or abs(pt[1]) > 1e-8]
            return points
        elif pl.dxftype() == 'POLYLINE':
            pts = []
            for v in pl.vertices:
                if hasattr(v.dxf, 'location'):
                    x, y = v.dxf.location.x, v.dxf.location.y
                    if abs(x) > 1e-8 or abs(y) > 1e-8:
                        pts.append((x, y, 0, 0))
            return pts
        else:
            return []
    except Exception:
        return []

def move_single_point_to(line, target_point, fixed_point):
    try:
        d_start = distance((line.dxf.start[0], line.dxf.start[1]), fixed_point)
        d_end = distance((line.dxf.end[0], line.dxf.end[1]), fixed_point)
        if d_start < d_end:
            line.dxf.end = target_point
        else:
            line.dxf.start = target_point
    except Exception:
        pass

def is_valid_center(center):
    if center is None:
        return False
    x, y = center
    if abs(x) < 1e-5 and abs(y) < 1e-5:
        return False
    if abs(x) > 1e5 or abs(y) > 1e5:
        return False
    return True

def is_nearly_same_points(points, tol=0.05):
    # 모든 점이 서로 거의 같은 위치면 True 반환 (공백/유령 폴리라인 방지)
    if len(points) < 2:
        return True
    base = points[0][:2]
    for pt in points[1:]:
        if distance(base, pt[:2]) > tol:
            return False
    return True

def process_file(filepath):
    try:
        doc = ezdxf.readfile(filepath)
        msp = doc.modelspace()
        modified = False
        to_delete = []

        for weld in list(msp.query('LWPOLYLINE POLYLINE')):
            points = get_poly_points(weld)
            if len(points) != 7:
                continue

            # 모든 점이 거의 같은 위치면 건너뜀 (공백 유령 폴리라인 방지)
            if is_nearly_same_points(points):
                continue

            weld_center = midpoint([pt[:2] for pt in points])
            if not is_valid_center(weld_center):
                continue

            # 전체 폴리라인 길이 체크 (실제 WELD 크기에 맞게 조정)
            length = polyline_length(weld)
            if length < 1 or length > 100:
                continue

            # 주변 2점짜리 POLYLINE (LWPOLYLINE or POLYLINE) 길이 2.2 이하 수집
            short_plines = []
            for pl in msp.query('LWPOLYLINE POLYLINE LINE'):
                if pl == weld:
                    continue
                pts = get_poly_points(pl)
                if len(pts) != 2:
                    continue
                if any(distance(pt[:2], wp[:2]) <= 3.0 for pt in pts for wp in points):
                    if polyline_length(pl) <= 2.8:
                        short_plines.append(pl)

            # 중심 원 생성 (1.6mm, color 2-yellow)
            main_circle = msp.add_circle(center=weld_center, radius=1, dxfattribs={"color": 2})
            main_circle.dxf.lineweight = 20

            # 선종류 변경
            if hasattr(weld.dxf, 'linetype') and isinstance(weld.dxf.linetype, str):
                if weld.dxf.linetype.upper() == "GT100":
                    weld.dxf.linetype = "DOT"

            # BYLAYER이면 CIRCLE 여러 겹(채운 듯한 느낌)
            if hasattr(weld.dxf, 'linetype') and weld.dxf.linetype.upper() == "BYLAYER":
                for r in [0.85, 0.7, 0.55, 0.4, 0.25 ]:
                    inner = msp.add_circle(center=weld_center, radius=r, dxfattribs={"color": 2})
                    inner.dxf.lineweight = 20

            # 레이어 라벨링: 2점짜리 주변 폴리라인 5개 이상 = SW, 이하면 OW
            main_circle.dxf.layer = "SW" if len(short_plines) >= 5 else "OW"

            # 빨간 선 stretch
            red_lines = []
            for ent in msp.query('LINE'):
                if hasattr(ent.dxf, 'color') and ent.dxf.color == 1:
                    p_start = (ent.dxf.start[0], ent.dxf.start[1])
                    p_end = (ent.dxf.end[0], ent.dxf.end[1])
                    for pt in points:
                        if distance(pt[:2], p_start) <= 1 or distance(pt[:2], p_end) <= 1:
                            red_lines.append((ent, p_start, p_end))
                            break

            # 가장 가까운 점(wp1)만 weld 중심으로 이동
            for line, p1, p2 in red_lines:
                d1 = distance(p1, weld_center)
                d2 = distance(p2, weld_center)
                wp1 = p1 if d1 < d2 else p2
                wp2 = p2 if d1 < d2 else p1
                move_single_point_to(line, weld_center, fixed_point=wp2)
                break

            # 삭제 대상 등록
            to_delete.append(weld)
            to_delete.extend(short_plines)
            modified = True

        for ent in to_delete:
            try:
                msp.delete_entity(ent)
            except Exception:
                pass

        if modified:
            new_path = os.path.splitext(filepath)[0] + "_wsym.dxf"
            doc.saveas(new_path)
            print(f"✔ 저장 완료: {new_path}")
        else:
            print(f"⚠ 조건 일치 없음: {os.path.basename(filepath)}")

    except Exception as e:
        print(f"❌ 오류 - {filepath}: {e}")

def main():
    root = tk.Tk()
    root.withdraw()
    filepaths = filedialog.askopenfilenames(title="DXF 파일 선택", filetypes=[("DXF files", "*.dxf")])
    if not filepaths:
        print("❗ DXF 파일을 선택하지 않았습니다.")
        return

    for path in filepaths:
        process_file(path)

if __name__ == "__main__":
    main()
