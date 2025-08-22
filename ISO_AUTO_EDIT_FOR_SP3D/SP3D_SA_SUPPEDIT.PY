import ezdxf
import tkinter as tk
from tkinter import filedialog
import math
import os
import traceback
import sys
import re

# ---------- 상수 ----------
CYAN = 4
RED = 1
YELLOW = 2
BLUE = 5
MAGENTA = 6
WHITE = 7

SL1_LENGTH = 3.5        # 참고값
HALF_SL1 = 0.25         # CP 원 반지름(=지름 0.5mm)
LINE_LENGTH = 7.0       # 직교 보조선 길이
LINE_WIDTH = 0.6
NODENO_RADIUS = 5.25
NODENO_OFFSET_Y = 12.25
NODENO_OFFSET_FALLBACK = 20.0   # 모든 각도 간섭 시 보조 오프셋
ROTATION_ANGLE = 30
TEXT_HEIGHT = 3.0
TEXT_VALUE = '0000'

# S1 페어링 거리 임계값
DMIN = 3.0
DMAX = 7.0

# OPTION B: 수직(90, 270) 패널티
VERTICAL_PENALTY = 0.1

# Fallback: SUPP 원 지름 허용 (3.5~4.0mm) + 공차
FALLBACK_DIAM_MIN = 3.5
FALLBACK_DIAM_MAX = 4.0
DIAM_TOL = 0.05

# C1 중심을 "통과"하는 LINE 판정 허용 오차
LINE_THROUGH_TOL = 0.10  # mm

# ELBO 두 LINE 접점/엔드포인트 비교 허용 오차
JOIN_TOL = 0.2  # mm

# ---------- 유틸 ----------
def calc_distance(p1, p2):
    return math.hypot(p1[0]-p2[0], p1[1]-p2[1])

def extract_points(ent):
    """LINE 전용 포인트 추출"""
    try:
        if not ent or not hasattr(ent, 'dxf') or ent.dxf is None:
            return []
        if ent.dxftype() == 'LINE':
            return [(ent.dxf.start.x, ent.dxf.start.y), (ent.dxf.end.x, ent.dxf.end.y)]
    except:
        pass
    return []

def has_curve(ent):
    """요청 명시: LINE은 항상 곡선 아님"""
    return False

def polyline_length(pts):
    return sum(calc_distance(pts[i], pts[i+1]) for i in range(len(pts)-1))

def midpoint(pts):
    return (sum(p[0] for p in pts)/len(pts), sum(p[1] for p in pts)/len(pts))

def point_to_line_distance(point, a, b):
    x0, y0 = point; x1, y1 = a; x2, y2 = b
    dx = x2-x1; dy = y2-y1
    if dx == 0 and dy == 0:
        return calc_distance(point, a)
    t = ((x0-x1)*dx + (y0-y1)*dy) / (dx*dx + dy*dy)
    t = max(0, min(1, t))
    closest = (x1 + t*dx, y1 + t*dy)
    return calc_distance(point, closest)

def is_entity_cyan(e, doc):
    """엔티티가 실질적으로 CYAN인지: 직접색(4) 또는 BYLAYER(256) + 레이어 색상 4"""
    try:
        ent_col = getattr(e.dxf, "color", None)
        if ent_col == CYAN:
            return True
        if ent_col in (256, None):  # ByLayer
            lyr_name = getattr(e.dxf, "layer", None)
            if lyr_name and lyr_name in doc.layers:
                lyr_col = doc.layers.get(lyr_name).dxf.color
                return lyr_col == CYAN
        return False
    except:
        return False

# ---------- CT STYPE 추출 ----------
def extract_stype_from_text(ct_content: str):
    """
    CT 전체 문자열에서 -G, -A, -C, -V 중 '가장 마지막 매치'를 STYPE으로 반환.
    (대소문자 무시) / 없으면 None
    """
    last = None
    for m in re.finditer(r"-(G|A|C|V)", ct_content, flags=re.IGNORECASE):
        last = m
    if last is None:
        return None
    return last.group(1).upper()

# ---------- S1 ----------
def is_valid_s1(ent):
    """
    S1 조건:
      - LINE
      - 레이어: WELDS 또는 NOZZLES
      - 점 2개
      - 수평 제외(abs(dy) >= 1e-6)
      - 길이 3.0~4.0mm
      - 곡선 없음
    """
    if ent.dxftype() != 'LINE':
        return False
    if has_curve(ent):
        return False
    if getattr(ent.dxf, 'layer', '') not in ("WELDS", "NOZZLES"):
        return False

    pts = extract_points(ent)
    if len(pts) != 2:
        return False

    if abs(pts[0][1] - pts[1][1]) < 1e-6:
        return False

    L = polyline_length(pts)
    return 3.0 <= L <= 4.0

def find_s1_candidates(msp):
    s1_list = []
    for e in msp:
        if is_valid_s1(e):
            pts = extract_points(e)
            s1_list.append({'ent': e, 'pts': pts})
    if s1_list:
        print(f"✅ 유효한 S1 개수: {len(s1_list)}")
    return s1_list

# ---------- Fallback: SUPP 원(C1) + D1 ----------
def find_supp_cyan_circles_as_fallback(msp, doc):
    """
    SUPP 레이어의 CYAN 원 중 지름 3.5~4.0mm(±공차) 수집.
    반환: [({'ent': circle, 'center': (x,y), 'dia': d}), ...]
    """
    found = []
    for e in msp:
        if e.dxftype() != "CIRCLE":
            continue
        if getattr(e.dxf, "layer", "") != "SUPP":
            continue
        if not is_entity_cyan(e, doc):
            continue
        try:
            dia = float(e.dxf.radius) * 2.0
        except:
            continue
        if (FALLBACK_DIAM_MIN - DIAM_TOL) <= dia <= (FALLBACK_DIAM_MAX + DIAM_TOL):
            cx, cy = e.dxf.center.x, e.dxf.center.y
            found.append({'ent': e, 'center': (cx, cy), 'dia': dia})
    if found:
        print(f"⚠️ Fallback 후보(C1) {len(found)}개 발견 (지름 {FALLBACK_DIAM_MIN}~{FALLBACK_DIAM_MAX}mm ±{DIAM_TOL})")
    return found

