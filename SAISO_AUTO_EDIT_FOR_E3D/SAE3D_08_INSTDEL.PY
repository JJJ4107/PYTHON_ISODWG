import ezdxf
import tkinter as tk
from tkinter import filedialog
import math
import os
from typing import List, Tuple, Optional, Dict, Set

# ==================== 타입/상수 ====================
Point = Tuple[float, float]

# 탐지 파라미터 (필요시 조정)
INST_LAYER = "GT_1"   # INST 후보 폴리라인 레이어
AD1_NEAR_R = 5.0      # AD1: INST 중심 반경
AD1_LEN_MAX = 5.0     # AD1: 총 길이 상한
AD1_VERT_COUNT = 3    # AD1: 꼭짓점 수

AD2_LAYER = "ARROW"   # AD2: LINE 레이어
AD2_LEN_MAX = 1.0     # AD2: LINE 길이 상한
AD2_NEAR_TOL = 0.1    # AD1 점 ↔ AD2 끝점 근접 허용

AD3_LAYER = "PL2"     # AD3: 폴리라인 레이어
AD3_TOUCH_TOL = 0.1   # AD1과 AD3 점 접촉 허용 오차
AD3_MAX_PER_AD1 = 2   # AD1 하나당 AD3 최대 매칭 수

AD4_LAYER = "PL2"     # AD4: LINE 레이어
AD4_NEAR_R = 5.0      # AD4: INST 중심 반경

CYAN_COLOR = 4        # CYAN 색상 인덱스

# ==================== 공용 유틸 ====================

def hypot_xy(p: Point, q: Point) -> float:
    """두 점 사이의 거리"""
    return math.hypot(q[0] - p[0], q[1] - p[1])

def is_valid_entity(e) -> bool:
    """엔티티 dxf 접근 전 강력한 유효성 검사"""
    return bool(e) and hasattr(e, "dxf") and (e.dxf is not None)

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

# ==================== 레이어 및 색상 변경 ====================

def change_entity_layer_color(e, new_layer: str, color_index: int = CYAN_COLOR):
    """엔티티의 레이어와 색상을 변경"""
    if is_valid_entity(e):
        try:
            e.dxf.layer = new_layer
            e.dxf.color = color_index
            return True
        except Exception as ex:
            print(f"  [변경 실패] {e.dxftype()}: {ex}")
            return False
    return False

# ==================== 공통 쿼리 유틸 ====================

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
    
    # 1) AD1 찾기 (INST 근처의 작은 삼각형 폴리라인) - 원래 레이어만 체크
    ad1_entities = []
    for p in all_polys:
        if p is inst:
            continue
        if getattr(p.dxf, "layer", None) != INST_LAYER:  # 원래 레이어만!
            continue
        pts, _closed = poly_vertices(p)
        if len(pts) != AD1_VERT_COUNT:
            continue
        if not pts:
            continue
        if not any(hypot_xy((cx, cy), (pt[0], pt[1])) <= AD1_NEAR_R for pt in pts):
            continue
        if poly_total_length(p) > AD1_LEN_MAX + 1e-9:
            continue
        ad1_entities.append(p)
    
    result["AD1"] = ad1_entities
    
    # 2) AD2 찾기 (AD1과 연결된 화살표 선) - 원래 레이어만 체크
    ad2_entities = []
    for ad1 in ad1_entities:
        pts_ad1, _ = poly_vertices(ad1)
        if not pts_ad1:
            continue
        for ln in all_lines:
            if getattr(ln.dxf, "layer", None) != AD2_LAYER:  # 원래 레이어만!
                continue
            p0, p1 = get_line_endpoints(ln)
            if hypot_xy(p0, p1) > AD2_LEN_MAX + 1e-9:
                continue
            if any(near((pt[0], pt[1]), p0, AD2_NEAR_TOL) or near((pt[0], pt[1]), p1, AD2_NEAR_TOL) for pt in pts_ad1):
                if ln not in ad2_entities:  # 중복 방지
                    ad2_entities.append(ln)
    
    result["AD2"] = ad2_entities
    
    # 3) AD3 찾기 (AD1과 접촉하는 PL2 폴리라인) - 원래 레이어만 체크
    ad3_pairs = []  # (AD3 poly, AD1)
    pl2_polys = [ent for ent in all_polys if getattr(ent.dxf, "layer", None) == AD3_LAYER]  # 원래 레이어만!
    
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
            ad3_pairs.append((p, ad1))
            matched += 1
    
    result["AD3"] = [p for p, _ in ad3_pairs]
    
    # 4) AD4 찾기 (INST 근처의 PL2 라인 중 가장 가까운 것) - 원래 레이어만 체크
    pl2_lines = [ln for ln in all_lines if getattr(ln.dxf, "layer", None) == AD4_LAYER]  # 원래 레이어만!
    candidates = []
    for ln in pl2_lines:
        p0, p1 = get_line_endpoints(ln)
        min_dist = min(hypot_xy((cx, cy), p0), hypot_xy((cx, cy), p1))
        if min_dist <= AD4_NEAR_R:
            candidates.append((ln, min_dist))
    
    if candidates:
        candidates.sort(key=lambda x: x[1])
        result["AD4"] = [candidates[0][0]]  # 가장 가까운 것만
    
    # 5) DEL1 텍스트 찾기
    del1_texts = []
    for p_ad3, ad1 in ad3_pairs:
        pts_ad3, _ = poly_vertices(p_ad3)
        pts_ad1, _ = poly_vertices(ad1)
        if not pts_ad3 or not pts_ad1:
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
                if t not in del1_texts:  # 중복 방지
                    del1_texts.append(t)
    
    result["DEL1"] = del1_texts
    
    return result

