# -*- coding: utf-8 -*-
"""
DXF 자동 편집기 - TEETEXTEDIT (ezdxf) - 개선된 버전

주요 개선사항:
1. TEXT BOX 높이를 2.5mm로 고정 (TEXT 높이 2.2mm + 위아래 여백 0.15mm씩)
2. TEXT 회전 각도를 BOX에도 적용
3. 연속 라인 찾기 로직을 적용한 TOTEE 클러스터 확장
"""

import math
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import List, Tuple, Optional, Dict, Set

import ezdxf
from ezdxf.entities import LWPolyline, Polyline, Line, Text, MText
from ezdxf.math import Vec2, Vec3

# ---------------- GUI (파일 선택) ----------------
try:
    import tkinter as tk
    from tkinter import filedialog
except Exception:
    tk = None

# ---------------- 파라미터 ----------------
ANG_TOL_DEG = 3.0      # 같은 기울기 허용각(°)
TP_JOIN_TOL = 0.2      # TP 결합 거리(mm)
TP_TO_AD1_RAD = 0.3    # TP→AD1 탐색 반경(mm)
AD1_MAX_LEN = 5.0      # AD1 길이 상한(mm)
AD_NEAR_TOL = 0.1      # AD1 인접 탐색 반경(mm)
ARROW_MAX_LEN = 1.0    # AD2(Line) 길이 상한(mm)

AP2_WIN_X_NEG = 40.0   # AP2 검색 X-
AP2_WIN_X_POS = 15.0   # AP2 검색 X+
AP2_WIN_Y     = 7.0    # AP2 검색 |Y|

T1_ROT_TOL    = 2.0    # T1 회전≈0 판정 허용(도)

# ---- T2 탐색 파라미터(유연) ----
T2_Y_MIN      = 4.0    # T1 아래 최소 거리
T2_Y_MAX      = 10.0   # T1 아래 최대 거리
T2_X_HALF     = 30.0   # 좌우 허용치
T2_Y_FALLBACK_MAX = 14.0
T2_X_FALLBACK     = 45.0

TYP_DY        = 6.2    # '(TYP.)' 출력 오프셋 (아래로)

# TEXT BOX 파라미터
TEXT_BOX_HEIGHT = 2.5  # TEXT 높이 2.2mm + 위아래 여백 0.15mm씩

# 레이어명
LAYER_AD1 = "AD1"
LAYER_AD2 = "AD2"
LAYER_AD3 = "AD3"

# ---------------- 텍스트 정규화/정규식 ----------------
def clean_text(s: str) -> str:
    """MTEXT 제어코드 제거/정리."""
    if not s:
        return ""
    s = s.replace("\\P", " ")
    s = re.sub(r"\\[A-Za-z]", "", s)  # \L, \O 등 제거
    s = s.replace("{", "").replace("}", "")
    return s.strip()

# 'EL' 또는 'FL' 토큰(독립 단어) 탐지
RE_ELFL = re.compile(r"\b(?:EL|FL)\b", re.IGNORECASE)

# (옵션) 값까지 추출: 'EL 12.3', 'FL.-100' 등
RE_ELFL_WITH_VALUE = re.compile(r"(?i)\b(EL|FL)\b[^\d\-]*(-?\d+(?:\.\d+)?)")

# ---------------- 유틸 ----------------
def safe_has_dxf(e) -> bool:
    return (e is not None) and hasattr(e, "dxf") and (getattr(e, "dxf") is not None)

def dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0]-b[0], a[1]-b[1])

def deg_between(v1: Vec2, v2: Vec2) -> float:
    if v1.magnitude == 0 or v2.magnitude == 0:
        return 180.0
    ang = math.degrees(v1.angle_between(v2))
    return min(ang, abs(180.0 - ang))  # 평행/반평행 허용

def is_same_slope(v1: Vec2, v2: Vec2, tol_deg: float = ANG_TOL_DEG) -> bool:
    return deg_between(v1, v2) <= tol_deg

def _iter_poly_vertices(pl):
    """Polyline.vertices: 함수/리스트 양쪽 호환."""
    vattr = getattr(pl, "vertices", None)
    if vattr is None:
        return []
    try:
        return list(vattr()) if callable(vattr) else list(vattr)
    except Exception:
        return []