def find_lines_through_point(msp, center, tol=LINE_THROUGH_TOL):
    """
    center를 '통과'한다고 볼 수 있는 LINE들을 찾음 (최단거리 <= tol).
    반환: [LINE, LINE, ...] (길이 내림차순 상위 2개)
    """
    candidates = []
    for e in msp:
        if e.dxftype() != 'LINE':
            continue
        pts = extract_points(e)
        if len(pts) != 2:
            continue
        dist = point_to_line_distance(center, pts[0], pts[1])
        if dist <= tol:
            L = calc_distance(pts[0], pts[1])
            candidates.append((e, L))
    candidates.sort(key=lambda x: x[1], reverse=True)
    return [c[0] for c in candidates[:2]]

def pipe_angle_from_two_lines(lines):
    """
    LINE 2개로부터 파이프 주 방향 추정: 두 선 방향 벡터 평균
    """
    if not lines:
        return 0.0
    dirs = []
    for ln in lines:
        pts = extract_points(ln)
        if len(pts) == 2:
            v = (pts[1][0]-pts[0][0], pts[1][1]-pts[0][1])
            mag = math.hypot(v[0], v[1])
            if mag > 0:
                dirs.append((v[0]/mag, v[1]/mag))
    if not dirs:
        return 0.0
    base = dirs[0]
    adj = [base]
    for d in dirs[1:]:
        dp = base[0]*d[0] + base[1]*d[1]
        adj.append((-d[0], -d[1]) if dp < 0 else d)
    avg = (sum(a[0] for a in adj)/len(adj), sum(a[1] for a in adj)/len(adj))
    if abs(avg[0]) < 1e-6 and abs(avg[1]) < 1e-6:
        avg = base
    return math.atan2(avg[1], avg[0])

# ---------- 방향/직교선 ----------
def get_pipe_angle(pts1, pts2):
    """두 S1 LINE으로 파이프 주 방향 각도 계산"""
    dir1 = (pts1[1][0] - pts1[0][0], pts1[1][1] - pts1[0][1])
    dir2 = (pts2[1][0] - pts2[0][0], pts2[1][1] - pts2[0][1])
    mag1 = math.hypot(*dir1); mag2 = math.hypot(*dir2)
    norm1 = (dir1[0]/mag1, dir1[1]/mag1) if mag1 > 0 else (0,0)
    norm2 = (dir2[0]/mag2, dir2[1]/mag2) if mag2 > 0 else (0,0)
    dp = norm1[0]*norm2[0] + norm1[1]*norm2[1]
    if dp < -0.5:
        dir2 = (-dir2[0], -dir2[1])
    avg_dir = ((dir1[0]+dir2[0])/2, (dir1[1]+dir2[1])/2)
    if abs(avg_dir[0]) < 0.01 and abs(avg_dir[1]) < 0.01:
        avg_dir = dir1
    return math.atan2(avg_dir[1], avg_dir[0])

def create_triangle_arrow(center, direction_angle_deg, side_length, base_width, msp, color=CYAN, layer='SUPP', scale=1.0):
    """삼각형 화살표: LINE 3개로 구성"""
    ang = math.radians(direction_angle_deg)
    h = math.sqrt(max(0.0, side_length**2 - (base_width/2)**2))
    centroid_dist = h * 2/3
    centroid = (center[0] + centroid_dist*math.cos(ang),
                center[1] + centroid_dist*math.sin(ang))

    p1 = center
    p2 = (center[0] - (base_width/2)*math.cos(ang+math.pi/2) + h*math.cos(ang),
          center[1] - (base_width/2)*math.sin(ang+math.pi/2) + h*math.sin(ang))
    p3 = (center[0] + (base_width/2)*math.cos(ang+math.pi/2) + h*math.cos(ang),
          center[1] + (base_width/2)*math.sin(ang+math.pi/2) + h*math.sin(ang))

    def scale_point(p):
        return (centroid[0] + (p[0]-centroid[0])*scale,
                centroid[1] + (p[1]-centroid[1])*scale)
    p1, p2, p3 = scale_point(p1), scale_point(p2), scale_point(p3)

    msp.add_line(p1, p2, dxfattribs={'color': color, 'layer': layer})
    msp.add_line(p2, p3, dxfattribs={'color': color, 'layer': layer})
    msp.add_line(p3, p1, dxfattribs={'color': color, 'layer': layer})

def create_iso_orthogonal_lines(center, pipe_angle, length, msp):
    """ISO 기준 직교 방향 4개로 LINE 생성 + 삼각형 스택"""
    lines = []
    line_angles = []
    pipe_angle_deg = math.degrees(pipe_angle) % 360
    normalized = round(pipe_angle_deg/30)*30 % 360
    if 85 <= pipe_angle_deg <= 95 or 265 <= pipe_angle_deg <= 275:
        normalized = 90 if pipe_angle_deg < 180 else 270

    if normalized in (0, 180):
        angles = [90, 270, 30, 210]
    elif normalized in (90, 270):
        angles = [30, 150, 210, 330]
    elif normalized in (30, 210):
        angles = [90, 270, 150, 330]
    elif normalized in (60, 240):
        angles = [90, 270, 180, 0]
    elif normalized in (120, 300):
        angles = [90, 270, 60, 240]
    elif normalized in (150, 330):
        angles = [90, 270, 30, 210]
    else:
        orth = (pipe_angle_deg + 90) % 360
        orth_n = round(orth/30)*30
        angles = [orth_n % 360, (orth_n+180)%360, (orth_n+60)%360, (orth_n+240)%360]

    for angle_deg in angles[:4]:
        ang = math.radians(angle_deg)
        start = (center[0] + HALF_SL1*math.cos(ang), center[1] + HALF_SL1*math.sin(ang))
        end = (center[0] + length*math.cos(ang), center[1] + length*math.sin(ang))
        line = msp.add_line(start, end, dxfattribs={'color': CYAN, 'layer': 'SUPP', 'lineweight': 60})
        lines.append(line)
        line_angles.append(angle_deg)

        arrow_side = 4.0
        arrow_base = 1.4
        for j in range(5):
            scale = 1.0 - j*0.2
            if scale <= 0:
                break
            create_triangle_arrow(center, angle_deg, arrow_side, arrow_base, msp, scale=scale)

    return lines, line_angles

