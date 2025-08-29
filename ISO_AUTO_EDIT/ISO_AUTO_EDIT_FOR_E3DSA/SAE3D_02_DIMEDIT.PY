import os
import sys
import math
import ezdxf
import numpy as np
from typing import List, Tuple, Dict, Any, Iterable, Optional, Set
from ezdxf.entities import Line, LWPolyline, Polyline, Text
import tkinter as tk
from tkinter import filedialog
from tkinter import ttk

# ─────────────────────────────────────────────────────────────
# 설정 값
# ─────────────────────────────────────────────────────────────
ANGLE_TOLERANCE = 5.0  # 각도 허용 오차 (°)
DIM_LAYER_PREFIXES = ("GT_", "PL2")  # 치수선 레이어 접두사들

# 근접성/검색 윈도우 파라미터(성능/정확도 트레이드오프)
CLOSE_TOL = 0.2        # DIM 쌍에서 공통점으로 간주할 양끝 근접 거리(mm)
FAR_THR = 3.0          # DIM 쌍에서 반대쪽 끝점 사이 최소 거리(mm)
LEN_TOL = 0.5          # DIM 쌍 길이 허용 오차(mm)
CT_SEARCH_RADIUS = 50.0  # CT 후보 텍스트 탐색 반경(mm)
AD_TOL = 0.5           # AD1/AD2/AD3 탐색 근접 허용(mm)
TOUCH_TOL = 0.2        # DIM 선분에 접하는 AD3 판단(mm)
ARROW_LINE_TOL = 0.1   # AD3 점과 접하는 ARROW Line 판정(mm)
ARROW_LINE_MAXLEN = 1.0  # 삭제 대상 ARROW Line 최대 길이(mm)

# ─────────────────────────────────────────────────────────────
# 전역 TBOX 캐시
# ─────────────────────────────────────────────────────────────
TBOX_CACHE: Dict[str, Dict[str, Any]] = {}

def clear_tbox_cache():
    global TBOX_CACHE
    TBOX_CACHE = {}

# ─────────────────────────────────────────────────────────────
# 수학/기하 유틸
# ─────────────────────────────────────────────────────────────

def to2d(pt):
    if hasattr(pt, "__getitem__"):
        return np.array((float(pt[0]), float(pt[1])), float)
    return np.array((float(pt.x), float(pt.y)), float)


def distance(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(a - b))


def angle_deg(a: np.ndarray, b: np.ndarray) -> float:
    dx, dy = b - a
    return (math.degrees(math.atan2(float(dy), float(dx))) + 360.0) % 360.0


def point_to_line_distance(point: np.ndarray, line_start: np.ndarray, line_end: np.ndarray) -> float:
    line_vec = line_end - line_start
    lsq = float(np.dot(line_vec, line_vec))
    if lsq == 0.0:
        return distance(point, line_start)
    t = float(np.dot(point - line_start, line_vec) / lsq)
    t = max(0.0, min(1.0, t))
    closest = line_start + t * line_vec
    return distance(point, closest)


def get_entity_handle(entity) -> str:
    try:
        if hasattr(entity, 'dxf') and hasattr(entity.dxf, 'handle'):
            return str(entity.dxf.handle)
        elif hasattr(entity, 'handle'):
            return str(entity.handle)
        return str(id(entity))
    except Exception:
        return "unknown"


# ─────────────────────────────────────────────────────────────
# 공간 해시(Spatial Hash) 인덱스
#  - 평균 O(n·k) 근접 질의(k는 작은 상수)
# ─────────────────────────────────────────────────────────────
class SpatialHash2D:
    __slots__ = ("cell", "_buckets")

    def __init__(self, cell: float):
        self.cell: float = max(1e-6, float(cell))
        self._buckets: Dict[Tuple[int, int], List[Tuple[np.ndarray, Any]]] = {}

    def _key(self, p: np.ndarray) -> Tuple[int, int]:
        return (int(math.floor(float(p[0]) / self.cell)), int(math.floor(float(p[1]) / self.cell)))

    def insert(self, p: np.ndarray, payload: Any) -> None:
        k = self._key(p)
        self._buckets.setdefault(k, []).append((p, payload))

    def query(self, p: np.ndarray, radius: float) -> Iterable[Tuple[np.ndarray, Any]]:
        r = max(radius, 0.0)
        rx = int(math.ceil(r / self.cell))
        ry = int(math.ceil(r / self.cell))
        kx, ky = self._key(p)
        for ix in range(kx - rx, kx + rx + 1):
            for iy in range(ky - ry, ky + ry + 1):
                for qp, payload in self._buckets.get((ix, iy), ()):  # type: ignore
                    # 실제 거리 필터는 호출측에서 수행(필요시)
                    yield qp, payload


# ─────────────────────────────────────────────────────────────
# DXF 엔티티 유틸
# ─────────────────────────────────────────────────────────────

def extract_segments(ent) -> List[Tuple[Any, Any]]:
    if isinstance(ent, Line):
        return [(ent.dxf.start, ent.dxf.end)]
    if isinstance(ent, LWPolyline):
        pts = list(ent.get_points("xyb"))
        z = float(ent.dxf.elevation)
        return [((x0, y0, z), (x1, y1, z)) for (x0, y0, _), (x1, y1, _) in zip(pts, pts[1:])]
    if isinstance(ent, Polyline):
        verts = list(ent.vertices)
        return [(verts[i].dxf.location, verts[i + 1].dxf.location) for i in range(len(verts) - 1)]
    return []