def get_poly_points(e) -> List[Tuple[float, float]]:
    """LWPolyline/Polyline 꼭지점 2D 좌표 리스트로 안전 추출."""
    if isinstance(e, LWPolyline):
        try:
            return [(p[0], p[1]) for p in e.get_points("xy")]
        except Exception:
            pts = []
            try:
                for p in e:
                    x = getattr(p.dxf, "x", None)
                    y = getattr(p.dxf, "y", None)
                    if x is not None and y is not None:
                        pts.append((float(x), float(y)))
            except Exception:
                pass
            return pts

    if isinstance(e, Polyline):
        pts = []
        for v in _iter_poly_vertices(e):
            loc = getattr(v.dxf, "location", None)
            if loc is not None:
                pts.append((float(loc.x), float(loc.y))); continue
            if hasattr(v.dxf, "point"):
                p = v.dxf.point;  pts.append((float(p.x), float(p.y))); continue
            if hasattr(v.dxf, "start"):
                p = v.dxf.start;  pts.append((float(p.x), float(p.y))); continue
            x = getattr(v.dxf, "x", None); y = getattr(v.dxf, "y", None)
            if x is not None and y is not None:
                pts.append((float(x), float(y)))
        return pts

    return []

def poly_is_closed(e) -> bool:
    try:
        if isinstance(e, LWPolyline): return bool(e.closed)
        if isinstance(e, Polyline):   return bool(e.is_closed)
    except Exception:
        return False
    return False

def poly_length(e) -> float:
    pts = get_poly_points(e)
    if len(pts) < 2: return 0.0
    L = sum(dist(pts[i], pts[i+1]) for i in range(len(pts)-1))
    if poly_is_closed(e): L += dist(pts[-1], pts[0])
    return L

def end_vectors(e):
    """시작/끝 세그먼트 벡터 + 시작/끝점 좌표."""
    pts = get_poly_points(e)
    if len(pts) < 2: return None, None, None, None
    p0, p1   = Vec2(pts[0]),  Vec2(pts[1])
    pn_1, pn = Vec2(pts[-2]), Vec2(pts[-1])
    return (p1-p0), (pn-pn_1), (pts[0][0], pts[0][1]), (pts[-1][0], pts[-1][1])

def nearest_end_info(e, ref: Tuple[float, float]):
    v_start, v_end, p_start, p_end = end_vectors(e)
    if p_start is None: return None
    d0, d1 = dist(p_start, ref), dist(p_end, ref)
    return {"end":"start","pt":p_start,"vec":v_start} if d0<=d1 else {"end":"end","pt":p_end,"vec":v_end}

def within_rect(pt: Tuple[float,float], x0: float, x1: float, y0: float, y1: float) -> bool:
    return (x0 <= pt[0] <= x1) and (y0 <= pt[1] <= y1)

def text_string(e) -> str:
    if isinstance(e, Text):  return e.dxf.text or ""
    if isinstance(e, MText): return e.text or ""
    return ""

def text_insert_point(e) -> Tuple[float, float]:
    if isinstance(e, (Text, MText)):
        p = e.dxf.insert; return (p.x, p.y)
    return (0.0, 0.0)

def text_rotation(e) -> float:
    try:
        return float(e.dxf.get("rotation", 0.0) or 0.0)
    except Exception:
        return 0.0

def ensure_layer(doc, name: str):
    try:
        if name not in doc.layers: doc.layers.add(name)
    except Exception:
        pass

def delete_safe(msp, e):
    try:
        if e is not None: msp.delete_entity(e)
    except Exception:
        pass

def set_layer_safe(e, name: str):
    try:
        e.dxf.layer = name
    except Exception:
        pass