# ---------- NODE 위치 선택 (OPTION B + 오프셋 fallback) ----------
def _best_angle_for_offset(candidate_angles, cp, offset, msp, exclude_entities):
    best_angle = None
    best_score = float('inf')
    any_zero = False

    for angle in candidate_angles:
        ang = math.radians(angle)
        test_pos = (cp[0] + offset * math.cos(ang),
                    cp[1] + offset * math.sin(ang))

        interference_count = 0
        for ent in msp:
            if ent in exclude_entities:
                continue
            t = ent.dxftype()
            if t == 'CIRCLE':
                oc = (ent.dxf.center.x, ent.dxf.center.y)
                orad = ent.dxf.radius
                if calc_distance(test_pos, oc) < (NODENO_RADIUS + orad + 1.0):
                    interference_count += 1
            elif t == 'LINE':
                pts = extract_points(ent)
                if len(pts) == 2 and point_to_line_distance(test_pos, pts[0], pts[1]) < NODENO_RADIUS + 1.0:
                    interference_count += 1
            elif t in ('TEXT','MTEXT'):
                pos = (ent.dxf.insert.x, ent.dxf.insert.y)
                if calc_distance(test_pos, pos) < NODENO_RADIUS + 2.0:
                    interference_count += 1

        if interference_count == 0:
            any_zero = True

        vertical_pen = VERTICAL_PENALTY if angle in (90, 270) else 0.0
        score = interference_count + vertical_pen
        if score < best_score:
            best_score = score
            best_angle = angle

    return best_angle, best_score, any_zero

def find_best_orthogonal_position_for_special(cp, offset_distance, pipe_angle, msp, exclude_entities):
    """ELBO/TEE용: 모든 30° 간격 각도(수직 포함) 후보, 수직은 패널티.
       모든 각도 간섭이면 offset=20mm로 재시도."""
    candidate_angles = [0, 30, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330]

    angle1, score1, any_zero1 = _best_angle_for_offset(candidate_angles, cp, offset_distance, msp, exclude_entities)
    if not any_zero1:  # 모든 각도 간섭 → 20mm로 재시도
        angle2, score2, any_zero2 = _best_angle_for_offset(candidate_angles, cp, NODENO_OFFSET_FALLBACK, msp, exclude_entities)
        if angle2 is not None and score2 <= score1:
            ang = math.radians(angle2)
            return (cp[0] + NODENO_OFFSET_FALLBACK * math.cos(ang),
                    cp[1] + NODENO_OFFSET_FALLBACK * math.sin(ang))
    # 기본/우선 결과
    ang = math.radians(angle1 if angle1 is not None else 0)
    return (cp[0] + offset_distance * math.cos(ang),
            cp[1] + offset_distance * math.sin(ang))

def find_best_orthogonal_position(cp, offset_distance, pipe_angle, msp, exclude_entities, line_angles=None):
    """일반 NODE용: 후보 각도(수직 포함) 중 간섭 최소 + 수직 패널티, 전각도 간섭시 20mm 재시도."""
    pipe_angle_deg = math.degrees(pipe_angle) % 360
    normalized_angle = round(pipe_angle_deg / 30) * 30 % 360
    if 85 <= pipe_angle_deg <= 95 or 265 <= pipe_angle_deg <= 275:
        normalized_angle = 90 if pipe_angle_deg < 180 else 270

    if normalized_angle in (0, 180):
        orthogonal_angles = [90, 270, 30, 210]
    elif normalized_angle in (90, 270):
        orthogonal_angles = [30, 150, 210, 330]
    elif normalized_angle in (30, 210):
        orthogonal_angles = [90, 270, 150, 330]
    elif normalized_angle in (60, 240):
        orthogonal_angles = [90, 270, 180, 0]
    elif normalized_angle in (120, 300):
        orthogonal_angles = [90, 270, 60, 240]
    elif normalized_angle in (150, 330):
        orthogonal_angles = [90, 270, 30, 210]
    else:
        orth_angle = (pipe_angle_deg + 90) % 360
        orth_angle_normalized = round(orth_angle / 30) * 30
        orthogonal_angles = [
            orth_angle_normalized % 360,
            (orth_angle_normalized + 180) % 360,
            (orth_angle_normalized + 60) % 360,
            (orth_angle_normalized + 240) % 360
        ]

    candidate_angles = orthogonal_angles
    angle1, score1, any_zero1 = _best_angle_for_offset(candidate_angles, cp, offset_distance, msp, exclude_entities)
    if not any_zero1:
        angle2, score2, any_zero2 = _best_angle_for_offset(candidate_angles, cp, NODENO_OFFSET_FALLBACK, msp, exclude_entities)
        if angle2 is not None and score2 <= score1:
            ang = math.radians(angle2)
            return (cp[0] + NODENO_OFFSET_FALLBACK * math.cos(ang),
                    cp[1] + NODENO_OFFSET_FALLBACK * math.sin(ang)), angle2

    ang = math.radians(angle1 if angle1 is not None else candidate_angles[0])
    return (cp[0] + offset_distance * math.cos(ang),
            cp[1] + offset_distance * math.sin(ang)), (angle1 if angle1 is not None else candidate_angles[0])

