import ezdxf
import tkinter as tk
from tkinter import filedialog
import math
import os
from typing import List, Tuple, Optional, Dict, Set

# ==================== 타입/상수 ====================
Point = Tuple[float, float]

# AutoCAD 색상 인덱스
COLOR_YELLOW = 2
COLOR_CYAN = 4

# 탐지 파라미터 (사용자 지정값)
INST_LAYER = "GT_1"   # INST 후보 폴리라인 레이어
AD1_NEAR_R = 10.0     # AD1: INST 중심 반경
AD1_LEN_MAX = 50.0    # AD1: 총 길이 상한
AD1_VERT_COUNT_MIN = 3    # AD1: 최소 꼭짓점 수
AD1_VERT_COUNT_MAX = 4    # AD1: 최대 꼭짓점 수
AD1_MAX_PER_INST = 2      # INST 하나당 AD1 최대 개수

AD2_LAYER = "ARROW"   # AD2: LINE 레이어
AD2_LEN_MAX = 5.0     # AD2: LINE 길이 상한
AD2_NEAR_TOL = 1.0    # AD1 점 ↔ AD2 끝점 근접 허용

AD3_LAYER = "PL2"     # AD3: 폴리라인 레이어
AD3_TOUCH_TOL = 1.0   # AD1과 AD3 점 접촉 허용 오차
AD3_MAX_PER_AD1 = 2   # AD1 하나당 AD3 최대 매칭 수

AD4_LAYER = "PL2"     # AD4: LINE 레이어
AD4_NEAR_R = 10.0     # AD4: INST 중심 반경

VERIFY_BASENAME = "INDEL_verify_report"  # 검증 리포트 파일 접두어

# ==================== 공용 유틸 ====================

def hypot_xy(p: Point, q: Point) -> float:
    """두 점 사이의 거리"""
    return math.hypot(q[0] - p[0], q[1] - p[1])

def is_valid_entity(e) -> bool:
    """엔티티 dxf 접근 전 강력한 유효성 검사"""
    return bool(e) and hasattr(e, "dxf") and (e.dxf is not None)

def get_entity_color(e) -> Optional[int]:
    """엔티티의 색상 인덱스 반환"""
    if not is_valid_entity(e):
        return None
    try:
        return getattr(e.dxf, "color", None)
    except Exception:
        return None

def near(p: Point, q: Point, tol: float = 0.1) -> bool:
    return hypot_xy(p, q) <= tol

def seg_length_xy(p: Point, q: Point, bulge: float = 0.0) -> float:
    """bulge를 고려한 세그먼트 길이 계산"""
    c = hypot_xy(p, q)
    if not bulge:
        return c
    b = abs(float(bulge))
    theta = 4.0 * math.atan(b)
    R = c * (1 + b * b) / (4 * b)
    return R * theta

def bulge_to_radius_center(p: Point, q: Point, bulge: float):
    """bulge로부터 반지름과 중심 계산 (bulge>0: 반시계)"""
    if not bulge:
        return None, None
    x1, y1 = p
    x2, y2 = q
    dx, dy = x2 - x1, y2 - y1
    chord = math.hypot(dx, dy)
    if chord == 0:
        return None, None
    mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    b = float(bulge)
    theta = 4.0 * math.atan(abs(b))
    R = chord * (1 + b * b) / (4 * abs(b))
    ux, uy = -dy / chord, dx / chord
    s = R - (chord / (2 * math.tan(theta / 2.0)))
    sign = 1.0 if b > 0 else -1.0
    cx, cy = mx + sign * ux * s, my + sign * uy * s
    return R, (cx, cy)

def poly_vertices(e) -> Tuple[List[Tuple[float, float, float]], bool]:
    """(x,y,bulge) 리스트와 closed 여부 반환"""
    if not is_valid_entity(e):
        return [], False
    t = e.dxftype()
    if t == "LWPOLYLINE":
        pts = [(float(x), float(y), float(b or 0.0)) for x, y, b in e.get_points("xyb")]
        closed = bool(e.is_closed)
        return pts, closed
    elif t == "POLYLINE":
        pts = []
        for v in e.vertices:
            loc = v.dxf.location
            bulge = getattr(v.dxf, "bulge", 0.0) or 0.0
            pts.append((float(loc.x), float(loc.y), float(bulge)))
        closed = bool(e.is_closed)
        return pts, closed
    return [], False