def copy_text_props(src, dst_text):
    """src(TEXT/MTEXT)의 스타일/높이/회전/레이어를 TEXT에 최대한 복사."""
    try:
        dst_text.dxf.layer = getattr(src.dxf, "layer", dst_text.dxf.layer)
        if isinstance(src, Text):
            if hasattr(src.dxf, "height"):   dst_text.dxf.height = src.dxf.height
            dst_text.dxf.rotation = float(getattr(src.dxf, "rotation", 0.0) or 0.0)
            if hasattr(src.dxf, "style"):    dst_text.dxf.style = src.dxf.style
            if hasattr(src.dxf, "width"):    dst_text.dxf.width = src.dxf.width
        elif isinstance(src, MText):
            try:    dst_text.dxf.height = float(getattr(src.dxf, "char_height", 2.5) or 2.5)
            except: pass
            try:    dst_text.dxf.rotation = float(getattr(src.dxf, "rotation", 0.0) or 0.0)
            except: pass
            if hasattr(src.dxf, "style"):    dst_text.dxf.style = src.dxf.style
    except Exception:
        pass

def add_typ_text(msp, ref_text, delta_y: float):
    ip = text_insert_point(ref_text)
    new_t = msp.add_text("(TYP.)", dxfattribs={"layer": getattr(ref_text.dxf, "layer", "0")})
    copy_text_props(ref_text, new_t)
    new_t.dxf.insert = (ip[0], ip[1] - delta_y)
    return new_t

# ---------------- 개선된 TEXT BOX 계산 ----------------
def get_text_bbox_with_rotation(text, box_height=TEXT_BOX_HEIGHT):
    """
    TEXT 엔티티의 경계 상자 계산 (회전 고려)
    BOX 높이는 고정값 2.5mm 사용
    
    Returns:
        dict: BOX 정보 {'corners': [(x,y),...], 'center': (x,y), 'rotation': angle}
    """
    if not text or not safe_has_dxf(text):
        return None
        
    # TEXT 위치와 속성
    pos = text_insert_point(text)
    rotation = text_rotation(text)  # 도 단위
    text_str = text_string(text)
    
    # TEXT 높이와 길이 계산
    height = getattr(text.dxf, 'height', 2.2)
    text_len = len(text_str) * height * 0.8  # 대략적인 텍스트 길이
    
    # 회전되지 않은 상태의 BOX 코너 (원점 기준)
    # TEXT는 일반적으로 왼쪽 하단이 기준점
    corners_local = [
        (0, -0.15),  # 왼쪽 하단
        (text_len, -0.15),  # 오른쪽 하단
        (text_len, height + 0.15),  # 오른쪽 상단
        (0, height + 0.15)  # 왼쪽 상단
    ]
    
    # 회전 변환 적용
    rad = math.radians(rotation)
    cos_r = math.cos(rad)
    sin_r = math.sin(rad)
    
    corners_world = []
    for x, y in corners_local:
        # 회전 변환
        x_rot = x * cos_r - y * sin_r
        y_rot = x * sin_r + y * cos_r
        # 위치 이동
        corners_world.append((pos[0] + x_rot, pos[1] + y_rot))
    
    # 중심점 계산
    cx = sum(p[0] for p in corners_world) / 4
    cy = sum(p[1] for p in corners_world) / 4
    
    return {
        'corners': corners_world,
        'center': (cx, cy),
        'rotation': rotation,
        'width': text_len,
        'height': box_height
    }