# ---------- ARROW(AD2) (현재는 ISOTEXT에서 길이≤1mm로 탐색) ----------
def find_arrow_lines(msp, a1_points):
    results = []
    for e in msp:
        if e.dxftype() == 'LINE' and getattr(e.dxf, 'layer', '') == 'ISOTEXT':
            line_pts = extract_points(e)
            if len(line_pts) == 2:
                line_length = calc_distance(line_pts[0], line_pts[1])
                if line_length <= 1.0:
                    for a1_pt in [a1_points[0], a1_points[-1]]:
                        for lp in line_pts:
                            if calc_distance(a1_pt, lp) <= 0.1:
                                results.append(e)
                                break
                        if e in results:
                            break
    return results

# ---------- PIPE 연결/ELBO ----------
def find_connected_pipes(elbo_pts, msp):
    start_point = elbo_pts[0]; end_point = elbo_pts[-1]
    start_pipe = None; end_pipe = None
    for e in msp:
        lyr = getattr(e.dxf, 'layer', '')
        if e.dxftype() == 'LINE' and 'PIPE' in lyr:
            pts = extract_points(e)
            if len(pts) == 2:
                for pt in pts:
                    if calc_distance(pt, start_point) < 0.5:
                        start_pipe = {'entity': e, 'points': pts, 'connection': pt}
                        break
                for pt in pts:
                    if calc_distance(pt, end_point) < 0.5:
                        end_pipe = {'entity': e, 'points': pts, 'connection': pt}
                        break
    return start_pipe, end_pipe

def find_line_intersection(p1, v1, p2, v2):
    det = v1[0]*v2[1] - v1[1]*v2[0]
    if abs(det) < 1e-10:
        return None
    dp = (p2[0]-p1[0], p2[1]-p1[1])
    t1 = (dp[0]*v2[1] - dp[1]*v2[0]) / det
    return (p1[0] + t1*v1[0], p1[1] + t1*v1[1])

def _arc_endpoint(cx, cy, r, ang_deg):
    ang = math.radians(ang_deg)
    return (cx + r*math.cos(ang), cy + r*math.sin(ang))

def _tangent_dirs(theta_rad):
    return [(-math.sin(theta_rad), math.cos(theta_rad)),
            ( math.sin(theta_rad), -math.cos(theta_rad))]

def _outer_intersection_for_arc(arc):
    cx, cy = arc.dxf.center.x, arc.dxf.center.y
    r = arc.dxf.radius
    sa = arc.dxf.start_angle
    ea = arc.dxf.end_angle
    p1 = _arc_endpoint(cx, cy, r, sa)
    p2 = _arc_endpoint(cx, cy, r, ea)
    v1cands = _tangent_dirs(math.radians(sa))
    v2cands = _tangent_dirs(math.radians(ea))

    best = None
    for v1 in v1cands:
        for v2 in v2cands:
            inter = find_line_intersection(p1, v1, p2, v2)
            if inter:
                d = calc_distance(inter, (cx, cy))
                if (best is None) or (d > best[0]):
                    best = (d, inter, v1, v2)
    if best:
        _, inter, v1, v2 = best
        avg_dir = ((v1[0]+v2[0])/2.0, (v1[1]+v2[1])/2.0)
        ang = math.atan2(avg_dir[1], avg_dir[0])
        return inter, ang
    mid = ((p1[0]+p2[0])/2.0, (p1[1]+p2[1])/2.0)
    return mid, 0.0

def find_elbow_vertices_line_pair_junction(msp):
    elbo_lines = [e for e in msp if getattr(e.dxf, 'layer', '') == 'ELBO' and e.dxftype() == 'LINE']
    junctions = []
    used_pairs = set()
    for i in range(len(elbo_lines)):
        p1s, p1e = extract_points(elbo_lines[i])
        for j in range(i+1, len(elbo_lines)):
            p2s, p2e = extract_points(elbo_lines[j])
            ends1 = [p1s, p1e]; ends2 = [p2s, p2e]
            for a in ends1:
                for b in ends2:
                    if calc_distance(a, b) <= JOIN_TOL:
                        key = (i, j)
                        if key not in used_pairs:
                            used_pairs.add(key)
                            junction = ((a[0]+b[0])/2.0, (a[1]+b[1])/2.0)
                            junctions.append(junction)
                        break
    return junctions

# ---------- TEXT ----------
def add_text_to_node(msp, center, text_value, height, color, layer, doc=None):
    try:
        if doc and "ARIAL" not in doc.styles:
            try:
                doc.styles.new("ARIAL", dxfattribs={"font": "arial.ttf"})
            except:
                pass
        txt = msp.add_text(
            text_value,
            dxfattribs={
                'height': 3.5,
                'color': MAGENTA,
                'layer': layer,
                'insert': (0, 0, 0),
                'halign': 4,
                'valign': 2,
                'style': 'ARIAL' if doc else 'Standard',
                'width': 0.85
            }
        )
        try:
            from ezdxf.math import Matrix44
            txt.transform(Matrix44.translate(center[0], center[1], 0))
            return txt
        except:
            try:
                msp.delete_entity(txt)
            except:
                pass
            return msp.add_text(
                text_value,
                dxfattribs={
                    'height': 3.5,
                    'color': MAGENTA,
                    'layer': layer,
                    'insert': (center[0], center[1], 0),
                    'halign': 4,
                    'valign': 2,
                    'style': 'ARIAL' if doc else 'Standard',
                    'width': 0.85
                }
            )
    except:
        try:
            return msp.add_text(
                text_value,
                dxfattribs={'height': 3.5, 'color': MAGENTA, 'layer': layer, 'insert': (center[0], center[1], 0), 'halign': 4, 'valign': 2}
            )
        except:
            return None