# ==================== 메인 처리 ====================

def process_dxf_file(filepath: str) -> bool:
    try:
        print(f"[INFO] Processing: {os.path.basename(filepath)}")
        doc = ezdxf.readfile(filepath)
        msp = doc.modelspace()

        # 레이어가 없으면 생성하고 CYAN 색상 설정
        target_layers = ["INST", "AD1", "AD2", "AD3", "AD4", "DEL1"]
        for layer_name in target_layers:
            if layer_name not in doc.layers:
                new_layer = doc.layers.add(layer_name)
                new_layer.color = CYAN_COLOR
            else:
                # 기존 레이어의 색상도 CYAN으로 변경
                doc.layers.get(layer_name).color = CYAN_COLOR

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

        # ---------- 2) 모든 INST에 대해 관련 엔티티 찾기 (변경하지 않고) ----------
        # 엔티티와 카테고리를 매핑 (같은 엔티티가 여러 카테고리에 속할 수 있음)
        entity_changes = {}  # {entity_handle: category}
        
        # 모든 INST 등록
        for inst, _ in inst_entities:
            h = safe_handle(inst) or str(id(inst))
            entity_changes[h] = "INST"
        
        # 각 INST별 관련 엔티티 수집
        inst_related_entities = []  # 각 INST별 관련 엔티티 정보 저장
        
        for inst_idx, (inst, center) in enumerate(inst_entities):
            print(f"\n분석중 INST #{inst_idx + 1}/{len(inst_entities)}")
            
            # 이 INST에 대한 관련 엔티티 찾기
            related = find_related_entities_for_inst(inst, center, all_polys, all_lines, all_texts)
            inst_related_entities.append(related)
            
            # 각 카테고리별로 저장 (같은 엔티티가 여러 INST에 연관될 수 있음)
            for category, entities in related.items():
                for e in entities:
                    h = safe_handle(e) or str(id(e))
                    # 기존 카테고리와 다르면 우선순위에 따라 결정
                    # 우선순위: DEL1 > AD4 > AD3 > AD2 > AD1
                    priority = {"AD1": 1, "AD2": 2, "AD3": 3, "AD4": 4, "DEL1": 5}
                    if h not in entity_changes or priority.get(category, 0) > priority.get(entity_changes.get(h), 0):
                        entity_changes[h] = category
            
            # 이 INST에 대한 결과 출력
            counts_str = ", ".join([f"{cat}:{len(ents)}" for cat, ents in related.items() if ents])
            if counts_str:
                print(f"  -> 찾은 엔티티: {counts_str}")
        
        # 카테고리별로 엔티티 정리
        all_changes = {
            "INST": [],
            "AD1": [],
            "AD2": [],
            "AD3": [],
            "AD4": [],
            "DEL1": []
        }
        
        # INST 엔티티 추가
        for inst, _ in inst_entities:
            all_changes["INST"].append(inst)
        
        # 각 INST에서 찾은 모든 엔티티 추가 (중복 포함)
        for related in inst_related_entities:
            for category, entities in related.items():
                all_changes[category].extend(entities)

        # ---------- 3) 모든 엔티티의 레이어와 색상을 한 번에 변경 ----------
        print("\n=== 레이어/색상 변경 시작 ===")
        
        # 실제 변경할 고유 엔티티들 (중복 제거)
        unique_entities = {}  # {handle: (entity, category)}
        changed_counts = {
            "INST": 0,
            "AD1": 0,
            "AD2": 0,
            "AD3": 0,
            "AD4": 0,
            "DEL1": 0
        }
        
        # 찾은 엔티티 수 (중복 포함)
        found_counts = {category: len(entities) for category, entities in all_changes.items()}
        
        # 고유 엔티티 추출 및 변경
        for category, entities in all_changes.items():
            for e in entities:
                h = safe_handle(e) or str(id(e))
                if h not in unique_entities:
                    unique_entities[h] = (e, category)
                    if change_entity_layer_color(e, category, CYAN_COLOR):
                        changed_counts[category] += 1

        # ---------- 4) 변경 결과 요약 ----------
        print("\n=== 레이어/색상 변경 결과 ===")
        print("카테고리 | 찾은 수(중복포함) | 변경한 수(고유)")
        print("-" * 50)
        for category in ["INST", "AD1", "AD2", "AD3", "AD4", "DEL1"]:
            found = found_counts.get(category, 0)
            changed = changed_counts.get(category, 0)
            print(f"{category:8} | {found:17} | {changed:11}")
        
        total_found = sum(found_counts.values())
        total_changed = sum(changed_counts.values())
        print("-" * 50)
        print(f"{'총계':8} | {total_found:17} | {total_changed:11}")

        # ---------- 5) 저장 ----------
        base_name = os.path.splitext(os.path.basename(filepath))[0]
        dir_name = os.path.dirname(filepath)
        new_filename = os.path.join(dir_name, f"{base_name}_LAYER_CHANGED.DXF")
        doc.saveas(new_filename)
        print(f"\n[OK] Saved: {new_filename}")

        return True

    except Exception as e:
        print(f"[ERROR] {os.path.basename(filepath)}: {e}")
        import traceback
        traceback.print_exc()
        return False

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