# ---------------- 연속 라인 찾기 클래스 ----------------
class ContinuousPolylineFinder:
    """연속된 폴리라인을 찾는 클래스 (A1LineFinder 방식 적용)"""
    
    def __init__(self):
        self.used_entities = set()  # 이미 사용된 엔티티 추적
    
    def get_distance(self, p1, p2):
        """두 점 사이의 거리 계산"""
        return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)
    
    def get_line_angle(self, start, end):
        """라인의 각도를 계산 (0~360도)"""
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        
        # 라디안을 도로 변환
        angle = math.atan2(dy, dx) * 180 / math.pi
        
        # 0~360도로 정규화
        if angle < 0:
            angle += 360
            
        return angle
    
    def get_polyline_end_angle(self, poly, which_end='start'):
        """폴리라인의 시작 또는 끝 부분의 각도 계산"""
        pts = get_poly_points(poly)
        if len(pts) < 2:
            return None
            
        if which_end == 'start':
            return self.get_line_angle(pts[0], pts[1])
        else:  # end
            return self.get_line_angle(pts[-2], pts[-1])
    
    def find_continuous_polylines(self, polys, base_poly, max_distance=TP_JOIN_TOL, 
                                angle_tolerance=ANG_TOL_DEG, target_layers=None):
        """기준 폴리라인과 연속된 폴리라인들을 찾기"""
        if target_layers is None:
            target_layers = ["TEE", "PIPE"]
            
        continuous_polys = []
        
        # 기준 폴리라인의 끝점들
        base_pts = get_poly_points(base_poly)
        if len(base_pts) < 2:
            return continuous_polys
            
        # 방문한 폴리라인 추적
        visited = set([base_poly.dxf.handle])
        
        # 재귀적으로 연속된 폴리라인 찾기
        self._find_continuous_from_endpoints(
            polys, base_poly, max_distance, 
            angle_tolerance, continuous_polys, visited,
            target_layers
        )
        
        return continuous_polys
    
    def _find_continuous_from_endpoints(self, polys, current_poly, max_distance, 
                                      angle_tolerance, continuous_polys, visited,
                                      target_layers):
        """현재 폴리라인의 양 끝점에서 연속된 폴리라인 찾기 (재귀)"""
        current_pts = get_poly_points(current_poly)
        if len(current_pts) < 2:
            return
            
        current_start = current_pts[0]
        current_end = current_pts[-1]
        
        # 현재 폴리라인의 시작과 끝 각도
        start_angle = self.get_polyline_end_angle(current_poly, 'start')
        end_angle = self.get_polyline_end_angle(current_poly, 'end')
        
        for cand_poly in polys:
            if not safe_has_dxf(cand_poly):
                continue
                
            ch = cand_poly.dxf.handle
            if ch in visited or ch in self.used_entities:
                continue
                
            # 레이어 확인
            if not any(layer_has(cand_poly, layer) for layer in target_layers):
                continue
                
            cand_pts = get_poly_points(cand_poly)
            if len(cand_pts) < 2:
                continue
                
            cand_start = cand_pts[0]
            cand_end = cand_pts[-1]
            
            # 연결 가능한 경우들 확인
            connections = [
                (current_end, cand_start, end_angle, self.get_polyline_end_angle(cand_poly, 'start')),
                (current_end, cand_end, end_angle, self.get_polyline_end_angle(cand_poly, 'end')),
                (current_start, cand_start, start_angle, self.get_polyline_end_angle(cand_poly, 'start')),
                (current_start, cand_end, start_angle, self.get_polyline_end_angle(cand_poly, 'end'))
            ]
            
            for point1, point2, angle1, angle2 in connections:
                if angle1 is None or angle2 is None:
                    continue
                    
                dist = self.get_distance(point1, point2)
                if dist <= max_distance:
                    # 각도 차이 계산
                    angle_diff = abs(angle1 - angle2)
                    if angle_diff > 180:
                        angle_diff = 360 - angle_diff
                    
                    # 반대 방향(180도 차이)도 같은 기울기로 간주
                    if angle_diff > 90:
                        angle_diff = 180 - angle_diff
                    
                    if angle_diff <= angle_tolerance:
                        # 연속된 폴리라인으로 추가
                        continuous_polys.append(cand_poly)
                        visited.add(ch)
                        
                        # 재귀적으로 이 폴리라인에서 또 연속된 폴리라인 찾기
                        self._find_continuous_from_endpoints(
                            polys, cand_poly, max_distance, 
                            angle_tolerance, continuous_polys, visited,
                            target_layers
                        )
                        break

def layer_has(e, key: str) -> bool:
    try:
        return key.upper() in (e.dxf.layer or "").upper()
    except Exception:
        return False