def is_enclosed(point, msp) -> bool:
    x, y = float(point[0]), float(point[1])
    for entity in msp.query("LWPOLYLINE POLYLINE"):
        try:
            if not entity.is_closed:
                continue
            if isinstance(entity, LWPolyline):
                pts = list(entity.get_points("xy"))
            else:
                pts = [(v.dxf.location[0], v.dxf.location[1]) for v in entity.vertices]
            if len(pts) < 3:
                continue
            if point_in_polygon(x, y, pts):
                return True
        except Exception:
            pass
    return False


def point_in_polygon(x: float, y: float, poly_pts: List[Tuple[float, float]]) -> bool:
    n = len(poly_pts)
    inside = False
    p1x, p1y = poly_pts[0]
    for i in range(1, n + 1):
        p2x, p2y = poly_pts[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside


# ─────────────────────────────────────────────────────────────
# TBOX
# ─────────────────────────────────────────────────────────────

def get_text_key(txt: Text) -> str:
    try:
        h = get_entity_handle(txt)
        if hasattr(txt.dxf, 'insert') and txt.dxf.insert is not None:
            ins = txt.dxf.insert
            return f"{h}_{float(ins[0])}_{float(ins[1])}"
        return h
    except Exception:
        return str(id(txt))


def get_text_dimensions(txt) -> Tuple[float, float]:
    try:
        if txt.dxftype() == "TEXT":
            val = txt.dxf.text
            height = float(txt.dxf.height)
            char_w = height * 0.6
            return len(val) * char_w, height
        elif txt.dxftype() == "MTEXT":
            val = txt.plain_text() if hasattr(txt, "plain_text") else txt.dxf.text
            height = float(getattr(txt.dxf, 'char_height', 1.0))
            char_w = height * 0.6
            return len(val) * char_w, height
    except Exception:
        return 0.0, 0.0
    return 0.0, 0.0


def create_tbox(txt) -> Optional[Dict[str, Any]]:
    key = get_text_key(txt)
    if key in TBOX_CACHE:
        return TBOX_CACHE[key]

    # 위치
    if hasattr(txt.dxf, 'insert') and txt.dxf.insert is not None:
        pos = to2d(txt.dxf.insert)
    elif hasattr(txt.dxf, 'align_point') and txt.dxf.align_point is not None:
        pos = to2d(txt.dxf.align_point)
    else:
        return None

    length, height = get_text_dimensions(txt)
    left = float(pos[0])
    right = left + length
    bottom = float(pos[1])
    top = bottom + height

    # +X 로 길이/2 만큼 이동
    move_x = length / 2.0
    left += move_x
    right += move_x

    corners = [
        np.array([left, bottom]),
        np.array([right, bottom]),
        np.array([right, top]),
        np.array([left, top]),
    ]

    info = {
        'corners': corners,
        'left': left,
        'right': right,
        'bottom': bottom,
        'top': top,
        'text_length': length,
        'text_height': height,
        'original_position': pos,
    }
    TBOX_CACHE[key] = info
    return info


# ─────────────────────────────────────────────────────────────
# 고성능 DIM 쌍 찾기: 공간 해시 이용
#  - 평균 O(n·k)
# ─────────────────────────────────────────────────────────────

def _layer_starts_with(ent, prefixes: Tuple[str, ...]) -> bool:
    try:
        lname = ent.dxf.layer
        for p in prefixes:
            if lname.startswith(p):
                return True
        return False
    except Exception:
        return False


def find_dim_pairs_indexed(all_line_entities: List[Any]) -> Tuple[List[Dict[str, Any]], List[Any]]:
    two_point: List[Tuple[Any, np.ndarray, np.ndarray, float]] = []

    for ent in all_line_entities:
        try:
            if not _layer_starts_with(ent, DIM_LAYER_PREFIXES):
                continue
            segs = extract_segments(ent)
            if len(segs) != 1:
                continue
            p0, p1 = segs[0]
            v0, v1 = to2d(p0), to2d(p1)
            length = distance(v0, v1)
            if 1.5 <= length <= 12.0:
                two_point.append((ent, v0, v1, length))
        except Exception:
            continue

    # 공간 해시: 가까운 끝점만 후보로
    idx = SpatialHash2D(cell=CLOSE_TOL)
    for i, (_, v0, v1, _) in enumerate(two_point):
        idx.insert(v0, (i, 0))
        idx.insert(v1, (i, 1))

    dim_pairs: List[Dict[str, Any]] = []
    overlapped: List[Any] = []

    used: Set[Tuple[int, int]] = set()  # (min_i, max_j) 중복 방지

    for i, (e1, v0_1, v1_1, len1) in enumerate(two_point):
        for endpoint, v_close_1, v_far_1 in ((0, v0_1, v1_1), (1, v1_1, v0_1)):
            # 근접 후보만
            for qp, (j, ep_j) in idx.query(v_close_1, CLOSE_TOL):
                if j <= i:
                    continue
                e2, v0_2, v1_2, len2 = two_point[j]
                if abs(len1 - len2) > LEN_TOL:
                    continue

                # j의 가까운/먼 점 결정
                v_close_2 = v0_2 if ep_j == 0 else v1_2
                v_far_2 = v1_2 if ep_j == 0 else v0_2

                if distance(v_close_1, v_close_2) > CLOSE_TOL:
                    continue

                # 완전 중첩(두 끝점 모두 근접)
                if distance(v_far_1, v_far_2) <= CLOSE_TOL:
                    if e1 not in overlapped:
                        e1.dxf.color = 3
                        overlapped.append(e1)
                    if e2 not in overlapped:
                        e2.dxf.color = 3
                        overlapped.append(e2)
                    continue

                # 반대 방향/멀리 떨어져 있는지
                if distance(v_far_1, v_far_2) < FAR_THR:
                    continue
                vec1 = v_far_1 - v_close_1
                vec2 = v_far_2 - v_close_2
                if float(np.dot(vec1, vec2)) >= 0.0:
                    continue

                key = (i, j)
                if key in used:
                    continue
                used.add(key)

                dim_pairs.append({
                    'DIM1': e1,
                    'DIM2': e2,
                    'DIM1_common': v_close_1,
                    'DIM1_opposite': v_far_1,
                    'DIM2_common': v_close_2,
                    'DIM2_opposite': v_far_2,
                    'common_point': (v_close_1 + v_close_2) / 2.0,
                    'length': (len1 + len2) / 2.0,
                })

    return dim_pairs, overlapped


# ─────────────────────────────────────────────────────────────
# AD1/AD2/AD3 탐색: 공간 인덱스(3점 폴리라인 점들)
# ─────────────────────────────────────────────────────────────

def _collect_three_point_polylines(all_line_entities: List[Any], layers: Tuple[str, ...] = ()) -> List[Any]:
    out: List[Any] = []
    for ent in all_line_entities:
        try:
            if not isinstance(ent, (LWPolyline, Polyline)):
                continue
            if layers:
                lname = ent.dxf.layer.upper()
                ok = any(lname.startswith(layer.upper()) for layer in layers)
                if not ok:
                    continue
            if isinstance(ent, LWPolyline):
                pts = list(ent.get_points("xy"))
            else:
                pts = [v.dxf.location for v in ent.vertices]
            if len(pts) == 3:
                out.append(ent)
        except Exception:
            continue
    return out


def _build_point_index_for_entities(entities: List[Any], cell: float) -> SpatialHash2D:
    idx = SpatialHash2D(cell=cell)
    for ent in entities:
        try:
            if isinstance(ent, LWPolyline):
                pts = list(ent.get_points("xy"))
            else:
                pts = [v.dxf.location for v in ent.vertices]
            for p in pts:
                idx.insert(to2d(p), ent)
        except Exception:
            continue
    return idx


def find_arrow_entities_indexed(all_line_entities: List[Any], near_point: np.ndarray, tol: float = AD_TOL) -> List[Any]:
    # DIM 레이어(접두사)만 대상
    three_pts = _collect_three_point_polylines(all_line_entities, layers=DIM_LAYER_PREFIXES)
    idx = _build_point_index_for_entities(three_pts, cell=tol)

    seen: Set[str] = set()
    result: List[Any] = []
    for qp, ent in idx.query(near_point, tol):
        try:
            if distance(qp, near_point) <= tol:
                h = get_entity_handle(ent)
                if h not in seen:
                    seen.add(h)
                    result.append(ent)
        except Exception:
            continue
    return result


def find_ad3_entities_indexed(all_line_entities: List[Any], dim_pair: Dict[str, Any], ad1_entities: List[Any], ad2_entities: List[Any], tol: float = AD_TOL) -> List[Any]:
    # DIM 레이어 접두사 또는 ARROW 레이어 모두 포함
    three_dim = _collect_three_point_polylines(all_line_entities, layers=DIM_LAYER_PREFIXES)
    three_arr = [e for e in _collect_three_point_polylines(all_line_entities) if getattr(e.dxf, 'layer', '').upper() == 'ARROW']
    candidates = three_dim + three_arr
    idx = _build_point_index_for_entities(candidates, cell=tol)

    excluded: Set[str] = set(get_entity_handle(e) for e in (ad1_entities + ad2_entities))

    common_point = dim_pair['common_point']
    near: List[Any] = []
    for qp, ent in idx.query(common_point, tol):
        try:
            if distance(qp, common_point) <= tol:
                h = get_entity_handle(ent)
                if h not in excluded:
                    near.append(ent)
        except Exception:
            continue

    # 가장 가까운 한 개만 채택(기존 정책 유지)
    if not near:
        return []

    def min_dist_to_cp(e) -> float:
        try:
            if isinstance(e, LWPolyline):
                pts = list(e.get_points("xy"))
            else:
                pts = [v.dxf.location for v in e.vertices]
            return min(distance(to2d(p), common_point) for p in pts)
        except Exception:
            return 1e9

    near.sort(key=min_dist_to_cp)
    return [near[0]]


def find_ad3_touching_dims_indexed(all_line_entities: List[Any], dim1_ent: Any, dim2_ent: Any, ad1_entities: List[Any], ad2_entities: List[Any], tol: float = TOUCH_TOL) -> List[Any]:
    # ARROW 레이어의 3점 폴리라인만 고려
    arrows = [e for e in _collect_three_point_polylines(all_line_entities) if getattr(e.dxf, 'layer', '').upper() == 'ARROW']
    idx = _build_point_index_for_entities(arrows, cell=tol)

    segs1 = extract_segments(dim1_ent)
    segs2 = extract_segments(dim2_ent)
    if not segs1 or not segs2:
        return []
    d1s, d1e = to2d(segs1[0][0]), to2d(segs1[0][1])
    d2s, d2e = to2d(segs2[0][0]), to2d(segs2[0][1])

    excluded = {get_entity_handle(dim1_ent), get_entity_handle(dim2_ent)}
    excluded.update(get_entity_handle(e) for e in (ad1_entities + ad2_entities))

    # 두 DIM 선 주변의 후보만 검사 (끝점 근방 + 선 주변 스캔)
    result: List[Any] = []
    seen: Set[str] = set()

    probe_points = [d1s, d1e, d2s, d2e]

    for probe in probe_points:
        for qp, ent in idx.query(probe, tol):
            try:
                if distance(qp, probe) > tol:
                    continue
                h = get_entity_handle(ent)
                if h in excluded or h in seen:
                    continue
                # 접촉 여부 판단
                if isinstance(ent, LWPolyline):
                    pts = list(ent.get_points("xy"))
                else:
                    pts = [v.dxf.location for v in ent.vertices]
                pts2 = [to2d(p) for p in pts]
                is_touch = any(
                    point_to_line_distance(pt, d1s, d1e) <= tol or
                    point_to_line_distance(pt, d2s, d2e) <= tol
                    for pt in pts2
                )
                if is_touch:
                    result.append(ent)
                    seen.add(h)
            except Exception:
                continue

    return result


# ─────────────────────────────────────────────────────────────
# ARROW 레이어 1mm 이하 LINE 삭제 후보 탐색(AD3 점 근접)
# ─────────────────────────────────────────────────────────────

def find_arrow_lines_touching_ad3_indexed(all_line_entities: List[Any], ad3_entities: List[Any], tol: float = ARROW_LINE_TOL) -> List[Any]:
    arrow_lines = [e for e in all_line_entities if isinstance(e, Line) and getattr(e.dxf, 'layer', '').upper() == 'ARROW']

    # 라인 끝점 인덱스
    idx = SpatialHash2D(cell=tol)
    lengths: Dict[str, float] = {}
    for ln in arrow_lines:
        try:
            segs = extract_segments(ln)
            if not segs:
                continue
            p0, p1 = segs[0]
            v0, v1 = to2d(p0), to2d(p1)
            ln_len = distance(v0, v1)
            lengths[get_entity_handle(ln)] = ln_len
            idx.insert(v0, ln)
            idx.insert(v1, ln)
        except Exception:
            continue

    # AD3의 모든 점들 수집
    pts_ad3: List[np.ndarray] = []
    for ad3 in ad3_entities:
        try:
            if isinstance(ad3, LWPolyline):
                pts = list(ad3.get_points("xy"))
            else:
                pts = [v.dxf.location for v in ad3.vertices]
            for p in pts:
                pts_ad3.append(to2d(p))
        except Exception:
            continue

    result: List[Any] = []
    seen: Set[str] = set()
    for p in pts_ad3:
        for qp, ln in idx.query(p, tol):
            try:
                if distance(qp, p) > tol:
                    continue
                h = get_entity_handle(ln)
                if h in seen:
                    continue
                if lengths.get(h, 1e9) <= ARROW_LINE_MAXLEN:
                    result.append(ln)
                    seen.add(h)
            except Exception:
                continue
    return result


# ─────────────────────────────────────────────────────────────
# G1 탐색(모든 DIM 사용 엔티티 제외) — 공간 인덱스 활용
# ─────────────────────────────────────────────────────────────

def find_g1_entities_indexed(all_line_entities: List[Any], dim1_ent: Any, dim2_ent: Any, dim_pair: Dict[str, Any], all_used_dim_handles: Set[str], tol: float = 0.2) -> List[Tuple[Any, np.ndarray, np.ndarray]]:
    # 후보: DIM 레이어의 단일 선분 요소들
    candidates: List[Tuple[Any, np.ndarray, np.ndarray]] = []
    for ent in all_line_entities:
        try:
            if not _layer_starts_with(ent, DIM_LAYER_PREFIXES):
                continue
            h = get_entity_handle(ent)
            if h in all_used_dim_handles:
                continue
            segs = extract_segments(ent)
            if len(segs) != 1:
                continue
            p0, p1 = segs[0]
            candidates.append((ent, to2d(p0), to2d(p1)))
        except Exception:
            continue

    # 끝점 인덱스 구축
    idx = SpatialHash2D(cell=tol)
    for c in candidates:
        _, v0, v1 = c
        idx.insert(v0, c)
        idx.insert(v1, c)

    # 유효 영역: CP/각 DIM 공통점/선까지의 거리 기준
    segs1 = extract_segments(dim1_ent)
    segs2 = extract_segments(dim2_ent)
    if not segs1 or not segs2:
        return []
    d1s, d1e = to2d(segs1[0][0]), to2d(segs1[0][1])
    d2s, d2e = to2d(segs2[0][0]), to2d(segs2[0][1])

    cp = dim_pair['common_point']
    search_points = [cp, dim_pair['DIM1_common'], dim_pair['DIM2_common']]

    best: Optional[Tuple[Any, np.ndarray, np.ndarray, float]] = None

    for sp in search_points:
        for qp, cand in idx.query(sp, tol):
            try:
                ent, v0, v1 = cand
                # 가장 가까운 유효성 스코어(작을수록 좋음)
                d_cp = min(distance(v0, cp), distance(v1, cp))
                d1 = min(distance(v0, dim_pair['DIM1_common']), point_to_line_distance(v0, d1s, d1e),
                         distance(v1, dim_pair['DIM1_common']), point_to_line_distance(v1, d1s, d1e))
                d2 = min(distance(v0, dim_pair['DIM2_common']), point_to_line_distance(v0, d2s, d2e),
                         distance(v1, dim_pair['DIM2_common']), point_to_line_distance(v1, d2s, d2e))
                score = min(d_cp, d1, d2)
                if score <= tol:
                    if best is None or score < best[3]:
                        best = (ent, v0, v1, score)
            except Exception:
                continue

    return [(best[0], best[1], best[2])] if best else []


# ─────────────────────────────────────────────────────────────
# CT 텍스트 탐색 — 텍스트 전역 인덱스 + 반경 50mm
# ─────────────────────────────────────────────────────────────

def build_text_index(text_entities: List[Any], cell: float = 10.0) -> SpatialHash2D:
    idx = SpatialHash2D(cell=cell)
    for txt in text_entities:
        try:
            if hasattr(txt.dxf, 'insert') and txt.dxf.insert is not None:
                pos = to2d(txt.dxf.insert)
            elif hasattr(txt.dxf, 'align_point') and txt.dxf.align_point is not None:
                pos = to2d(txt.dxf.align_point)
            else:
                continue
            idx.insert(pos, txt)
        except Exception:
            continue
    return idx


def find_ct_texts_indexed(msp, g1_entities: List[Tuple[Any, np.ndarray, np.ndarray]], text_entities: List[Any], dim_pair: Dict[str, Any], text_index: SpatialHash2D, search_radius: float = CT_SEARCH_RADIUS) -> List[Any]:
    ct_texts: List[Any] = []
    cp = dim_pair['common_point']

    for g1_ent, v0, v1 in g1_entities:
        # CP에서 더 먼 쪽
        sp = v0 if distance(v0, cp) > distance(v1, cp) else v1

        candidates: List[Tuple[float, Any, int, Dict[str, Any]]] = []
        for qp, txt in text_index.query(sp, search_radius):
            try:
                # 위치/반경 필터
                if distance(qp, sp) > search_radius:
                    continue

                # 색상/레이어 필터
                if hasattr(txt.dxf, 'color') and int(getattr(txt.dxf, 'color', 0)) == 1:
                    continue  # RED 제외
                if hasattr(txt.dxf, 'layer') and 'WDNO' in str(txt.dxf.layer).upper():
                    continue

                # 회전 0 근처
                rot = float(getattr(txt.dxf, 'rotation', 0.0))
                if abs(rot) > 0.1:
                    continue

                # 값이 10 초과 정수
                val = txt.plain_text() if hasattr(txt, "plain_text") else txt.dxf.text
                if not str(val).isdigit():
                    continue
                iv = int(val)
                if iv <= 10:
                    continue

                # 폐영역 내부 제외
                if is_enclosed(qp, msp):
                    continue

                tbox = create_tbox(txt)
                if not tbox:
                    continue

                min_d_tbox = min(distance(sp, corner) for corner in tbox['corners'])
                candidates.append((min_d_tbox, txt, iv, tbox))
            except Exception:
                continue

        if candidates:
            candidates.sort(key=lambda x: x[0])
            ct_texts.append(candidates[0][1])
            break

    return ct_texts


# ─────────────────────────────────────────────────────────────
# 각도/텍스트 배치 유틸
# ─────────────────────────────────────────────────────────────

def calculate_chain_direction(dim1_ent, dim2_ent) -> float:
    segs = extract_segments(dim1_ent)
    if segs:
        v0, v1 = to2d(segs[0][0]), to2d(segs[0][1])
        return angle_deg(v0, v1)
    return 0.0


def calculate_text_angle(chain_dir: float) -> float:
    ang = chain_dir % 360.0
    if abs(ang - 90.0) <= ANGLE_TOLERANCE or abs(ang - 270.0) <= ANGLE_TOLERANCE:
        return 90.0
    if 90.0 < ang < 270.0:
        return (ang + 180.0) % 360.0
    return ang


def find_parallel_polylines_for_ang(msp, dim_pair: Dict[str, Any], tol: float = 0.5) -> float:
    dim1_opp = dim_pair['DIM1_opposite']
    dim2_opp = dim_pair['DIM2_opposite']

    excl = {get_entity_handle(dim_pair['DIM1']), get_entity_handle(dim_pair['DIM2'])}

    # 후보(정확히 2점) 수집 및 인덱스
    cands: List[Tuple[Any, np.ndarray, np.ndarray]] = []
    for ent in msp.query("LWPOLYLINE POLYLINE"):
        try:
            if not _layer_starts_with(ent, DIM_LAYER_PREFIXES):
                continue
            if get_entity_handle(ent) in excl:
                continue
            if isinstance(ent, LWPolyline):
                pts = list(ent.get_points("xy"))
            else:
                pts = [v.dxf.location for v in ent.vertices]
            if len(pts) != 2:
                continue
            v0, v1 = to2d(pts[0]), to2d(pts[1])
            cands.append((ent, v0, v1))
        except Exception:
            continue

    idx = SpatialHash2D(cell=tol)
    for ent, v0, v1 in cands:
        idx.insert(v0, (ent, v0, v1))
        idx.insert(v1, (ent, v0, v1))

    search_points = [dim1_opp, dim2_opp]
    best: Optional[Tuple[Any, float, float]] = None  # (ent, angle, dist)

    for sp in search_points:
        for qp, payload in idx.query(sp, tol):
            try:
                ent, v0, v1 = payload
                d = min(distance(v0, sp), distance(v1, sp))
                if d > tol:
                    continue
                ang = angle_deg(v0, v1)
                if best is None or d < best[2]:
                    best = (ent, ang, d)
            except Exception:
                continue

    return 0.0 if best is None else float(best[1])


def find_and_color_ct1_polylines(msp, dim_pair: Dict[str, Any], tol: float = 0.5) -> None:
    d1c = dim_pair['DIM1_common']
    d1o = dim_pair['DIM1_opposite']
    excl = {get_entity_handle(dim_pair['DIM1']), get_entity_handle(dim_pair['DIM2'])}

    cands: List[Tuple[Any, np.ndarray, np.ndarray]] = []
    for ent in msp.query("LWPOLYLINE POLYLINE"):
        try:
            if not _layer_starts_with(ent, DIM_LAYER_PREFIXES):
                continue
            if get_entity_handle(ent) in excl:
                continue
            if isinstance(ent, LWPolyline):
                pts = list(ent.get_points("xy"))
            else:
                pts = [v.dxf.location for v in ent.vertices]
            if len(pts) != 2:
                continue
            v0, v1 = to2d(pts[0]), to2d(pts[1])
            cands.append((ent, v0, v1))
        except Exception:
            continue

    idx = SpatialHash2D(cell=tol)
    for ent, v0, v1 in cands:
        idx.insert(v0, ent)
        idx.insert(v1, ent)

    found: List[Tuple[Any, float]] = []
    for sp in (d1c, d1o):
        for qp, ent in idx.query(sp, tol):
            try:
                if distance(qp, sp) <= tol:
                    found.append((ent, distance(qp, sp)))
            except Exception:
                continue

    if found:
        found.sort(key=lambda x: x[1])
        ent = found[0][0]
        try:
            ent.dxf.color = 7  # WHITE
        except Exception:
            pass


def check_ct_dim_interference(ct_pos: np.ndarray, text_length: float, text_height: float,
                              d1s: np.ndarray, d1e: np.ndarray, d2s: np.ndarray, d2e: np.ndarray,
                              window_radius: float = CT_SEARCH_RADIUS) -> Tuple[bool, float, float]:
    # ±50mm 윈도우 내에서만 간섭 검사
    d1 = point_to_line_distance(ct_pos, d1s, d1e)
    d2 = point_to_line_distance(ct_pos, d2s, d2e)
    if min(d1, d2) > window_radius:
        return False, d1, d2

    thr = text_height * 0.6
    return (d1 < thr or d2 < thr), d1, d2


def process_ct_text(txt, g1_ent, v0, v1, text_angle: float, cp: np.ndarray, dim_pair: Dict[str, Any], msp) -> bool:
    # 위치
    try:
        if hasattr(txt.dxf, 'insert') and txt.dxf.insert is not None:
            cur = to2d(txt.dxf.insert)
        elif hasattr(txt.dxf, 'align_point') and txt.dxf.align_point is not None:
            cur = to2d(txt.dxf.align_point)
        else:
            return False
    except Exception:
        return False

    # DIM 선 준비
    segs1 = extract_segments(dim_pair['DIM1'])
    segs2 = extract_segments(dim_pair['DIM2'])
    if not segs1 or not segs2:
        return False
    d1s, d1e = to2d(segs1[0][0]), to2d(segs1[0][1])
    d2s, d2e = to2d(segs2[0][0]), to2d(segs2[0][1])

    dim_len = float(dim_pair['length'])
    is_ct1 = 1.2 <= dim_len <= 1.5

    if is_ct1:
        final_ang = 0.0
        find_and_color_ct1_polylines(msp, dim_pair)
    else:
        use_ang = 1.5 <= dim_len <= 2.0
        if use_ang:
            final_ang = find_parallel_polylines_for_ang(msp, dim_pair)
        else:
            final_ang = text_angle

    tlen, th = get_text_dimensions(txt)
    half = tlen / 2.0

    ang_rad = math.radians(final_ang)
    dir_vec = np.array([math.cos(ang_rad), math.sin(ang_rad)])
    perp = np.array([-math.sin(ang_rad), math.cos(ang_rad)])

    # 1) 중심 CP 정렬
    cp_centered = cp - dir_vec * half

    # 2) CP -> 텍스트 중심 0.6mm 이동
    cur_center = cp_centered + dir_vec * half
    v = cur_center - cp
    vlen = float(np.linalg.norm(v))
    if vlen > 0:
        step = v / vlen * 0.6
    else:
        step = dir_vec * 0.6
    inter = cp_centered + step

    # 3) 간섭 검사 (±50mm 윈도우내)
    clash, _, _ = check_ct_dim_interference(inter, tlen, th, d1s, d1e, d2s, d2e)
    final = inter

    if clash:
        # 4) 반대방향 1.2mm 이동
        if vlen > 0:
            cand = inter - (v / vlen) * 1.2
        else:
            cand = inter - dir_vec * 1.2
        clash2, _, _ = check_ct_dim_interference(cand, tlen, th, d1s, d1e, d2s, d2e)
        final = cand if not clash2 else inter

        # 5) 여전히 간섭이면 좌우/위아래 탐색(최대 8회)
        if clash2:
            positions: List[np.ndarray] = []
            for off in [1.0, -1.0, 2.0, -2.0, 3.0, -3.0, 4.0, -4.0]:
                positions.append(cand + perp * off)
            for off in [1.0, -1.0, 2.0, -2.0, 3.0, -3.0, 4.0, -4.0]:
                positions.append(cand + dir_vec * off)
            for p in positions:
                ok, _, _ = check_ct_dim_interference(p, tlen, th, d1s, d1e, d2s, d2e)
                if not ok:
                    final = p
                    break

    # 6) 최종 위치에서 CP 방향으로 2mm 추가 이동
    dvec = cp - final
    dlen = float(np.linalg.norm(dvec))
    if dlen > 0:
        final = final + (dvec / dlen) * 2.0

    # 7) DIM1 기울기 기준 -2mm 평행 이동(요구사항 유지)
    segs1 = extract_segments(dim_pair['DIM1'])
    if segs1:
        d1s2, d1e2 = to2d(segs1[0][0]), to2d(segs1[0][1])
        vec = d1e2 - d1s2
        vecl = float(np.linalg.norm(vec))
        if vecl > 0:
            unit = vec / vecl
            proj = float(np.dot(cp - final, unit))
            move_dir = unit if proj > 0 else -unit
            final = final + move_dir * (-2.0)  # 기존 코드 유지

    # 적용
    try:
        if txt.dxftype() == "TEXT":
            old_z = float(txt.dxf.insert[2]) if len(txt.dxf.insert) > 2 else 0.0
            txt.dxf.insert = (float(final[0]), float(final[1]), old_z)
            txt.dxf.halign = 0
            txt.dxf.valign = 0
            try:
                if hasattr(txt.dxf, 'align_point'):
                    delattr(txt.dxf, 'align_point')
            except Exception:
                pass
            txt.dxf.rotation = float(final_ang)
        elif txt.dxftype() == "MTEXT":
            old_z = float(txt.dxf.insert[2]) if len(txt.dxf.insert) > 2 else 0.0
            txt.dxf.insert = (float(final[0]), float(final[1]), old_z)
            txt.dxf.attachment_point = 1
            txt.dxf.rotation = float(final_ang)
    except Exception:
        return is_ct1

    return is_ct1


# ─────────────────────────────────────────────────────────────
# 메인 시스템 처리(인덱스 적용)
# ─────────────────────────────────────────────────────────────

def process_dimension_system(msp, text_entities: List[Any]):
    all_line_entities = list(msp.query("LINE LWPOLYLINE POLYLINE"))

    # DIM 쌍 찾기
    dim_pairs, overlapped_entities = find_dim_pairs_indexed(all_line_entities)

    all_processed: List[Any] = []
    all_processed.extend(overlapped_entities)

    ct_texts: List[Any] = []
    ct1_texts: List[Any] = []
    g1_to_delete: List[Any] = []
    ad3_to_delete: List[Any] = []
    arrow_lines_to_delete: List[Any] = []

    protected_handles: Set[str] = set()
    protected_entities: List[Any] = []
    ad1ad2_all: List[Any] = []

    # 모든 DIM 엔티티 핸들(후속 제외용)
    used_dim_handles: Set[str] = set()
    for dp in dim_pairs:
        used_dim_handles.add(get_entity_handle(dp['DIM1']))
        used_dim_handles.add(get_entity_handle(dp['DIM2']))

    # 텍스트 인덱스(반경 질의)
    text_index = build_text_index(text_entities, cell=10.0)

    all_dim_far_points: List[np.ndarray] = []

    for dp in dim_pairs:
        d1 = dp['DIM1']
        d2 = dp['DIM2']
        d1o = dp['DIM1_opposite']
        d2o = dp['DIM2_opposite']
        d1c = dp['DIM1_common']
        d2c = dp['DIM2_common']

        # 보호 설정 + 색상 표시
        protected_handles.update({get_entity_handle(d1), get_entity_handle(d2)})
        protected_entities.extend([d1, d2])
        try:
            d1.dxf.color = 3
            d2.dxf.color = 3
        except Exception:
            pass
        all_processed.extend([d1, d2])

        # 체인 방향/텍스트 각도
        chain_dir = calculate_chain_direction(d1, d2)
        text_ang = calculate_text_angle(chain_dir)

        # AD1/AD2 (공간 인덱스)
        ad1_list = find_arrow_entities_indexed(all_line_entities, d1o, tol=AD_TOL)
        ad2_list = find_arrow_entities_indexed(all_line_entities, d2o, tol=AD_TOL)

        for e in ad1_list + ad2_list:
            protected_handles.add(get_entity_handle(e))
            protected_entities.append(e)
            ad1ad2_all.append(e)
            try:
                e.dxf.color = 2
            except Exception:
                pass
            all_processed.append(e)

        # AD3 (CP 근방)
        ad3_list = find_ad3_entities_indexed(all_line_entities, dp, ad1_list, ad2_list, tol=AD_TOL)

        # G1 (모든 DIM 제외 후 탐색)
        g1_list = find_g1_entities_indexed(all_line_entities, d1, d2, dp, used_dim_handles, tol=0.2)

        # CT 탐색/처리
        ct_found = False
        cts = find_ct_texts_indexed(msp, g1_list, text_entities, dp, text_index, search_radius=CT_SEARCH_RADIUS)
        for g1_ent, v0, v1 in g1_list:
            try:
                g1_ent.dxf.color = 1
            except Exception:
                pass
            all_processed.append(g1_ent)
            g1_to_delete.append(g1_ent)

        if cts:
            ct_found = True
            for ct in cts:
                try:
                    ct.dxf.color = 2
                except Exception:
                    pass
                is_ct1 = process_ct_text(ct, g1_list[0][0], g1_list[0][1], g1_list[0][2], text_ang, dp['common_point'], dp, msp)
                if is_ct1:
                    ct1_texts.append(ct)
                else:
                    ct_texts.append(ct)

        # CT가 있을 때만 AD3 삭제 후보 지정
        if ct_found:
            for ad3 in ad3_list:
                h = get_entity_handle(ad3)
                if h not in protected_handles and ad3 not in ad1ad2_all and ad3 not in protected_entities:
                    try:
                        ad3.dxf.color = 4
                    except Exception:
                        pass
                    all_processed.append(ad3)
                    ad3_to_delete.append(ad3)
                else:
                    try:
                        ad3.dxf.color = 2
                    except Exception:
                        pass
                    all_processed.append(ad3)
        else:
            for ad3 in ad3_list:
                try:
                    ad3.dxf.color = 2
                except Exception:
                    pass
                all_processed.append(ad3)

        # DIM 선분에 접하는 AD3 (ARROW, 0.2mm)
        touching_ad3 = find_ad3_touching_dims_indexed(all_line_entities, d1, d2, ad1_list, ad2_list, tol=TOUCH_TOL)
        for e in touching_ad3:
            h = get_entity_handle(e)
            if h not in protected_handles and e not in ad3_to_delete and e not in ad1ad2_all and e not in protected_entities:
                try:
                    e.dxf.color = 4
                except Exception:
                    pass
                all_processed.append(e)
                ad3_to_delete.append(e)

        all_dim_far_points.extend([d1o, d2o])

    # AD1/AD2 보호: ARROW 레이어에서 DIM 반대편 끝점 근처 0.5mm 이내는 보호
    for ent in all_line_entities:
        try:
            if getattr(ent.dxf, 'layer', '').upper() != 'ARROW':
                continue
            if isinstance(ent, LWPolyline):
                pts = list(ent.get_points("xy"))
            else:
                if not isinstance(ent, Polyline):
                    continue
                pts = [v.dxf.location for v in ent.vertices]
            pts2 = [to2d(p) for p in pts]
            for p in pts2:
                if any(distance(p, q) <= 0.5 for q in all_dim_far_points):
                    protected_handles.add(get_entity_handle(ent))
                    break
        except Exception:
            continue

    # AD3 점에 접하는 ARROW Line (<=1mm)
    arrow_lines = find_arrow_lines_touching_ad3_indexed(all_line_entities, ad3_to_delete, tol=ARROW_LINE_TOL)
    for ln in arrow_lines:
        h = get_entity_handle(ln)
        if h not in protected_handles and ln not in protected_entities:
            try:
                ln.dxf.color = 4
            except Exception:
                pass
            all_processed.append(ln)
            arrow_lines_to_delete.append(ln)

    # 실제 삭제 수행(보호 제외)
    for e in ad3_to_delete:
        try:
            h = get_entity_handle(e)
            if h not in protected_handles and e not in protected_entities and e not in ad1ad2_all:
                msp.delete_entity(e)
        except Exception:
            pass

    for g1 in g1_to_delete:
        try:
            if get_entity_handle(g1) not in protected_handles:
                msp.delete_entity(g1)
        except Exception:
            pass

    for ln in arrow_lines_to_delete:
        try:
            if get_entity_handle(ln) not in protected_handles and ln not in protected_entities:
                msp.delete_entity(ln)
        except Exception:
            pass

    return all_processed, ct_texts, ct1_texts


# ─────────────────────────────────────────────────────────────
# 파이프라인/파일 처리
# ─────────────────────────────────────────────────────────────

def auto_align_dxf(input_dxf: str, output_dxf: str) -> bool:
    if not os.path.isfile(input_dxf):
        return False
    try:
        clear_tbox_cache()
        doc = ezdxf.readfile(input_dxf)
        msp = doc.modelspace()

        texts = list(msp.query("TEXT MTEXT"))
        process_dimension_system(msp, texts)

        doc.saveas(output_dxf)
        clear_tbox_cache()
        return True
    except Exception:
        clear_tbox_cache()
        return False


# ─────────────────────────────────────────────────────────────
# GUI: 파일 선택/프로그레스 (원문 유지, 불필요 로그 제거)
# ─────────────────────────────────────────────────────────────

def select_dxf_files() -> List[str]:
    root = tk.Tk()
    root.withdraw()
    file_paths = filedialog.askopenfilenames(
        title="DXF 파일을 선택하세요 (여러 개 선택 가능)",
        filetypes=[("DXF files", "*.dxf"), ("All files", "*.*")],
        multiple=True,
    )
    root.destroy()
    return list(file_paths)


def show_progress_window(total_files: int):
    win = tk.Tk()
    win.title("DXF 처리 진행 상황")
    win.geometry("500x150")
    win.resizable(False, False)
    try:
        win.eval('tk::PlaceWindow . center')
    except Exception:
        pass

    label = tk.Label(win, text="DXF 파일을 처리 중입니다...", font=("Arial", 12))
    label.pack(pady=10)

    file_label = tk.Label(win, text="", font=("Arial", 10), fg="blue")
    file_label.pack(pady=5)

    var = tk.DoubleVar()
    bar = ttk.Progressbar(win, variable=var, maximum=total_files, length=400, mode='determinate')
    bar.pack(pady=10)

    text = tk.Label(win, text=f"0 / {total_files}", font=("Arial", 10))
    text.pack()

    win.update()
    return win, var, file_label, text


def update_progress(win, var, file_label, text, cur: int, total: int, fname: str):
    if win and win.winfo_exists():
        var.set(cur)
        try:
            file_label.config(text=f"처리 중: {os.path.basename(fname)}")
            text.config(text=f"{cur} / {total}")
        except Exception:
            pass
        win.update()


def close_progress_window(win):
    if win and win.winfo_exists():
        win.destroy()


def process_multiple_files():
    files = select_dxf_files()
    if not files:
        return

    win, var, file_label, text = show_progress_window(len(files))
    success = 0
    failed: List[str] = []
    try:
        for i, input_file in enumerate(files):
            update_progress(win, var, file_label, text, i, len(files), input_file)
            d = os.path.dirname(input_file)
            name = os.path.splitext(os.path.basename(input_file))[0]
            out = os.path.join(d, f"{name}_DIM.dxf")
            if auto_align_dxf(input_file, out):
                success += 1
            else:
                failed.append(os.path.basename(input_file))
        update_progress(win, var, file_label, text, len(files), len(files), "완료")
    finally:
        close_progress_window(win)


if __name__ == "__main__":
    if len(sys.argv) == 3:
        auto_align_dxf(sys.argv[1], sys.argv[2])
    else:
        process_multiple_files()