# ---------- 특수 노드(ELBO/TEE) ----------
def process_special_nodes(msp, doc):
    processed_count = 0
    texts_to_add = []

    # ELBO 레이어 색상 변경 유지
    elbo_count = 0
    for e in msp:
        if getattr(e.dxf, 'layer', '') == 'ELBO':
            try:
                e.dxf.color = CYAN
                elbo_count += 1
            except:
                pass
    if elbo_count:
        print(f"  ELBO 레이어 {elbo_count}개 엔티티 색상 CYAN")

    # --- (1) ELBO가 선(두 LINE)인 경우: 교차점에 NODE 생성 후, TEE와 동일한 간섭/이동 처리 ---
    junctions = find_elbow_vertices_line_pair_junction(msp)
    for jp in junctions:
        node_circle = msp.add_circle(center=jp, radius=NODENO_RADIUS, dxfattribs={'color': MAGENTA, 'layer': 'NODE'})
        nodeno_pos = find_best_orthogonal_position_for_special(
            jp, NODENO_OFFSET_Y, 0.0, msp, []
        )
        try:
            node_circle.dxf.center = nodeno_pos
        except:
            try:
                msp.delete_entity(node_circle)
            except:
                pass
            node_circle = msp.add_circle(center=nodeno_pos, radius=NODENO_RADIUS, dxfattribs={'color': MAGENTA, 'layer': 'NODE'})
        dx = nodeno_pos[0] - jp[0]
        dy = nodeno_pos[1] - jp[1]
        dist = math.hypot(dx, dy)
        if dist > 0:
            ux, uy = dx/dist, dy/dist
            trim_end = (nodeno_pos[0] - ux*NODENO_RADIUS, nodeno_pos[1] - uy*NODENO_RADIUS)
            msp.add_line(jp, trim_end, dxfattribs={'color': WHITE, 'layer': 'NODE'})
        texts_to_add.append(nodeno_pos)
        processed_count += 1

    # --- (2) ELBO가 호(ARC)인 경우: 기존과 동일(코너 추정 후 오프셋 배치) ---
    for e in msp:
        if getattr(e.dxf, 'layer', '') == 'ELBO' and e.dxftype() == 'ARC':
            corner, pipe_ang = _outer_intersection_for_arc(e)
            nodeno_pos = find_best_orthogonal_position_for_special(
                corner, NODENO_OFFSET_Y, pipe_ang, msp, []
            )
            msp.add_circle(center=nodeno_pos, radius=NODENO_RADIUS, dxfattribs={'color': MAGENTA, 'layer': 'NODE'})
            dx = nodeno_pos[0] - corner[0]
            dy = nodeno_pos[1] - corner[1]
            dist = math.hypot(dx, dy)
            if dist > 0:
                ux, uy = dx/dist, dy/dist
                trim_end = (nodeno_pos[0] - ux*NODENO_RADIUS, nodeno_pos[1] - uy*NODENO_RADIUS)
                msp.add_line(corner, trim_end, dxfattribs={'color': WHITE, 'layer': 'NODE'})
            texts_to_add.append(nodeno_pos)
            processed_count += 1

    # --- (3) TEE 처리: 동일 로직 유지 ---
    tee_count = 0
    for e in msp:
        if 'TEE' in getattr(e.dxf, 'layer', ''):
            try:
                e.dxf.color = CYAN
                tee_count += 1
            except:
                pass
    if tee_count:
        print(f"  TEE 레이어 {tee_count}개 엔티티 색상 CYAN")

    tee_lines = []
    for e in msp:
        if 'TEE' in getattr(e.dxf, 'layer', '') and e.dxftype() == 'LINE':
            pts = extract_points(e)
            if pts:
                tee_lines.append({'entity': e, 'points': pts})
    point_count = {}
    point_entities = {}
    for item in tee_lines:
        for pt in item['points']:
            key = f"{pt[0]:.1f},{pt[1]:.1f}"
            point_count[key] = point_count.get(key, 0) + 1
            point_entities.setdefault(key, []).append(item['entity'])

    tee_points = []
    for key, cnt in point_count.items():
        if cnt >= 3:
            x, y = map(float, key.split(','))
            tee_points.append({'point': (x, y), 'count': cnt, 'entities': point_entities[key]})

    for tee in tee_points:
        center_point = tee['point']
        pipe_angle = 0.0
        dirs = []
        for ent in tee['entities'][:2]:
            pts = extract_points(ent)
            if len(pts) == 2:
                d0 = calc_distance(pts[0], center_point)
                d1 = calc_distance(pts[1], center_point)
                if d0 <= d1:
                    dirs.append((pts[1][0]-pts[0][0], pts[1][1]-pts[0][1]))
                else:
                    dirs.append((pts[0][0]-pts[1][0], pts[0][1]-pts[1][1]))
        if dirs:
            avg = (sum(d[0] for d in dirs)/len(dirs), sum(d[1] for d in dirs)/len(dirs))
            if abs(avg[0]) > 0.01 or abs(avg[1]) > 0.01:
                pipe_angle = math.atan2(avg[1], avg[0])

        nodeno_pos = find_best_orthogonal_position_for_special(
            center_point, NODENO_OFFSET_Y, pipe_angle, msp, []
        )
        msp.add_circle(center=nodeno_pos, radius=NODENO_RADIUS, dxfattribs={'color': MAGENTA, 'layer': 'NODE'})

        dx = nodeno_pos[0] - center_point[0]
        dy = nodeno_pos[1] - center_point[1]
        dist = math.hypot(dx, dy)
        if dist > 0:
            ux, uy = dx/dist, dy/dist
            trim_end = (nodeno_pos[0] - ux*NODENO_RADIUS, nodeno_pos[1] - uy*NODENO_RADIUS)
            msp.add_line(center_point, trim_end, dxfattribs={'color': WHITE, 'layer': 'NODE'})

        texts_to_add.append(nodeno_pos)
        processed_count += 1

    for pos in texts_to_add:
        add_text_to_node(msp, pos, TEXT_VALUE, TEXT_HEIGHT, YELLOW, 'NODE', doc)

    return processed_count