# ---------------- 개선된 TOTEE 클러스터 확장 ----------------
def expand_totee_clusters_improved(polys: List[object]):
    """
    연속 라인 찾기 로직을 적용한 TOTEE 클러스터 확장
    """
    tee_seeds = [p for p in polys if safe_has_dxf(p) and layer_has(p, "TEE")]
    
    finder = ContinuousPolylineFinder()
    clusters = []
    
    for seed in tee_seeds:
        if seed.dxf.handle in finder.used_entities:
            continue
            
        # 이 TEE를 시작으로 연속된 폴리라인들 찾기
        continuous = finder.find_continuous_polylines(
            polys, seed, 
            max_distance=TP_JOIN_TOL,
            angle_tolerance=ANG_TOL_DEG,
            target_layers=["TEE", "PIPE"]
        )
        
        # 클러스터 구성
        cluster_handles = set([seed.dxf.handle])
        cluster_handles.update(p.dxf.handle for p in continuous)
        
        # 사용된 엔티티로 표시
        finder.used_entities.update(cluster_handles)
        
        # TP (끝점) 수집
        tps = []
        seen = set()
        
        all_polys = [seed] + continuous
        for poly in all_polys:
            for pt in endpoints_of_poly(poly):
                key = (round(pt[0], 4), round(pt[1], 4))
                if key not in seen:
                    seen.add(key)
                    tps.append(pt)
        
        clusters.append({"handles": cluster_handles, "tps": tps})
    
    return clusters

def endpoints_of_poly(e) -> List[Tuple[float,float]]:
    pts = get_poly_points(e)
    if len(pts) < 2: return []
    return [pts[0], pts[-1]]

# ---------------- 탐색 보조 ----------------
def find_ad1_near_tp(polys: List[object], tp: Tuple[float,float]) -> Optional[object]:
    for p in polys:
        if not safe_has_dxf(p): continue
        if not layer_has(p, "GT_1"): continue
        pts = get_poly_points(p)
        if len(pts) != 3: continue
        if poly_length(p) > AD1_MAX_LEN: continue
        if any(dist(tp, v) <= TP_TO_AD1_RAD for v in pts):
            return p
    return None

def find_ad2_around_ad1(lines: List[Line], ad1) -> Optional[Line]:
    pts = get_poly_points(ad1)
    for ln in lines:
        if not safe_has_dxf(ln): continue
        if not layer_has(ln, "ARROW"): continue
        p0 = (ln.dxf.start.x, ln.dxf.start.y)
        p1 = (ln.dxf.end.x,   ln.dxf.end.y)
        if dist(p0, p1) > ARROW_MAX_LEN: continue
        if any(dist(p0, v) <= AD_NEAR_TOL or dist(p1, v) <= AD_NEAR_TOL for v in pts):
            return ln
    return None

def find_ad3_around_ad1(polys: List[object], ad1) -> Optional[object]:
    pts = get_poly_points(ad1)
    for p in polys:
        if not safe_has_dxf(p): continue
        if not layer_has(p, "PL2"): continue
        vts = get_poly_points(p)
        if any(dist(v, w) <= AD_NEAR_TOL for v in pts for w in vts):
            return p
    return None

def ap1_ap2_from_ad3(ad3, ad1) -> Tuple[Optional[Tuple[float,float]], Optional[Tuple[float,float]]]:
    if ad3 is None or ad1 is None: return None, None
    pts3 = get_poly_points(ad3)
    if not pts3: return None, None
    pts1 = get_poly_points(ad1)
    cx = sum(p[0] for p in pts1)/len(pts1); cy = sum(p[1] for p in pts1)/len(pts1)
    c1 = (cx, cy)
    dists = sorted(((dist(c1, p), p) for p in pts3), key=lambda x: x[0])
    ap1 = dists[0][1]; ap2 = dists[-1][1]
    return ap1, ap2

def find_t1_near_ap2(texts: List[object], ap2: Tuple[float,float]) -> Optional[object]:
    """AP2 기준 창(-X40~+15, Y±7)에서 회전≈0 이고 'DN' & 'x' 포함 TEXT/MTEXT."""
    if ap2 is None: return None
    x0 = ap2[0] - AP2_WIN_X_NEG; x1 = ap2[0] + AP2_WIN_X_POS
    y0 = ap2[1] - AP2_WIN_Y;     y1 = ap2[1] + AP2_WIN_Y

    for t in texts:
        if not safe_has_dxf(t): continue
        raw = text_string(t); s = clean_text(raw); su = s.upper()
        has_x = ("X" in su) or ("×" in raw)  # 곱셈기호도 허용
        if ("DN" in su) and has_x:
            ip = text_insert_point(t); rot = text_rotation(t)
            if abs(rot) <= T1_ROT_TOL and within_rect(ip, x0, x1, y0, y1):
                return t
    return None