def poly_total_length(e) -> float:
    pts, closed = poly_vertices(e)
    if len(pts) < 2:
        return 0.0
    L = 0.0
    for i in range(len(pts) - 1):
        p = (pts[i][0], pts[i][1])
        q = (pts[i + 1][0], pts[i + 1][1])
        L += seg_length_xy(p, q, pts[i][2])
    if closed:
        p = (pts[-1][0], pts[-1][1])
        q = (pts[0][0], pts[0][1])
        L += seg_length_xy(p, q, pts[-1][2])
    return L

def poly_has_radius_between(e, rmin=3.0, rmax=5.0):
    """폴리라인이 특정 반지름 범위의 호를 포함하는지 확인"""
    pts, closed = poly_vertices(e)
    if len(pts) < 2:
        return False, None, None
    segs = [(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    if closed:
        segs.append((pts[-1], pts[0]))
    for (x1, y1, b), (x2, y2, _b2) in segs:
        if b:
            R, C = bulge_to_radius_center((x1, y1), (x2, y2), b)
            if R is not None and rmin <= R <= rmax:
                return True, R, C
    return False, None, None

def entity_center_for_inst(e) -> Point:
    """엔티티의 중심점 계산: 호가 있으면 원호 중심, 없으면 평균"""
    ok, _R, C = poly_has_radius_between(e, 0.0, 1e12)
    if ok and C:
        return C
    pts, _ = poly_vertices(e)
    if not pts:
        return (0.0, 0.0)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (sum(xs) / len(xs), sum(ys) / len(ys))

def get_line_endpoints(ln) -> Tuple[Point, Point]:
    return (float(ln.dxf.start[0]), float(ln.dxf.start[1])), (float(ln.dxf.end[0]), float(ln.dxf.end[1]))

def text_in_rect_unrotated_T_keys(t, rect_min: Point, rect_max: Point) -> bool:
    """회전 거의 0°, TEXT 값에 T/P/I 계열 키 포함 여부"""
    if not is_valid_entity(t):
        return False
    ins = getattr(t.dxf, "insert", None)
    if ins is None:
        return False
    x, y = float(ins[0]), float(ins[1])
    if not (rect_min[0] <= x <= rect_max[0] and rect_min[1] <= y <= rect_max[1]):
        return False
    rot = float(getattr(t.dxf, "rotation", 0.0) or 0.0)
    if abs(rot) > 1e-2:
        return False
    val = (t.dxf.text or "").upper()
    keys = ("TT", "TI", "TE", "TP", "PI", "PP", "PE", "PT")
    return any(k in val for k in keys)

def safe_handle(e) -> Optional[str]:
    return e.dxf.handle if (is_valid_entity(e) and hasattr(e.dxf, "handle")) else None

# ==================== 소유 컨테이너 기반 삭제 유틸 ====================

def get_owner_layout(doc, e):
    """엔티티의 owner(레이아웃/블록 레코드)를 찾아 해당 엔티티 스페이스 컨테이너를 반환"""
    try:
        owner_handle = e.dxf.owner
    except Exception:
        return None
    if not owner_handle:
        return None
    owner = doc.entitydb.get(owner_handle)
    if owner is None:
        return None
    if owner.dxftype() == "BLOCK_RECORD":
        name = owner.dxf.name
        # Model/Paper 특수 이름
        if name == "*Model_Space":
            return doc.modelspace()
        elif name == "*Paper_Space":
            try:
                return doc.layout("*Paper_Space")
            except Exception:
                for lay in doc.layouts:
                    if lay.name != "Model":
                        return lay
                return None
        else:
            # 일반 블록
            return doc.blocks.get(name)
    return None

def hard_delete(doc, e, deleted: Set[str]) -> bool:
    """
    소유 컨테이너에서 안전 삭제 (BLOCK 내부/레이아웃 모두 지원).
    ⚠️ 반드시 '삭제 전'에 핸들과 타입을 캐싱하고, 삭제 후에는 e.dxf에 접근하지 않는다.
    """
    # 삭제 전 캐시
    try:
        etype = e.dxftype() if hasattr(e, "dxftype") else str(type(e))
    except Exception:
        etype = str(type(e))
    h = None
    try:
        if is_valid_entity(e) and hasattr(e.dxf, "handle"):
            h = e.dxf.handle
    except Exception:
        h = None

    # 중복 방지
    if h and h in deleted:
        return False

    try:
        owner_space = get_owner_layout(doc, e)
        if owner_space is not None:
            owner_space.delete_entity(e)  # 이후 e는 무효일 수 있음
        else:
            e.destroy()  # 최후 수단
        if h:
            deleted.add(h)
        return True
    except Exception as ex:
        msg_h = h if h is not None else "unknown"
        print(f"  [삭제 실패-hard] {etype} ({msg_h}): {ex}")
        return False

# ==================== 공통 쿼리 유틸 (검증/탐색용) ====================

def collect_all_spaces(doc):
    """ModelSpace, 모든 PaperSpace 레이아웃, 모든 Blocks 컨테이너를 반환"""
    spaces = [doc.modelspace()]
    for layout in doc.layouts:
        if layout.name != "Model":
            spaces.append(layout)
    for blk in doc.blocks:
        spaces.append(blk)
    return spaces

def all_query(doc, selector):
    """모든 스페이스에서 selector 쿼리"""
    for sp in collect_all_spaces(doc):
        try:
            for ent in sp.query(selector):
                if is_valid_entity(ent):
                    yield ent
        except Exception:
            continue

# ==================== INST별 관련 엔티티 찾기 ====================

def find_related_entities_for_inst(inst, center: Point, all_polys, all_lines, all_texts):
    """특정 INST에 대한 모든 관련 엔티티 찾기 (AD1, AD2, AD3, AD4, DEL1)"""
    cx, cy = center
    result = {
        "AD1": [],
        "AD2": [],
        "AD3": [],
        "AD4": [],
        "DEL1": []
    }
    
    # 1) AD1 찾기 (INST 근처의 작은 삼각형 폴리라인)
    # 색상 필터 추가: YELLOW(2) 제외, 최대 2개까지만 선택
    ad1_candidates = []
    for p in all_polys:
        if p is inst:
            continue
        if getattr(p.dxf, "layer", None) != INST_LAYER:
            continue
        
        # YELLOW 색상 제외
        color = get_entity_color(p)
        if color == COLOR_YELLOW:
            continue
            
        pts, _closed = poly_vertices(p)
        if len(pts) < AD1_VERT_COUNT_MIN or len(pts) > AD1_VERT_COUNT_MAX:
            continue
        if not pts:
            continue
        
        # 거리 계산
        min_dist = min(hypot_xy((cx, cy), (pt[0], pt[1])) for pt in pts)
        if min_dist > AD1_NEAR_R:
            continue
            
        if poly_total_length(p) > AD1_LEN_MAX + 1e-9:
            continue
            
        ad1_candidates.append((p, min_dist))
    
    # 거리순으로 정렬하여 가장 가까운 2개만 선택
    ad1_candidates.sort(key=lambda x: x[1])
    ad1_entities = [p[0] for p in ad1_candidates[:AD1_MAX_PER_INST]]
    
    result["AD1"] = ad1_entities
    
    # 2) AD2 찾기 (AD1과 연결된 화살표 선)
    ad2_entities = []
    for ad1 in ad1_entities:
        pts_ad1, _ = poly_vertices(ad1)
        if not pts_ad1:
            continue
        for ln in all_lines:
            if getattr(ln.dxf, "layer", None) != AD2_LAYER:
                continue
            p0, p1 = get_line_endpoints(ln)
            if hypot_xy(p0, p1) > AD2_LEN_MAX + 1e-9:
                continue
            if any(near((pt[0], pt[1]), p0, AD2_NEAR_TOL) or near((pt[0], pt[1]), p1, AD2_NEAR_TOL) for pt in pts_ad1):
                ad2_entities.append(ln)
    
    result["AD2"] = ad2_entities
    
    # 3) AD3 찾기 (AD1과 접촉하는 PL2 폴리라인)
    # 색상 필터 추가: CYAN(4) 제외
    ad3_entities = []
    pl2_polys = []
    for ent in all_polys:
        if getattr(ent.dxf, "layer", None) == AD3_LAYER:
            # CYAN 색상 제외
            color = get_entity_color(ent)
            if color != COLOR_CYAN:
                pl2_polys.append(ent)
    
    for ad1 in ad1_entities:
        pts_ad1, _ = poly_vertices(ad1)
        if not pts_ad1:
            continue
        matched = 0
        for p in pl2_polys:
            if matched >= AD3_MAX_PER_AD1:
                break
            pts_p, _ = poly_vertices(p)
            if not pts_p:
                continue
            touch = any(near((p1[0], p1[1]), (p2[0], p2[1]), AD3_TOUCH_TOL) for p1 in pts_ad1 for p2 in pts_p)
            if not touch:
                continue
            ad3_entities.append(p)
            matched += 1
    
    result["AD3"] = ad3_entities
    
    # 4) AD4 찾기 (INST 근처의 PL2 라인 중 가장 가까운 것)
    pl2_lines = [ln for ln in all_lines if getattr(ln.dxf, "layer", None) == AD4_LAYER]
    candidates = []
    for ln in pl2_lines:
        p0, p1 = get_line_endpoints(ln)
        min_dist = min(hypot_xy((cx, cy), p0), hypot_xy((cx, cy), p1))
        if min_dist <= AD4_NEAR_R:
            candidates.append((ln, min_dist))
    
    if candidates:
        candidates.sort(key=lambda x: x[1])
        result["AD4"] = [candidates[0][0]]  # 가장 가까운 것만
    
    # 5) DEL1 텍스트 찾기 - AD3와 AD1 쌍 재구성
    del1_texts = []
    for i, ad1 in enumerate(ad1_entities):
        pts_ad1, _ = poly_vertices(ad1)
        if not pts_ad1:
            continue
            
        # 이 AD1과 연결된 AD3 찾기
        for ad3 in ad3_entities:
            pts_ad3, _ = poly_vertices(ad3)
            if not pts_ad3:
                continue
                
            # AD1과 AD3가 접촉하는지 확인
            touch = any(near((p1[0], p1[1]), (p2[0], p2[1]), AD3_TOUCH_TOL) for p1 in pts_ad1 for p2 in pts_ad3)
            if not touch:
                continue

            def min_d_to_ad1(xy: Point) -> float:
                return min(hypot_xy(xy, (q[0], q[1])) for q in pts_ad1)

            dlist = [(min_d_to_ad1((pt[0], pt[1])), (pt[0], pt[1])) for pt in pts_ad3]
            dlist.sort(key=lambda x: x[0])
            AP2 = dlist[-1][1]  # 가장 먼 점

            rect_min = (AP2[0] - 60.0, AP2[1] - 7.0)
            rect_max = (AP2[0] + 15.0, AP2[1] + 7.0)

            for t in all_texts:
                if text_in_rect_unrotated_T_keys(t, rect_min, rect_max):
                    del1_texts.append(t)
    
    result["DEL1"] = del1_texts
    
    return result

# ==================== 메인 처리 ====================

def process_dxf_file(filepath: str) -> bool:
    try:
        print(f"[INFO] Processing: {os.path.basename(filepath)}")
        doc = ezdxf.readfile(filepath)
        msp = doc.modelspace()

        # 필요 레이어가 없으면 생성 (삭제 자체에는 영향 없음)
        for layer_name in ("INST", "AD1", "AD2", "AD3", "AD4", "DEL1"):
            if layer_name not in doc.layers:
                doc.layers.add(layer_name)

        # ---------- 1) INST 찾기 ----------
        inst_entities: List[Tuple[object, Point]] = []
        for e in msp.query("LWPOLYLINE POLYLINE"):
            if not is_valid_entity(e):
                continue
            if e.dxf.layer != INST_LAYER:
                continue
            ok, R, C = poly_has_radius_between(e, 3.0, 5.0)
            if not ok:
                continue
            center = C if C else entity_center_for_inst(e)
            inst_entities.append((e, center))
        
        print(f"INST 엔티티: {len(inst_entities)}개")

        # 후보 모음 (모든 공간)
        all_polys = list(all_query(doc, "LWPOLYLINE POLYLINE"))
        all_lines = list(all_query(doc, "LINE"))
        all_texts = list(all_query(doc, "TEXT"))

        # ---------- 2) 각 INST별로 관련 엔티티 찾기 ----------
        all_to_delete = {
            "INST": [],
            "AD1": [],
            "AD2": [],
            "AD3": [],
            "AD4": [],
            "DEL1": []
        }
        
        # INST 엔티티 추가
        for inst, _ in inst_entities:
            all_to_delete["INST"].append(inst)
        
        print("\n=== 각 INST별 관련 엔티티 찾기 ===")
        print(f"[색상 필터] AD1: YELLOW 제외, 최대 {AD1_MAX_PER_INST}개 선택")
        print(f"[색상 필터] AD3: CYAN 제외")
        
        for inst_idx, (inst, center) in enumerate(inst_entities):
            print(f"\n[INST #{inst_idx + 1}/{len(inst_entities)}]")
            print(f"  중심좌표: ({center[0]:.2f}, {center[1]:.2f})")
            
            # 이 INST에 대한 관련 엔티티 찾기
            related = find_related_entities_for_inst(inst, center, all_polys, all_lines, all_texts)
            
            # 각 카테고리별로 삭제 대상에 추가
            for category, entities in related.items():
                all_to_delete[category].extend(entities)
                if entities:
                    print(f"  {category}: {len(entities)}개 찾음")

        # 고유 엔티티만 남기기 (중복 제거)
        unique_to_delete = {}
        for category, entities in all_to_delete.items():
            unique_handles = set()
            unique_entities = []
            for e in entities:
                h = safe_handle(e) or str(id(e))
                if h not in unique_handles:
                    unique_handles.add(h)
                    unique_entities.append(e)
            unique_to_delete[category] = unique_entities

        print("\n=== 삭제 대상 요약 (중복 제거) ===")
        for category, entities in unique_to_delete.items():
            print(f"{category}: {len(entities)}개")

        # ---------- 3) 삭제 실행 ----------
        deleted_handles: Set[str] = set()
        
        # 연관선(AD2/3/4) → 보조도형(AD1) → 텍스트(DEL1) → 본체(INST) 순서로 삭제
        cnt_ad2 = sum(1 for e in unique_to_delete["AD2"] if hard_delete(doc, e, deleted_handles))
        cnt_ad3 = sum(1 for e in unique_to_delete["AD3"] if hard_delete(doc, e, deleted_handles))
        cnt_ad4 = sum(1 for e in unique_to_delete["AD4"] if hard_delete(doc, e, deleted_handles))
        cnt_ad1 = sum(1 for e in unique_to_delete["AD1"] if hard_delete(doc, e, deleted_handles))
        cnt_del1 = sum(1 for e in unique_to_delete["DEL1"] if hard_delete(doc, e, deleted_handles))
        cnt_inst = sum(1 for e in unique_to_delete["INST"] if hard_delete(doc, e, deleted_handles))

        total_deleted = cnt_ad2 + cnt_ad3 + cnt_ad4 + cnt_ad1 + cnt_del1 + cnt_inst
        print(
            f"\n삭제 결과: AD2 {cnt_ad2}, AD3 {cnt_ad3}, AD4 {cnt_ad4}, AD1 {cnt_ad1}, "
            f"DEL1 {cnt_del1}, INST {cnt_inst} -> 총 {total_deleted}개"
        )

        # ---------- 4) 검증 ----------
        base_name = os.path.splitext(os.path.basename(filepath))[0]
        dir_name = os.path.dirname(filepath)

        # ---------- 5) 저장 ----------
        new_filename = os.path.join(dir_name, f"{base_name}_INDEL.DXF")
        doc.saveas(new_filename)
        print(f"[OK] Saved: {new_filename}")

        return True

    except Exception as e:
        print(f"[ERROR] {os.path.basename(filepath)}: {e}")
        import traceback
        traceback.print_exc()
        return False

# ==================== 검증(remaining scan) ====================

def verify_remaining(doc, report_path: str) -> None:
    """삭제 후 남은 타깃 엔티티를 재스캔하여 수량/핸들 리포트 저장"""
    # INST
    inst_left = []
    for e in all_query(doc, "LWPOLYLINE POLYLINE"):
        if getattr(e.dxf, "layer", None) == INST_LAYER:
            ok, R, C = poly_has_radius_between(e, 3.0, 5.0)
            if ok:
                inst_left.append(safe_handle(e))

    # AD1 (근사 스캔: GT_1 / 꼭짓점 3-4 / 총길이<=50 / YELLOW 제외)
    ad1_left = []
    for e in all_query(doc, "LWPOLYLINE POLYLINE"):
        if getattr(e.dxf, "layer", None) == INST_LAYER:
            color = get_entity_color(e)
            if color == COLOR_YELLOW:
                continue
            pts, _ = poly_vertices(e)
            if AD1_VERT_COUNT_MIN <= len(pts) <= AD1_VERT_COUNT_MAX and poly_total_length(e) <= AD1_LEN_MAX + 1e-9:
                ad1_left.append(safe_handle(e))

    # AD2 (ARROW, 길이<=5)
    ad2_left = []
    for ln in all_query(doc, "LINE"):
        if getattr(ln.dxf, "layer", None) == AD2_LAYER:
            p0 = (float(ln.dxf.start[0]), float(ln.dxf.start[1]))
            p1 = (float(ln.dxf.end[0]), float(ln.dxf.end[1]))
            if hypot_xy(p0, p1) <= AD2_LEN_MAX + 1e-9:
                ad2_left.append(safe_handle(ln))

    # AD3 (PL2 폴리라인, CYAN 제외)
    ad3_left = []
    for e in all_query(doc, "LWPOLYLINE POLYLINE"):
        if getattr(e.dxf, "layer", None) == AD3_LAYER:
            color = get_entity_color(e)
            if color != COLOR_CYAN:
                ad3_left.append(safe_handle(e))
    
    # AD4 (PL2 라인)
    ad4_left = [safe_handle(e) for e in all_query(doc, "LINE") if getattr(e.dxf, "layer", None) == AD4_LAYER]

    # DEL1 (T/P/I 키 포함 TEXT)
    def text_has_keys(t):
        val = (t.dxf.text or "").upper()
        keys = ("TT","TI","TE","TP","PI","PP","PE","PT")
        return any(k in val for k in keys)
    del1_left = [safe_handle(t) for t in all_query(doc, "TEXT") if text_has_keys(t)]

    print("[VERIFY] 남은 엔티티 수:",
          f"INST {len(inst_left)}, AD1 {len(ad1_left)}, AD2 {len(ad2_left)}, AD3 {len(ad3_left)}, AD4 {len(ad4_left)}, DEL1 {len(del1_left)}")

    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("==== 삭제 후 남은 엔티티(핸들 기준) ====\n")
            f.write(f"INST({len(inst_left)}): {inst_left}\n")
            f.write(f"AD1({len(ad1_left)}): {ad1_left}\n")
            f.write(f"AD2({len(ad2_left)}): {ad2_left}\n")
            f.write(f"AD3({len(ad3_left)}): {ad3_left}\n")
            f.write(f"AD4({len(ad4_left)}): {ad4_left}\n")
            f.write(f"DEL1({len(del1_left)}): {del1_left}\n")
        print(f"[VERIFY] 리포트 저장: {report_path}")
    except Exception as ex:
        print(f"[VERIFY] 리포트 저장 실패: {ex}")

# ==================== 진입점 ====================

def main():
    root = tk.Tk()
    root.withdraw()
    filepaths = filedialog.askopenfilenames(
        title="DXF 파일 선택",
        filetypes=[("DXF files", "*.dxf"), ("All files", "*.*")]
    )
    if not filepaths:
        print("[CANCEL] 파일이 선택되지 않았습니다.")
        return
    for filepath in filepaths:
        try:
            process_dxf_file(filepath)
        except Exception as e:
            print(f"[ERROR] {os.path.basename(filepath)}: {e}")

if __name__ == "__main__":
    main()
    