# ---------- TYPE2 보조 ----------
def process_type2_support(msp, a1_data, a2_data, ct_entity, cp_center, orthogonal_lines, line_angles, pipe_angle, node_angle):
    if not a2_data or not ct_entity:
        return None

    ad1_center = midpoint(a1_data['pts'])
    a2_pts = a2_data['pts']
    ap1 = min(a2_pts, key=lambda p: calc_distance(p, ad1_center))
    ap2 = max(a2_pts, key=lambda p: calc_distance(p, ad1_center))

    # CT 내용 전체에서 STYPE 추출 (-G/-A/-C/-V 마지막 매치)
    if ct_entity.dxftype() == 'TEXT':
        ct_content = ct_entity.dxf.text
    else:
        ct_content = ct_entity.text
    stype = extract_stype_from_text(ct_content)
    if not stype:
        return None

    if stype in ['G', 'A']:
        # NODE 없는 각도의 LINE(L1) 선택
        l1_angle = None
        for i, angle in enumerate(line_angles):
            if angle != node_angle:
                l1_angle = angle
                break
        if l1_angle is None:
            return None

        pipe_angle_deg = math.degrees(pipe_angle)
        ang = math.radians(l1_angle)
        inter_pt = (cp_center[0] - 5.5*math.cos(ang), cp_center[1] - 5.5*math.sin(ang))

        perp_ang = math.radians(pipe_angle_deg)
        p1 = (inter_pt[0] - 5.0*math.cos(perp_ang), inter_pt[1] - 5.0*math.sin(perp_ang))
        p2 = (inter_pt[0] + 5.0*math.cos(perp_ang), inter_pt[1] + 5.0*math.sin(perp_ang))
        msp.add_line(p1, p2, dxfattribs={'color': CYAN, 'layer': 'SUPP'})

        arrow_side = 4.0; arrow_base = 1.4
        for j in range(5):
            scale = 1.0 - j*0.2
            if scale <= 0:
                break
            create_triangle_arrow(inter_pt, pipe_angle_deg, arrow_side, arrow_base, msp, scale=scale)
        opp = (pipe_angle_deg + 180) % 360
        for j in range(5):
            scale = 1.0 - j*0.2
            if scale <= 0:
                break
            create_triangle_arrow(inter_pt, opp, arrow_side, arrow_base, msp, scale=scale)

    elif stype in ['C', 'V']:
        verticals = []
        for i, angle in enumerate(line_angles):
            if angle in (90, 270):
                verticals.append((orthogonal_lines[i], angle))
        if len(verticals) < 2:
            return None
        for line, angle in verticals:
            ang = math.radians(angle)
            distances = [5.0, 6.0, 7.0]
            pts = []
            for d in distances:
                pt = (cp_center[0] + d*math.cos(ang), cp_center[1] + d*math.sin(ang))
                pts.append(pt)
                pipe_angle_deg = math.degrees(pipe_angle)
                perp = math.radians(pipe_angle_deg)
                p1 = (pt[0] - 1.5*math.cos(perp), pt[1] - 1.5*math.sin(perp))
                p2 = (pt[0] + 1.5*math.cos(perp), pt[1] + 1.5*math.sin(perp))
                msp.add_line(p1, p2, dxfattribs={'color': WHITE, 'layer': 'SUPP'})
            pipe_angle_deg = math.degrees(pipe_angle)
            perp = math.radians(pipe_angle_deg)
            p5_end = (pts[0][0] + 1.5*math.cos(perp), pts[0][1] + 1.5*math.sin(perp))
            p6_start = (pts[1][0] - 1.5*math.cos(perp), pts[1][1] - 1.5*math.sin(perp))
            msp.add_line(p5_end, p6_start, dxfattribs={'color': WHITE, 'layer': 'SUPP'})
            p6_end = (pts[1][0] + 1.5*math.cos(perp), pts[1][1] + 1.5*math.sin(perp))
            p7_start = (pts[2][0] - 1.5*math.cos(perp), pts[2][1] - 1.5*math.sin(perp))
            msp.add_line(p6_end, p7_start, dxfattribs={'color': WHITE, 'layer': 'SUPP'})

    return None