def parse_elfl_value(t) -> Optional[Tuple[str, float]]:
    """T2(TEXT/MTEXT)에서 ('EL' or 'FL', 값) 추출. 값이 없으면 None."""
    if t is None: return None
    s = clean_text(text_string(t))
    m = RE_ELFL_WITH_VALUE.search(s)
    if not m: return None
    kind = m.group(1).upper()
    try:
        val = float(m.group(2))
    except Exception:
        return None
    return kind, val

def find_t2_from_t1(texts: List[object], t1) -> Optional[object]:
    """
    T1 기준으로 '아래쪽'을 유연 범위로 탐색:
      1차: dy ∈ [T2_Y_MIN, T2_Y_MAX], |dx| ≤ T2_X_HALF
      2차(fallback): 0 < dy ≤ T2_Y_FALLBACK_MAX, |dx| ≤ T2_X_FALLBACK
    후보는 dy(수직거리) 최소 → dx 최소 순으로 선택.
    """
    if t1 is None: return None
    p1 = text_insert_point(t1)

    def collect_candidates(y_min, y_max, x_half):
        cands = []
        for t in texts:
            if not safe_has_dxf(t): continue
            s = clean_text(text_string(t))
            if not RE_ELFL.search(s):  # 'EL' 또는 'FL' 토큰이 없으면 제외
                continue
            ip = text_insert_point(t)
            dy = p1[1] - ip[1]  # 아래쪽이면 dy>0
            dx = abs(ip[0] - p1[0])
            if (dy > 0) and (y_min <= dy <= y_max) and (dx <= x_half):
                cands.append((dy, dx, t))
        cands.sort(key=lambda x: (x[0], x[1]))
        return cands

    # 1차(타이트): 4~10mm, ±30mm
    cands = collect_candidates(T2_Y_MIN, T2_Y_MAX, T2_X_HALF)
    if cands:
        return cands[0][2]

    # 2차(느슨): 0~14mm, ±45mm
    cands = collect_candidates(0.0, T2_Y_FALLBACK_MAX, T2_X_FALLBACK)
    if cands:
        return cands[0][2]

    return None

# ---------------- 데이터 구조 ----------------
@dataclass
class ADGroup:
    cluster_id: int = -1
    ad1: Optional[object] = None
    ad2: Optional[object] = None
    ad3: Optional[object] = None
    ap1: Optional[Tuple[float,float]] = None
    ap2: Optional[Tuple[float,float]] = None
    t1:  Optional[object] = None
    t2:  Optional[object] = None
    t2_kind: Optional[str] = None   # 'EL' or 'FL'
    t2_value: Optional[float] = None

# ---------------- 메인 처리 ----------------
def build_entity_lists(msp):
    polys, lines, texts = [], [], []
    for e in list(msp):
        if not safe_has_dxf(e): continue
        t = e.dxftype()
        if   t in ("LWPOLYLINE", "POLYLINE"): polys.append(e)
        elif t == "LINE":                     lines.append(e)
        elif t in ("TEXT", "MTEXT"):          texts.append(e)
    return polys, lines, texts

