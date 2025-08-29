# -*- coding: utf-8 -*-
import ezdxf
import os
import math
from ezdxf.math import Vec2
import sys

### 유틸 함수들 ###
def distance(p1, p2):
    if isinstance(p1, Vec2) and isinstance(p2, Vec2):
        return math.hypot(p2.x - p1.x, p2.y - p1.y)
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])

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
    if len(points) < 2:
        return True
    base = points[0][:2]
    for pt in points[1:]:
        if distance(base, pt[:2]) > tol:
            return False
    return True

### WELDSYMBOL 기능 - WELD 레이어 7개 점 찾아서 원 그리기 ###
def process_weldsymbol(doc):
    msp = doc.modelspace()
    to_delete = []
    weld_count = 0

    for weld in list(msp.query('LWPOLYLINE POLYLINE')):
        # 7개 점인지 확인
        points = get_poly_points(weld)
        if len(points) != 7:
            continue

        # 모든 점이 거의 같은 위치에 있는지 확인
        if is_nearly_same_points(points):
            continue

        # 점들 간 거리가 너무 멀지 않은지 확인 (2mm 이내)
        too_far = False
        for i in range(6):
            d = distance(points[i][:2], points[i+1][:2])
            if d > 2.0:
                too_far = True
                break
        if too_far:
            continue

        # 중심점 계산
        weld_center = midpoint([pt[:2] for pt in points])
        if not is_valid_center(weld_center):
            continue

        # 폴리라인 길이 확인
        length = polyline_length(weld)
        if length < 1 or length > 100:
            continue

        # 작은 라인들 찾기 (3mm 이내의 짧은 선들)
        short_plines = []
        for pl in msp.query('LWPOLYLINE POLYLINE LINE'):
            if pl == weld:
                continue
            pts = get_poly_points(pl)
            if len(pts) != 2:
                continue
            # WELD 점들과 가까운지 확인
            if any(distance(pt[:2], wp[:2]) <= 3.0 for pt in pts for wp in points):
                if polyline_length(pl) <= 2.8:
                    short_plines.append(pl)

        # 메인 원 그리기 (반지름 1mm)
        main_circle = msp.add_circle(center=weld_center, radius=1, dxfattribs={"color": 2})
        main_circle.dxf.lineweight = 20

        # SW/OW 레이어 결정 (작은 라인이 5개 이상이면 SW, 아니면 OW)
        main_circle.dxf.layer = "SW" if len(short_plines) >= 5 else "OW"

        # linetype이 BYLAYER인 경우 안쪽에 여러 개의 원 그리기
        if hasattr(weld.dxf, 'linetype') and str(weld.dxf.linetype).upper() == "BYLAYER":
            for r in [0.85, 0.7, 0.55, 0.4, 0.25]:
                inner = msp.add_circle(center=weld_center, radius=r, dxfattribs={"color": 2})
                inner.dxf.lineweight = 20

        # 삭제할 엔티티 목록에 추가
        to_delete.append(weld)
        to_delete.extend(short_plines)
        weld_count += 1

    # 엔티티 삭제
    for ent in to_delete:
        try:
            msp.delete_entity(ent)
        except Exception:
            pass

# ── ★ 런너 연동용 엔트리: in-memory 문서만 수정 ★
def process(doc):
    """
    SAE3D_ON_RUNTEST.PY가 호출하는 엔트리.
    - 파일 I/O 없이 현재 문서(doc)만 수정 후 반환
    - 오류 시 None → 런너가 직전 상태 유지
    """
    try:
        process_weldsymbol(doc)
        return doc
    except Exception:
        return None

# (선택) 호환 별칭: 런너가 다양한 이름을 찾도록 지원
run = process
pipeline = process
main_process = process

### 메인 실행 (단독 실행용) ###
if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)

    filepaths = sys.argv[1:]
    for filepath in filepaths:
        try:
            # DXF 파일 읽기
            doc = ezdxf.readfile(filepath)

            # WELD 처리
            process_weldsymbol(doc)

            # 출력 파일명 생성
            basename = os.path.splitext(os.path.basename(filepath))[0]
            output_dir = os.path.dirname(filepath)
            output_path = os.path.join(output_dir, basename + "_WELD.dxf")

            # 파일 저장
            try:
                doc.saveas(output_path)
            except PermissionError:
                # 권한 오류 시 바탕화면에 저장
                import getpass
                username = getpass.getuser()
                desktop_path = f"C:/Users/{username}/Desktop/{basename}_WELD.dxf"
                try:
                    doc.saveas(desktop_path)
                except Exception:
                    # 현재 디렉토리에 저장
                    current_dir_path = f"./{basename}_WELD.dxf"
                    try:
                        doc.saveas(current_dir_path)
                    except Exception:
                        pass

        except Exception:
            # 개별 파일 실패는 넘어가고 다음 파일 처리
            continue