# ---------- 메인 ----------
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

            # 필요한 레이어 보장
            for ln in ('NODE','SUPP','AD1','AD2','AD3'):
                if ln not in doc.layers:
                    doc.layers.new(ln)

            # --- 0) S1 찾기 ---
            s1_list = find_s1_candidates(msp)

            # --- 0-1) Fallback 후보(C1) 선편 수집 ---
            c1_candidates = find_supp_cyan_circles_as_fallback(msp, doc)

            cp_created_count = 0  # 이번 파일에서 만든 CP(지름 0.5) 개수

            # ===== (A) S1 경로 =====
            a1_a2_info = []

            if s1_list:
                # 1) AD1/AD2/AD3/CT 정보 수집 (레이어: ISOTEXT로 통합 탐색)
                for rec1 in s1_list:
                    for rec2 in s1_list:
                        if rec1 is rec2:
                            continue
                        if not hasattr(rec1['ent'], 'dxf') or not hasattr(rec2['ent'], 'dxf'):
                            continue

                        len1 = polyline_length(rec1['pts'])
                        len2 = polyline_length(rec2['pts'])
                        if abs(len1 - len2) > 0.2:
                            continue

                        all_dist = [calc_distance(a,b) for a in rec1['pts'] for b in rec2['pts']]
                        dmin = min(all_dist); dmax = max(all_dist)
                        if not (DMIN <= dmin <= DMAX and DMIN <= dmax <= DMAX):
                            continue
                        if any(calc_distance(p1, p2) <= 0.2 for p1 in rec1['pts'] for p2 in rec2['pts']):
                            continue

                        rec1['ent'].dxf.color = CYAN
                        rec2['ent'].dxf.color = CYAN

                        center_sl1 = midpoint([midpoint(rec1['pts']), midpoint(rec2['pts'])])

                        # AD1: 레이어 ISOTEXT, LINE, 길이<=5, CP 4mm 내
                        AD1 = None
                        for e in msp:
                            if e.dxftype() == 'LINE' and getattr(e.dxf, 'layer', '') == 'ISOTEXT':
                                pts = extract_points(e)
                                if len(pts) == 2 and polyline_length(pts) <= 5.0:
                                    if any(calc_distance(p, center_sl1) <= 4.0 for p in pts):
                                        AD1 = {'ent': e, 'pts': pts}
                                        break
                        if not AD1:
                            continue
                        AD1['ent'].dxf.layer = 'AD1'
                        AD1['ent'].dxf.color = RED

                        # AD2: 레이어 ISOTEXT, LINE, 길이<=1.0, AD1 점과 0.1mm 접촉 (AD1 제외)
                        AD2_list = []
                        for e in msp:
                            if e is AD1['ent']:
                                continue
                            if e.dxftype() == 'LINE' and getattr(e.dxf, 'layer', '') == 'ISOTEXT':
                                pts = extract_points(e)
                                if len(pts) == 2:
                                    L = calc_distance(pts[0], pts[1])
                                    if L <= 1.0:
                                        touched = False
                                        for ad1_pt in AD1['pts']:
                                            for lp in pts:
                                                if calc_distance(ad1_pt, lp) <= 0.1:
                                                    touched = True; break
                                            if touched: break
                                        if touched:
                                            e.dxf.layer = 'AD2'
                                            e.dxf.color = RED
                                            AD2_list.append(e)

                        # AD3: 레이어 ISOTEXT, LINE, AD1 점과 0.1mm 접촉, 길이>1.0 (AD1/AD2 제외)
                        AD3 = None
                        for e in msp:
                            if e is AD1['ent'] or e in AD2_list:
                                continue
                            if e.dxftype() == 'LINE' and getattr(e.dxf, 'layer', '') == 'ISOTEXT':
                                pts = extract_points(e)
                                if len(pts) == 2:
                                    L = calc_distance(pts[0], pts[1])
                                    if L > 1.0:
                                        found = False
                                        for ad1_pt in AD1['pts']:
                                            for p in pts:
                                                if calc_distance(ad1_pt, p) <= 0.1:
                                                    found = True; break
                                            if found: break
                                        if found:
                                            AD3 = {'ent': e, 'pts': pts}
                                            e.dxf.layer = 'AD3'
                                            e.dxf.color = RED
                                            break
                        if not AD3:
                            continue

                        # AP1/AP2
                        ad1_center = midpoint(AD1['pts'])
                        ap1 = min(AD3['pts'], key=lambda p: calc_distance(p, ad1_center))
                        ap2 = max(AD3['pts'], key=lambda p: calc_distance(p, ad1_center))

                        # CT: AP2 기준 범위, '-' 포함, rotation≈0
                        CT = None
                        for e in msp:
                            if e.dxftype() in ('TEXT','MTEXT'):
                                if e.dxftype() == 'TEXT':
                                    content = e.dxf.text
                                    pos = (e.dxf.insert.x, e.dxf.insert.y)
                                    rot = float(getattr(e.dxf, 'rotation', 0.0) or 0.0)
                                    if abs(rot) > 0.1:
                                        continue
                                else:
                                    content = e.text
                                    pos = (e.dxf.insert.x, e.dxf.insert.y)
                                if '-' in content:
                                    dx = pos[0]-ap2[0]; dy = pos[1]-ap2[1]
                                    if -70 <= dx <= 15 and -7 <= dy <= 7:
                                        CT = e
                                        try: e.dxf.color = RED
                                        except: pass
                                        break

                        a1_a2_info.append({
                            's1': rec1, 's2': rec2,
                            'a1': AD1,
                            'a2': AD3,
                            'ad2_list': AD2_list,
                            'ct': CT,
                            'center': center_sl1
                        })
                        # ⚠️ 요청사항: AD1/AD2/AD3/CT는 최종 삭제 대상에서 제외 → 삭제 목록에 추가하지 않음
                        break  # rec1당 한 쌍만

                # 2) CP/NODE/직교선 생성 루프
                texts_to_add = []
                for rec1 in list(s1_list):
                    for rec2 in list(s1_list):
                        if rec1 is rec2:
                            continue
                        if not hasattr(rec1['ent'], 'dxf') or not hasattr(rec2['ent'], 'dxf'):
                            continue

                        len1 = polyline_length(rec1['pts'])
                        len2 = polyline_length(rec2['pts'])
                        if abs(len1 - len2) > 0.2:
                            continue
                        all_dist = [calc_distance(a,b) for a in rec1['pts'] for b in rec2['pts']]
                        dmin = min(all_dist); dmax = max(all_dist)
                        if not (DMIN <= dmin <= DMAX and DMIN <= dmax <= DMAX):
                            continue
                        if any(calc_distance(p1, p2) <= 0.2 for p1 in rec1['pts'] for p2 in rec2['pts']):
                            continue

                        pts1, pts2 = rec1['pts'], rec2['pts']
                        center_sl1 = midpoint([midpoint(pts1), midpoint(pts2)])

                        # CP 원 (지름 0.5mm)
                        cp_circle = msp.add_circle(center=center_sl1, radius=HALF_SL1, dxfattribs={'color': CYAN})
                        cp_created_count += 1

                        # 직교선/노드 (OPTION B + 오프셋 fallback)
                        pipe_angle = get_pipe_angle(pts1, pts2)
                        orthogonal_lines, line_angles = create_iso_orthogonal_lines(center_sl1, pipe_angle, LINE_LENGTH, msp)

                        nodeno_pos, node_angle = find_best_orthogonal_position(
                            center_sl1, NODENO_OFFSET_Y, pipe_angle, msp, [cp_circle], line_angles
                        )
                        msp.add_circle(center=nodeno_pos, radius=NODENO_RADIUS, dxfattribs={'color': MAGENTA, 'layer': 'NODE'})

                        dx = nodeno_pos[0] - center_sl1[0]
                        dy = nodeno_pos[1] - center_sl1[1]
                        dist = math.hypot(dx, dy)
                        if dist > 0:
                            ux, uy = dx/dist, dy/dist
                            trim_end = (nodeno_pos[0] - ux*NODENO_RADIUS, nodeno_pos[1] - uy*NODENO_RADIUS)
                            msp.add_line(center_sl1, trim_end, dxfattribs={'color': WHITE, 'layer': 'NODE'})

                        texts_to_add.append(nodeno_pos)

                        # TYPE2 (CT 있는 경우만)
                        matching = None
                        for info in a1_a2_info:
                            if (info['s1']['ent'] == rec1['ent'] and info['s2']['ent'] == rec2['ent']) or \
                               (info['s1']['ent'] == rec2['ent'] and info['s2']['ent'] == rec1['ent']):
                                matching = info
                                break
                        if matching and matching.get('ct') is not None:
                            process_type2_support(msp, matching['a1'], matching['a2'], matching['ct'],
                                                  center_sl1, orthogonal_lines, line_angles,
                                                  pipe_angle, node_angle)

                        # 원래 S1 두 개 삭제(원래 흐름 유지)
                        try: msp.delete_entity(rec1['ent'])
                        except: pass
                        try: msp.delete_entity(rec2['ent'])
                        except: pass
                        break  # rec1에 대해 한 쌍만

                # 3) 특수(ELBO/TEE) 처리
                print("\n🔧 ELBO 및 TEE TEXT 특수 노드 처리 시작...")
                special_nodes_count = process_special_nodes(msp, doc)
                print(f"✅ 특수 노드 처리 완료: {special_nodes_count}개 노드 생성됨")

                # 4) NODE 텍스트 추가
                print("\n📝 텍스트 추가 시작...")
                text_count = 0
                for pos in texts_to_add:
                    if add_text_to_node(msp, pos, TEXT_VALUE, TEXT_HEIGHT, YELLOW, 'NODE', doc):
                        text_count += 1
                print(f"✅ {text_count}/{len(texts_to_add)}개 텍스트 추가 완료")

                # ⚠️ 요청사항: AD1/AD2/AD3/CT는 삭제하지 않음

            # ===== (B) Fallback: S1로 CP가 0건이면 C1/D1 경로 수행 =====
            if cp_created_count == 0 and c1_candidates:
                print("ℹ️ S1 경로에서 CP 생성 0건 → C1/D1 기반 fallback 실행")
                c1_to_delete = []
                d1_to_delete = []
                texts_to_add_fb = []

                for c1 in c1_candidates:
                    c1_ent = c1['ent']
                    center = c1['center']

                    c1_to_delete.append(c1_ent)

                    # (1) C1 중심 '통과' LINE 2개 찾기 → D1
                    d1_lines = find_lines_through_point(msp, center, tol=LINE_THROUGH_TOL)
                    for ln in d1_lines:
                        d1_to_delete.append(ln)

                    # (2) D1로 pipe 각도 추정(없으면 0도)
                    if len(d1_lines) >= 1:
                        pipe_angle = pipe_angle_from_two_lines(d1_lines)
                    else:
                        pipe_angle = 0.0

                    # (3) CP 원(지름 0.5mm) 생성
                    cp_circle = msp.add_circle(center=center, radius=HALF_SL1, dxfattribs={'color': CYAN})
                    cp_created_count += 1

                    # (4) 직교선/노드 (OPTION B + 오프셋 fallback)
                    orthogonal_lines, line_angles = create_iso_orthogonal_lines(center, pipe_angle, LINE_LENGTH, msp)
                    nodeno_pos, node_angle = find_best_orthogonal_position(
                        center, NODENO_OFFSET_Y, pipe_angle, msp, [], line_angles
                    )
                    msp.add_circle(center=nodeno_pos, radius=NODENO_RADIUS, dxfattribs={'color': MAGENTA, 'layer': 'NODE'})

                    # CP→NODE 연결
                    dx = nodeno_pos[0] - center[0]
                    dy = nodeno_pos[1] - center[1]
                    dist = math.hypot(dx, dy)
                    if dist > 0:
                        ux, uy = dx/dist, dy/dist
                        trim_end = (nodeno_pos[0] - ux*NODENO_RADIUS, nodeno_pos[1] - uy*NODENO_RADIUS)
                        msp.add_line(center, trim_end, dxfattribs={'color': WHITE, 'layer': 'NODE'})

                    texts_to_add_fb.append(nodeno_pos)

                # (5) 특수(ELBO/TEE) 처리
                print("\n🔧 (Fallback) ELBO/TEE 특수 노드 처리 시작...")
                special_nodes_count = process_special_nodes(msp, doc)
                print(f"✅ (Fallback) 특수 노드 처리 완료: {special_nodes_count}개 노드 생성됨")

                # (6) NODE 텍스트
                print("\n📝 (Fallback) 텍스트 추가 시작...")
                text_count = 0
                for pos in texts_to_add_fb:
                    if add_text_to_node(msp, pos, TEXT_VALUE, TEXT_HEIGHT, YELLOW, 'NODE', doc):
                        text_count += 1
                print(f"✅ (Fallback) {text_count}/{len(texts_to_add_fb)}개 텍스트 추가 완료")

                # (7) 요청 유지: C1/D1은 삭제(깨끗한 마무리)
                print("\n🗑️ (Fallback) C1/D1 삭제 시작...")
                del_cnt = 0
                for ent in c1_to_delete:
                    try:
                        msp.delete_entity(ent); del_cnt += 1
                    except:
                        pass
                for ent in d1_to_delete:
                    try:
                        msp.delete_entity(ent); del_cnt += 1
                    except:
                        pass
                print(f"✅ (Fallback) C1/D1 {del_cnt}개 엔티티 삭제 완료")

            # 저장
            out_path = os.path.splitext(filepath)[0] + '_SUPP.dxf'
            doc.saveas(out_path)
            print(f"✅ 저장됨: {out_path}")

        except Exception as e:
            print(f"❌ 오류 발생 @ {filepath}")
            traceback.print_exc(file=sys.stdout)

    print("🎉 전체 작업 완료")

if __name__ == '__main__':
    main()
