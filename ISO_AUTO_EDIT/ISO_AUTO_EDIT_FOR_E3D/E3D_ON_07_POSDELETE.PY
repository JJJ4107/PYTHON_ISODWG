#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PDEL_STEP.py
- CONT(CONN) 기준 APOS(E/W, S/N, FL/EL) 그룹 탐지
- CONT/CONN 아래 APOS는 CYAN, 독립 APOS는 RED로 표시
- 독립 APOS 기준 TBOX 주변의 DEL1(폴리라인), 교차 DEL2(LINE), DEL3(3점 폴리라인) 탐지
- 해당 APOS 그룹 + DEL1/DEL2/DEL3 삭제
- 런너(in-memory) 연동용 process(doc) 제공
- CLI 다중 파일도 지원: python PDEL_STEP.py A.dxf B.dxf  → *_PDEL.dxf 자동 저장
"""

import os
import re
import ezdxf
import math
import sys
from typing import List, Tuple, Iterable, Optional

# ─────────────────────────────── 기본 유틸 ───────────────────────────────

def get_xy(e) -> Tuple[float, float]:
    """엔티티의 X, Y 좌표를 반환"""
    try:
        if hasattr(e, "dxf") and hasattr(e.dxf, "insert"):
            ins = e.dxf.insert
            if hasattr(ins, "x") and hasattr(ins, "y"):
                return float(ins.x), float(ins.y)
            if isinstance(ins, (tuple, list)) and len(ins) >= 2:
                return float(ins[0]), float(ins[1])
        elif hasattr(e, "insert"):
            ins = e.insert
            if isinstance(ins, (tuple, list)) and len(ins) >= 2:
                return float(ins[0]), float(ins[1])
    except Exception:
        pass
    return 0.0, 0.0


def get_text(e) -> str:
    """엔티티의 텍스트(plain) 추출(TEXT/MTEXT 호환)"""
    try:
        # MTEXT: plain_text() 선호
        if hasattr(e, "plain_text") and callable(e.plain_text):
            return e.plain_text().strip()
        # TEXT/MTEXT 공통: dxf.text
        if hasattr(e, "dxf") and hasattr(e.dxf, "text"):
            return (e.dxf.text or "").strip()
        # 일부 구현체: .text
        if hasattr(e, "text"):
            return (e.text or "").strip()
    except Exception:
        pass
    return ""


def set_color(e, color: int) -> bool:
    """엔티티 색상 설정(ACI)"""
    try:
        if hasattr(e, "dxf"):
            e.dxf.color = int(color)
            return True
    except Exception:
        pass
    return False


# ───────────────────────────── 텍스트/그룹 탐색 ─────────────────────────────

def find_special_below(
    msp,
    base_x: float,
    base_y: float,
    x_tol: float = 4.0,
    y_tol: float = 20.0,
    patt: Optional[str] = None,
) -> List:
    """기준 좌표 아래 x/y 허용 내 특정 패턴 텍스트 후보들을 가까운 순서로"""
    candidates: List[Tuple[float, object]] = []
    for e in msp.query("TEXT MTEXT"):
        txt = get_text(e)
        if not txt:
            continue
        x, y = get_xy(e)
        if abs(x - base_x) <= x_tol and (y < base_y) and (0 < (base_y - y) <= y_tol):
            if patt is None or re.search(patt, txt, re.I):
                candidates.append((base_y - y, e))
    candidates.sort(key=lambda t: t[0])
    return [e for _, e in candidates]


def get_text_width(e) -> float:
    """텍스트 폭 추정: height * len * 0.7 (대략치)"""
    try:
        text = get_text(e)
        if not text:
            return 10.0
        h = getattr(e.dxf, "height", 2.5) or 2.5
        return float(h) * len(text) * 0.7
    except Exception:
        return 10.0


def get_tbox(entities: Iterable) -> Optional[Tuple[float, float, float, float]]:
    """
    APOS 묶음의 TBOX:
    - 가장 긴 텍스트 폭을 기준
    - X는 center + (max_width/2), Y는 center + (text_height/2) 시프팅
    """
    entities = list(entities)
    if not entities:
        return None

    max_w = 0.0
    text_h = 2.5
    xs, ys = [], []
    for e in entities:
        w = get_text_width(e)
        if w > max_w:
            max_w = w
            if hasattr(e, "dxf") and hasattr(e.dxf, "height"):
                text_h = float(e.dxf.height or 2.5)
        x, y = get_xy(e)
        xs.append(x)
        ys.append(y)

    cx = sum(xs) / len(xs)
    cy = sum(ys) / len(ys)

    scx = cx + max_w / 2.0
    scy = cy + text_h / 2.0

    min_x = scx - max_w / 2.0
    max_x = scx + max_w / 2.0
    min_y = min(ys) - 2.0
    max_y = max(ys) + 2.0
    return (min_x, min_y, max_x, max_y)


# ───────────────────────────── 폴리라인/기하 유틸 ─────────────────────────────

def distance_point_to_line(px, py, x1, y1, x2, y2) -> float:
    """점-선분 최단거리"""
    dx, dy = (x2 - x1), (y2 - y1)
    l2 = dx * dx + dy * dy
    if l2 <= 0.0:
        return math.hypot(px - x1, py - y1)
    t = ((px - x1) * dx + (py - y1) * dy) / l2
    t = max(0.0, min(1.0, t))
    projx = x1 + t * dx
    projy = y1 + t * dy
    return math.hypot(px - projx, py - projy)


def lines_intersect(x1, y1, x2, y2, x3, y3, x4, y4) -> bool:
    """두 선분 교차 판정"""
    def ccw(A, B, C):
        return (C[1] - A[1]) * (B[0] - A[0]) > (B[1] - A[1]) * (C[0] - A[0])

    A, B, C, D = (x1, y1), (x2, y2), (x3, y3), (x4, y4)
    return (ccw(A, C, D) != ccw(B, C, D)) and (ccw(A, B, C) != ccw(A, B, D))


def point_in_box(px, py, box) -> bool:
    min_x, min_y, max_x, max_y = box
    return (min_x <= px <= max_x) and (min_y <= py <= max_y)


def line_intersects_box(x1, y1, x2, y2, box) -> bool:
    if point_in_box(x1, y1, box) or point_in_box(x2, y2, box):
        return True
    min_x, min_y, max_x, max_y = box
    edges = [
        (min_x, min_y, max_x, min_y),
        (max_x, min_y, max_x, max_y),
        (max_x, max_y, min_x, max_y),
        (min_x, max_y, min_x, min_y),
    ]
    for bx1, by1, bx2, by2 in edges:
        if lines_intersect(x1, y1, x2, y2, bx1, by1, bx2, by2):
            return True
    return False


def get_polyline_points(polyline) -> List[Tuple[float, float]]:
    pts: List[Tuple[float, float]] = []
    try:
        if polyline.dxftype() == "LWPOLYLINE":
            # get_points() → (x, y, start_width, end_width, bulge)
            for p in polyline.get_points():
                if isinstance(p, (tuple, list)) and len(p) >= 2:
                    pts.append((float(p[0]), float(p[1])))
        elif polyline.dxftype() == "POLYLINE":
            for v in polyline.vertices:
                loc = v.dxf.location
                pts.append((float(loc.x), float(loc.y)))
    except Exception:
        pass
    return pts


def get_polyline_length(points: List[Tuple[float, float]]) -> float:
    if len(points) < 2:
        return 0.0
    s = 0.0
    for i in range(len(points) - 1):
        x1, y1 = points[i]
        x2, y2 = points[i + 1]
        s += math.hypot(x2 - x1, y2 - y1)
    return s


def get_polyline_angles(points: List[Tuple[float, float]]) -> List[float]:
    angs: List[float] = []
    for i in range(len(points) - 1):
        x1, y1 = points[i]
        x2, y2 = points[i + 1]
        a = math.degrees(math.atan2(y2 - y1, x2 - x1))
        if a < 0:
            a += 360.0
        angs.append(a)
    return angs


def polyline_near_tbox(points: List[Tuple[float, float]], box, tolerance: float = 5.0) -> bool:
    min_x, min_y, max_x, max_y = box
    # 점이 박스 내부?
    for px, py in points:
        if point_in_box(px, py, box):
            return True
    # 선분-박스 교차?
    for i in range(len(points) - 1):
        if line_intersects_box(points[i][0], points[i][1], points[i + 1][0], points[i + 1][1], box):
            return True
    # 코너/에지로부터의 거리
    corners = [(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)]
    for px, py in points:
        for bx, by in corners:
            if math.hypot(px - bx, py - by) <= tolerance:
                return True
    edges = [
        (min_x, min_y, max_x, min_y),
        (max_x, min_y, max_x, max_y),
        (max_x, max_y, min_x, max_y),
        (min_x, max_y, min_x, min_y),
    ]
    for px, py in points:
        for x1, y1, x2, y2 in edges:
            if distance_point_to_line(px, py, x1, y1, x2, y2) <= tolerance:
                return True
    return False


# ───────────────────────────── DEL1/2/3 탐지 ─────────────────────────────

def find_arrow_lines(msp, polyline_points: List[Tuple[float, float]]) -> List:
    """DEL1 폴리라인과 교차하는 LINE 1개(PIPE 레이어 제외)"""
    if len(polyline_points) < 2:
        return []
    segs = []
    for i in range(len(polyline_points) - 1):
        x1, y1 = polyline_points[i]
        x2, y2 = polyline_points[i + 1]
        segs.append((x1, y1, x2, y2))

    for line in msp.query("LINE"):
        try:
            if "PIPE" in line.dxf.layer.upper():
                continue
            s = line.dxf.start
            e = line.dxf.end
            for a, b, c, d in segs:
                if lines_intersect(s.x, s.y, e.x, e.y, a, b, c, d):
                    return [line]
        except Exception:
            continue
    return []


def find_del3_polylines(msp, del2_line) -> List:
    """DEL2 양끝을 모두 맞대는 3점 ARROW/GT_1/PL3 폴리라인(총 길이 ≤5, PIPE 제외)"""
    if not del2_line:
        return []
    s = del2_line.dxf.start
    e = del2_line.dxf.end
    ends = [(s.x, s.y), (e.x, e.y)]

    for pl in msp.query("LWPOLYLINE POLYLINE"):
        try:
            layer = pl.dxf.layer.upper()
        except Exception:
            continue
        if "PIPE" in layer:
            continue
        if not ("ARROW" in layer or "GT_1" in layer or "PL3" in layer):
            continue

        pts = get_polyline_points(pl)
        if len(pts) != 3:
            continue
        if get_polyline_length(pts) > 5.0:
            continue

        matched = 0
        for dx, dy in ends:
            for px, py in pts:
                if math.hypot(px - dx, py - dy) < 0.1:
                    matched += 1
                    break
        if matched >= 2:
            return [pl]
    return []


# ───────────────────────────── APOS 그룹 탐색 ─────────────────────────────

def find_apos_group_from_cont(msp, cont_x: float, cont_y: float) -> List[List]:
    """CONT/CONN 텍스트 기준 아래로 완전한 APOS(E/W, S/N, FL/EL) 찾기"""
    groups: List[List] = []
    afdno_es = find_special_below(msp, cont_x, cont_y, x_tol=4, y_tol=20, patt=r"(-|FMF)")
    for afd in afdno_es:
        color = getattr(afd.dxf, "color", 256)
        if color not in (1, 2, 5):  # RED/YELLOW/BLUE
            continue
        ax, ay = get_xy(afd)
        epos = find_special_below(msp, ax, ay, x_tol=4, y_tol=20, patt=r"\b(E|W)\b")
        if not epos:
            continue
        ex, ey = get_xy(epos[0])
        npos = find_special_below(msp, ex, ey, x_tol=4, y_tol=20, patt=r"\b(S|N)\b")
        if not npos:
            continue
        nx, ny = get_xy(npos[0])
        flpos = find_special_below(msp, nx, ny, x_tol=4, y_tol=20, patt=r"(FL|EL)")
        if not flpos:
            continue
        groups.append([epos[0], npos[0], flpos[0]])
    return groups


def find_independent_apos_groups(msp, cont_apos_entities: Iterable) -> List[List]:
    """CONT 소속 제외, 독립 APOS(E/W→S/N→FL/EL) 그룹"""
    cont_set = set(cont_apos_entities)
    groups: List[List] = []
    for e in msp.query("TEXT MTEXT"):
        if e in cont_set:
            continue
        txt = get_text(e).upper()
        if not txt or not re.search(r"\b(E|W)\b", txt):
            continue
        ex, ey = get_xy(e)
        npos = find_special_below(msp, ex, ey, x_tol=4, y_tol=20, patt=r"\b(S|N)\b")
        if not npos:
            continue
        if npos[0] in cont_set:
            continue
        nx, ny = get_xy(npos[0])
        flpos = find_special_below(msp, nx, ny, x_tol=4, y_tol=20, patt=r"(FL|EL)")
        if not flpos or (flpos[0] in cont_set):
            continue
        groups.append([e, npos[0], flpos[0]])
    return groups


# ───────────────────────────── 메인 처리 로직 ─────────────────────────────

def _collect_entities_to_delete(msp, apos_group: List) -> List:
    """APOS 그룹을 기준으로 DEL1/DEL2/DEL3 탐지 및 삭제 후보 수집"""
    to_del: List = []
    tbox = get_tbox(apos_group)
    if not tbox:
        return to_del

    # 후보 DEL1: GT_1 / PL2 / ARROW 레이어 폴리라인(PIPE 제외), 점수 2~3, 길이 ≥2.5, TBOX 근접
    cands: List[Tuple[float, object, List[Tuple[float, float]]]] = []
    for pl in msp.query("LWPOLYLINE POLYLINE"):
        try:
            layer = pl.dxf.layer.upper()
        except Exception:
            continue
        if "PIPE" in layer:
            continue
        if not ("GT_1" in layer or "PL2" in layer or "ARROW" in layer):
            continue
        pts = get_polyline_points(pl)
        if len(pts) < 2 or len(pts) > 3:
            continue
        if get_polyline_length(pts) < 2.5:
            continue
        if not polyline_near_tbox(pts, tbox, tolerance=5.0):
            continue
        # 최소거리로 1개만 선택
        # (min distance = 코너/에지 거리 중 최솟값)
        min_d = float("inf")
        min_x, min_y, max_x, max_y = tbox
        corners = [(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)]
        edges = [
            (min_x, min_y, max_x, min_y),
            (max_x, min_y, max_x, max_y),
            (max_x, max_y, min_x, max_y),
            (min_x, max_y, min_x, min_y),
        ]
        for px, py in pts:
            for bx, by in corners:
                d = math.hypot(px - bx, py - by)
                if d < min_d:
                    min_d = d
            for x1, y1, x2, y2 in edges:
                d = distance_point_to_line(px, py, x1, y1, x2, y2)
                if d < min_d:
                    min_d = d
        cands.append((min_d, pl, pts))

    if not cands:
        return to_del

    cands.sort(key=lambda x: x[0])
    _, del1, del1_pts = cands[0]
    to_del.append(del1)

    # DEL2: DEL1과 교차하는 LINE(PIPE 제외) 1개
    del2 = None
    ar_lines = find_arrow_lines(msp, del1_pts)
    if ar_lines:
        del2 = ar_lines[0]
        to_del.append(del2)

    # DEL3: DEL2 양끝을 모두 맞대는 3점 폴리라인(ARROW/GT_1/PL3, 길이≤5)
    if del2 is not None:
        del3s = find_del3_polylines(msp, del2)
        to_del.extend(del3s)

    # 해당 APOS 그룹 자체도 삭제
    to_del.extend(list(apos_group))
    return to_del


def _delete_entities(msp, entities: Iterable):
    """엔티티 안전 삭제(중복/핸들 기반 정리)"""
    seen = set()
    ordered = []
    for e in entities:
        try:
            h = getattr(e.dxf, "handle", None)
        except Exception:
            h = None
        key = (e.dxftype(), h)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(e)

    for e in ordered:
        try:
            msp.delete_entity(e)
        except Exception:
            # 이미 삭제되었거나 삭제 불가한 경우 무시
            pass


# ───────────────────────────── 외부/런너 인터페이스 ─────────────────────────────

def process(doc) -> object:
    """
    런너(in-memory)용 엔트리:
    - doc: ezdxf.document.Drawing
    - 반환: 변형된 doc (동일 객체)
    """
    try:
        msp = doc.modelspace()

        # 1) CONT/CONN 텍스트 스캔 및 CONT 소속 APOS(CYAN) 식별
        cont_groups_all: List[List] = []
        cont_entities_all: List = []

        for e in msp.query("TEXT MTEXT"):
            t = get_text(e).upper()
            if not t:
                continue
            if (("CONT" in t and "." in t) or ("CONN" in t and "." in t)):
                cx, cy = get_xy(e)
                groups = find_apos_group_from_cont(msp, cx, cy)
                for g in groups:
                    cont_groups_all.append(g)
                    cont_entities_all.extend(g)
                    for ge in g:
                        set_color(ge, 4)  # CYAN

        # 2) 독립 APOS(RED) 탐색
        indep_groups = find_independent_apos_groups(msp, cont_entities_all)
        for g in indep_groups:
            for ge in g:
                set_color(ge, 1)  # RED

        # 3) 독립 APOS 기준 DEL1/DEL2/DEL3 + APOS 삭제
        to_delete: List = []
        for g in indep_groups:
            to_delete.extend(_collect_entities_to_delete(msp, g))

        _delete_entities(msp, to_delete)

        return doc
    except Exception:
        # 조용 실패(런너 일관성 유지). 필요 시 런너에서 try/except로 잡음
        return doc


# 옵션: 다른 런너 호환 래퍼(필요 시)
def pipeline(doc):  # noqa
    return process(doc)

def run(doc):  # noqa
    return process(doc)

def main_process(doc):  # noqa
    return process(doc)


# ───────────────────────────── CLI 진입점(무조건 저장) ─────────────────────────────

def process_file(path: str) -> Optional[str]:
    if not (os.path.exists(path) and path.lower().endswith(".dxf")):
        return None
    try:
        doc = ezdxf.readfile(path)
    except Exception:
        return None
    process(doc)
    base = os.path.splitext(path)[0]
    out_path = f"{base}_PDEL.dxf"
    try:
        doc.saveas(out_path)
        return out_path
    except Exception:
        return None


if __name__ == "__main__":
    # GUI/프린트 없이, 인자로 받은 모든 DXF를 처리하고 *_PDEL.dxf로 저장
    if len(sys.argv) >= 2:
        for p in sys.argv[1:]:
            try:
                process_file(p)
            except Exception:
                pass
    else:
        # 인자가 없으면 조용히 종료
        sys.exit(0)