def process_file(path: str):
    print(f"[INFO] Processing: {os.path.basename(path)}")
    try:
        doc = ezdxf.readfile(path)
    except Exception as ex:
        print(f"[ERROR] open failed: {ex}")
        return

    msp = doc.modelspace()
    for L in (LAYER_AD1, LAYER_AD2, LAYER_AD3):
        ensure_layer(doc, L)

    polys, lines, texts = build_entity_lists(msp)

    # 1) 개선된 TOTEE 클러스터 확장
    clusters = expand_totee_clusters_improved(polys)

    # 2) 클러스터별 TP 처리 → entries_all
    entries_all: List[ADGroup] = []
    for cid, cluster in enumerate(clusters):
        for tp in cluster["tps"]:
            ad1 = find_ad1_near_tp(polys, tp)
            if ad1 is None:
                continue
            set_layer_safe(ad1, LAYER_AD1)

            ad2 = find_ad2_around_ad1(lines, ad1)
            if ad2 is not None:
                set_layer_safe(ad2, LAYER_AD2)

            ad3 = find_ad3_around_ad1(polys, ad1)
            if ad3 is not None:
                set_layer_safe(ad3, LAYER_AD3)

            ap1, ap2 = ap1_ap2_from_ad3(ad3, ad1)
            t1 = find_t1_near_ap2(texts, ap2) if ap2 is not None else None
            t2 = find_t2_from_t1(texts, t1) if t1 is not None else None

            t2_kind, t2_value = (None, None)
            if t2 is not None:
                pv = parse_elfl_value(t2)
                if pv is not None:
                    t2_kind, t2_value = pv

            entries_all.append(ADGroup(
                cluster_id=cid, ad1=ad1, ad2=ad2, ad3=ad3, ap1=ap1, ap2=ap2,
                t1=t1, t2=t2, t2_kind=t2_kind, t2_value=t2_value
            ))

    # 3) 클러스터별 T1 개수 집계 (TOTEE에 T1이 1개만인지 판정에 사용)
    cluster_t1_count: Dict[int, int] = defaultdict(int)
    for g in entries_all:
        if g.t1 is not None:
            cluster_t1_count[g.cluster_id] += 1

    # 4) 전역 그룹 로직 (T1 텍스트값 기준) + (TYP.) 출력 조건에 클러스터 개수 반영
    groups: Dict[str, List[ADGroup]] = defaultdict(list)
    for g in entries_all:
        key = clean_text(text_string(g.t1)).strip().upper() if g.t1 is not None else ""
        if key:
            groups[key].append(g)

    to_delete: List[ADGroup] = []

    for key, grp in groups.items():
        has_t2 = any(g.t2 is not None for g in grp)

        if has_t2:
            # T2 있는 항목만 보존
            for g in grp:
                if g.t2 is not None:
                    # (신규 규칙) 클러스터 내 T1이 1개뿐이면 '(TYP.)' 미출력
                    if cluster_t1_count.get(g.cluster_id, 0) > 1:
                        add_typ_text(msp, g.t2, TYP_DY)
                else:
                    to_delete.append(g)
        else:
            # T2 전무 → 첫 번째만 보존
            if grp:
                ref = grp[0]
                # (신규 규칙) 클러스터 내 T1이 1개뿐이면 '(TYP.)' 미출력
                if ref.t1 is not None and cluster_t1_count.get(ref.cluster_id, 0) > 1:
                    add_typ_text(msp, ref.t1, TYP_DY)
                for g in grp[1:]:
                    to_delete.append(g)

    # 5) 보존 외 삭제
    for g in to_delete:
        delete_safe(msp, g.t1)
        delete_safe(msp, g.ad1)
        delete_safe(msp, g.ad2)
        delete_safe(msp, g.ad3)

    # 6) 저장
    base, _ = os.path.splitext(path)
    out_path = f"{base}_TEEDIT.dxf"
    try:
        doc.saveas(out_path)
        print(f"[OK] Saved: {out_path}")
    except Exception as ex:
        print(f"[ERROR] save failed: {ex}")

# ---------------- 파일 선택 & 메인 ----------------
def pick_files() -> List[str]:
    if tk is None:
        print("[WARN] tkinter 없음: 현재 폴더의 *.dxf 자동 선택")
        return [f for f in os.listdir(".") if f.lower().endswith(".dxf")]
    root = tk.Tk(); root.withdraw()
    paths = filedialog.askopenfilenames(
        title="DXF 파일 선택 (1개 이상)",
        filetypes=[("DXF files", "*.dxf"), ("All files", "*.*")]
    )
    root.update(); root.destroy()
    return list(paths)

def main():
    paths = pick_files()
    if not paths:
        print("[INFO] 선택된 DXF 없음.")
        return
    for p in paths:
        process_file(p)

if __name__ == "__main__":
    main()