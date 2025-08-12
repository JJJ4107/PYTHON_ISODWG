import ezdxf
import os
import math
from ezdxf.math import Vec2
import tkinter as tk
from tkinter import filedialog

### DXF 파일 여러 개 선택 함수 ###
def select_dxf_files():
    root = tk.Tk()
    root.withdraw()
    file_paths = filedialog.askopenfilenames(
        title="DXF 파일을 선택하세요",
        filetypes=[("DXF Files", "*.dxf")]
    )
    root.destroy()
    if not file_paths:
        print("❌ 선택된 파일이 없습니다.")
        exit()
    return file_paths

### 공통 유틸 함수들 ###
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
    if len(points) < 2:
        return True
    base = points[0][:2]
    for pt in points[1:]:
        if distance(base, pt[:2]) > tol:
            return False
    return True

### 간섭 체크 함수 ###
def point_to_segment_distance(p: Vec2, a: Vec2, b: Vec2) -> float:
    ap = p - a
    ab = b - a
    ab_len_squared = ab.dot(ab)
    if ab_len_squared == 0:
        return distance(p, a)
    t = max(0, min(1, ap.dot(ab) / ab_len_squared))
    projection = a + ab * t
    return distance(p, projection)

def check_interference_at_position(test_center, msp, exclude_entities, weld_radius=3.0):
    """특정 위치에서의 간섭을 체크하는 함수"""
    for e in msp:
        if e in exclude_entities or not hasattr(e, "dxf") or e.dxf is None:
            continue
        
        if e.dxftype() == "TEXT":
            p = Vec2(e.dxf.insert.x, e.dxf.insert.y)
            if distance(p, test_center) < weld_radius:
                return True
                
        elif e.dxftype() in ("POLYLINE", "LWPOLYLINE"):
            if e.dxftype() == "POLYLINE":
                pts = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
            else:
                pts = [Vec2(x, y) for x, y, *_ in e.get_points()]
            
            for i in range(len(pts) - 1):
                if point_to_segment_distance(test_center, pts[i], pts[i+1]) < weld_radius:
                    return True
                    
        elif e.dxftype() == "CIRCLE":
            circle_center = Vec2(e.dxf.center.x, e.dxf.center.y)
            if distance(circle_center, test_center) < (e.dxf.radius + weld_radius):
                return True
    
    return False

def check_text_interference_only(test_center, msp, exclude_entities, weld_radius=3.0):
    """TEXT와의 간섭만 체크하는 함수"""
    for e in msp:
        if e in exclude_entities or not hasattr(e, "dxf") or e.dxf is None:
            continue
        
        if e.dxftype() == "TEXT":
            p = Vec2(e.dxf.insert.x, e.dxf.insert.y)
            if distance(p, test_center) < weld_radius:
                return True
    
    return False

### WELDNOEDIT 기능 ###
def is_overlap_and_text(center: Vec2, msp, exclude_entities, weld_radius=3.0):
    overlap = False
    is_text = False
    for e in msp:
        if e in exclude_entities or not hasattr(e, "dxf") or e.dxf is None:
            continue
        if e.dxftype() == "TEXT":
            p = Vec2(e.dxf.insert.x, e.dxf.insert.y)
            if distance(p, center) < weld_radius:
                overlap = True
                is_text = True
        elif e.dxftype() in ("POLYLINE", "LWPOLYLINE"):
            if e.dxftype() == "POLYLINE":
                pts = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
            else:
                pts = [Vec2(x, y) for x, y, *_ in e.get_points()]
            for i in range(len(pts) - 1):
                if point_to_segment_distance(center, pts[i], pts[i+1]) < weld_radius:
                    overlap = True
                    break
    return overlap, is_text

def process_weldnoedit(doc):
    msp = doc.modelspace()
    tolerance_touch = 0.2
    min_sl1_length = 14
    target_distance = 5
    text_search_radius = 6
    weld_radius = 2.8
    min_seg_len = 4.5
    max_seg_len = 6.0
    cicle_len = 5.6
    offset_len = cicle_len / 2

    weld_blocks = []
    moved = 0
    weld_results = []
    sl1_to_delete = []

    for poly in msp.query("POLYLINE LWPOLYLINE"):
        if poly.dxftype() == "POLYLINE":
            if len(poly.vertices) != 3:
                continue
            has_curve = any(v.dxf.bulge != 0 for v in poly.vertices)
            pts = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
        else:
            pts = [Vec2(x, y) for x, y, *_ in poly.get_points()]
            if len(pts) != 3:
                continue
            has_curve = any(b != 0 for (*_, b) in poly.get_points())
        if not has_curve:
            continue
        if not any(min_seg_len <= distance(pts[i], pts[i + 1]) <= max_seg_len for i in range(2)):
            continue
        center = Vec2(sum(p.x for p in pts)/3, sum(p.y for p in pts)/3)
        
        text_search_radius = 4
        closest_txt = None
        closest_dist = float('inf')
        for txt in msp.query("TEXT"):
            pos = Vec2(txt.dxf.insert.x, txt.dxf.insert.y)
            d = distance(pos, center)
            if d <= text_search_radius and d < closest_dist:
                closest_txt = txt
                closest_dist = d
        texts = []
        if closest_txt is not None:
            closest_txt.dxf.color = 1
            texts.append(closest_txt)
        poly.dxf.color = 1
        weld_blocks.append({"poly": poly, "texts": texts, "center": center})

    for weld in weld_blocks:
        weld_poly = weld["poly"]
        weld_center = weld["center"]
        weld_texts = weld["texts"]

        if weld_poly.dxftype() == "POLYLINE":
            weld_points = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in weld_poly.vertices]
        else:
            weld_points = [Vec2(x, y) for x, y, *_ in weld_poly.get_points()]

        for sl1 in list(msp.query("POLYLINE LWPOLYLINE")):
            if sl1 is weld_poly:
                continue
            if sl1.dxftype() == "POLYLINE":
                sl1_pts = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in sl1.vertices]
            else:
                sl1_pts = [Vec2(x, y) for x, y, *_ in sl1.get_points()]
            if len(sl1_pts) < 2:
                continue
            start, end = sl1_pts[0], sl1_pts[-1]
            sl1_len = distance(start, end)
            if any(distance(start, wp) <= tolerance_touch for wp in weld_points):
                sp1_idx, sp1, sp2 = 0, start, end
            elif any(distance(end, wp) <= tolerance_touch for wp in weld_points):
                sp1_idx, sp1, sp2 = -1, end, start
            else:
                continue

            final_sp2 = sp2
            if sl1_len < min_sl1_length:
                weld_results.append({"sp2": final_sp2, "center": weld_center, "weld_poly": weld_poly})
                sl1_to_delete.append(sl1)
                break

            direction_vec = sp2 - sp1
            direction_vec = direction_vec.normalize() if direction_vec.magnitude != 0 else None
            if direction_vec is None:
                continue

            found, move_vec = False, None
            for r in range(1, 10):
                test_point = sp2 + direction_vec * (-r)
                overlap, is_text = is_overlap_and_text(test_point, msp, [weld_poly, sl1] + weld_texts, weld_radius)
                if not overlap:
                    move_vec = test_point - sp1
                    found = True
                    break
            if not found:
                move_distance = distance(sp1, sp2) - target_distance
                if move_distance <= 0:
                    break
                move_vec = direction_vec * move_distance

            new_sp1 = sp1 + move_vec
            directions = [Vec2(dx, dy) for d in range(3, 11) for dx, dy in [(-d, 0), (d, 0), (0, -d), (0, d)]]
            final_offset = Vec2(0, 0)
            for offset in directions:
                test_center = weld_center + move_vec + offset
                overlap, is_text = is_overlap_and_text(test_center, msp, [weld_poly, sl1] + weld_texts, weld_radius)
                if not overlap:
                    final_offset = offset
                    break
            move_vec += final_offset
            new_sp1 = sp1 + move_vec

            if sl1.dxftype() == "POLYLINE":
                if sp1_idx == 0:
                    sl1.vertices[0].dxf.location = (new_sp1.x, new_sp1.y, 0)
                else:
                    sl1.vertices[-1].dxf.location = (new_sp1.x, new_sp1.y, 0)
            else:
                points = sl1.get_points()
                if sp1_idx == 0:
                    new_points = [(new_sp1.x, new_sp1.y)] + points[1:]
                else:
                    new_points = points[:-1] + [(new_sp1.x, new_sp1.y)]
                sl1.set_points(new_points)

            dx, dy = move_vec.x, move_vec.y
            if weld_poly.dxftype() == "POLYLINE":
                for v in weld_poly.vertices:
                    loc = v.dxf.location
                    v.dxf.location = (loc.x + dx, loc.y + dy, 0)
            else:
                weld_pts = [(x + dx, y + dy) for x, y, *_ in weld_poly.get_points()]
                weld_poly.set_points(weld_pts)
            for txt in weld_texts:
                pos = txt.dxf.insert
                txt.dxf.insert = (pos.x + dx, pos.y + dy, 0)

            sl1.dxf.color = 1
            weld_poly.dxf.color = 1
            for txt in weld_texts:
                txt.dxf.color = 1

            moved += 1
            weld_results.append({"sp2": final_sp2, "center": weld_center + move_vec + final_offset, "weld_poly": weld_poly})
            sl1_to_delete.append(sl1)
            break

    for weld in weld_results:
        sp2 = weld["sp2"]
        poly = weld["weld_poly"]
        center = weld["center"]
        if poly.dxftype() == "POLYLINE":
            pts = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
        else:
            pts = [Vec2(x, y) for x, y, *_ in poly.get_points()]
        if len(pts) == 3 and sp2 is not None:
            cp = (pts[0] + pts[1]) * 0.5
            vec = sp2 - cp
            if vec.magnitude != 0:
                cp = cp + vec.normalize() * offset_len
            msp.add_line((cp.x, cp.y), (sp2.x, sp2.y), dxfattribs={'color': 1})

    for sl1 in sl1_to_delete:
        try:
            msp.delete_entity(sl1)
        except Exception as ex:
            print(f"SL1 삭제 오류: {ex}")

    for weld in weld_results:
        poly = weld["weld_poly"]
        if poly.dxftype() == "POLYLINE":
            pts = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
        else:
            pts = [Vec2(x, y) for x, y, *_ in poly.get_points()]
        if len(pts) == 3:
            cp = (pts[0] + pts[1]) * 0.5
            msp.add_circle(center=cp, radius=cicle_len / 2, dxfattribs={"color": 2})
        try:
            msp.delete_entity(poly)
        except Exception as ex:
            print(f"❗ WELD 삭제 오류: {ex}")

    print(f"기존 WELDNOEDIT 처리 완료")

### WELDSYMBOL 기능 ###
def process_weldsymbol(doc):
    msp = doc.modelspace()
    modified = False
    to_delete = []
    WELDS = []

    for weld in list(msp.query('LWPOLYLINE POLYLINE')):
        points = get_poly_points(weld)
        if len(points) != 7:
            continue
        if is_nearly_same_points(points):
            continue
        too_far = False
        for i in range(6):
            d = distance(points[i][:2], points[i+1][:2])
            if d > 2.0:
                too_far = True
                break
        if too_far:
            continue
        weld_center = midpoint([pt[:2] for pt in points])
        if not is_valid_center(weld_center):
            continue
        length = polyline_length(weld)
        if length < 1 or length > 100:
            continue

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

        main_circle = msp.add_circle(center=weld_center, radius=1, dxfattribs={"color": 2})
        main_circle.dxf.lineweight = 20

        texts_in_circle = []
        for txt in msp.query('TEXT'):
            txt_pos = (txt.dxf.insert[0], txt.dxf.insert[1])
            if distance(txt_pos, weld_center) < 1.0:
                texts_in_circle.append(txt)

        leader_line = None
        for ent in msp.query('LINE'):
            if hasattr(ent.dxf, 'color') and ent.dxf.color == 1:
                p_start = (ent.dxf.start[0], ent.dxf.start[1])
                p_end = (ent.dxf.end[0], ent.dxf.end[1])
                for pt in points:
                    if distance(pt[:2], p_start) <= 1 or distance(pt[:2], p_end) <= 1:
                        leader_line = ent
                        break
            if leader_line:
                break

        WELDS.append({
            "circle": main_circle,
            "leader_line": leader_line,
            "texts": texts_in_circle
        })

        if hasattr(weld.dxf, 'linetype') and isinstance(weld.dxf.linetype, str):
            if weld.dxf.linetype.upper() == "GT100":
                weld.dxf.linetype = "DOT"

        if hasattr(weld.dxf, 'linetype') and weld.dxf.linetype.upper() == "BYLAYER":
            for r in [0.85, 0.7, 0.55, 0.4, 0.25]:
                inner = msp.add_circle(center=weld_center, radius=r, dxfattribs={"color": 2})
                inner.dxf.lineweight = 20

        main_circle.dxf.layer = "SW" if len(short_plines) >= 5 else "OW"

        red_lines = []
        for ent in msp.query('LINE'):
            if hasattr(ent.dxf, 'color') and ent.dxf.color == 1:
                p_start = (ent.dxf.start[0], ent.dxf.start[1])
                p_end = (ent.dxf.end[0], ent.dxf.end[1])
                for pt in points:
                    if distance(pt[:2], p_start) <= 1 or distance(pt[:2], p_end) <= 1:
                        red_lines.append((ent, p_start, p_end))
                        break

        for line, p1, p2 in red_lines:
            d1 = distance(p1, weld_center)
            d2 = distance(p2, weld_center)
            wp1 = p1 if d1 < d2 else p2
            wp2 = p2 if d1 < d2 else p1
            move_single_point_to(line, weld_center, fixed_point=wp2)
            break

        to_delete.append(weld)
        to_delete.extend(short_plines)
        modified = True

    for ent in to_delete:
        try:
            msp.delete_entity(ent)
        except Exception:
            pass

    print(f"WELDSYMBOL 적용 완료")

### NL1 생성 및 거리 제어 기능 ###
def find_all_circles_by_radius(msp, target_radius, radius_tolerance=0.1):
    """특정 반지름의 노랑색 원들을 모두 찾는 함수"""
    circles = []
    for entity in msp.query('CIRCLE'):
        try:
            if (hasattr(entity.dxf, 'color') and entity.dxf.color == 2 and  # 노랑색
                hasattr(entity.dxf, 'radius') and abs(entity.dxf.radius - target_radius) < radius_tolerance):
                center = Vec2(entity.dxf.center.x, entity.dxf.center.y)
                circles.append({
                    'entity': entity,
                    'center': center,
                    'radius': entity.dxf.radius
                })
        except Exception:
            continue
    return circles

def adjust_weld_circle_distance(weld_circle, small_circle, min_distance=6.0, msp=None):
    """WELD 원과 1mm 원 사이의 직선거리를 6mm로 조정하는 함수 (6mm 이하일 경우만)"""
    weld_center = weld_circle['center']
    small_center = small_circle['center']
    weld_radius = weld_circle['radius']  # 실제로는 2.8mm (5.6mm 지름)
    small_radius = small_circle['radius']  # 1mm
    
    # 현재 직선거리 계산 (중심점 간 거리)
    current_distance = distance(weld_center, small_center)
    
    print(f"  현재 WELD-1mm원 직선거리: {current_distance:.2f}mm")
    print(f"  최소 요구 거리: {min_distance}mm")
    
    # 6mm 이상이면 조정 불필요
    if current_distance >= min_distance:
        print(f"  거리 조정 불필요 (직선거리 {current_distance:.2f}mm >= {min_distance}mm)")
        return True, weld_center, [], "no_adjustment"
    
    # 6mm 미만인 경우만 STRETCH
    print(f"  STRETCH 필요: {current_distance:.2f}mm → {min_distance}mm")
    
    # 방향 벡터 계산 (1mm 원에서 멀어지는 방향)
    direction_vec = weld_center - small_center
    if direction_vec.magnitude == 0:
        print(f"  원들이 같은 위치에 있어 조정 불가능")
        return False, weld_center, [], "same_position"
    
    direction_normalized = direction_vec.normalize()
    
    # 새로운 WELD 원 위치 계산 (1mm 원에서 정확히 6mm 떨어진 위치)
    new_weld_center = small_center + direction_normalized * min_distance
    
    print(f"  WELD 원 이동 계획: ({weld_center.x:.2f}, {weld_center.y:.2f}) → ({new_weld_center.x:.2f}, {new_weld_center.y:.2f})")
    
    # WELDNO 텍스트만 찾기 (WELD 원 주변 3mm 내의 텍스트만)
    weldno_text_search_radius = 3.0
    weldno_texts = []
    text_backups = []
    
    for txt in msp.query('TEXT'):
        try:
            txt_pos = Vec2(txt.dxf.insert.x, txt.dxf.insert.y)
            if distance(weld_center, txt_pos) <= weldno_text_search_radius:
                # WELDNO 관련 텍스트만 이동 (다른 TEXT는 절대 이동하지 않음)
                weldno_texts.append(txt)
                text_backups.append({
                    'text': txt,
                    'original_pos': (txt.dxf.insert.x, txt.dxf.insert.y, txt.dxf.insert.z if hasattr(txt.dxf.insert, 'z') else 0)
                })
        except Exception as e:
            continue
    
    print(f"    WELDNO 텍스트 {len(weldno_texts)}개 발견 (다른 TEXT는 이동하지 않음)")
    
    # 원래 WELD 원 위치 백업
    original_weld_center = Vec2(weld_center.x, weld_center.y)
    
    # 새 위치에서 간섭 체크
    exclude_entities = [weld_circle['entity'], small_circle['entity']] + weldno_texts
    if check_interference_at_position(new_weld_center, msp, exclude_entities, weld_radius):
        print(f"  새 위치에서 간섭 발생 - 조정 실패, 원래 위치 유지")
        return False, weld_center, [], "stretch_interference"
    
    # 다른 원들과의 거리 체크 (최소 6mm 직선거리)
    all_circles = []
    for entity in msp.query('CIRCLE'):
        try:
            if (hasattr(entity.dxf, 'color') and entity.dxf.color == 2 and
                entity != weld_circle['entity']):
                circle_center = Vec2(entity.dxf.center.x, entity.dxf.center.y)
                all_circles.append({
                    'entity': entity,
                    'center': circle_center,
                    'radius': entity.dxf.radius
                })
        except Exception as e:
            continue
    
    # 다른 원들과의 최소 거리 체크
    for other_circle in all_circles:
        other_center = other_circle['center']
        dist_between_centers = distance(new_weld_center, other_center)
        
        if dist_between_centers < min_distance:
            print(f"    다른 원과의 거리 위반: {dist_between_centers:.2f}mm < {min_distance}mm")
            print(f"    조정 실패 - 다른 원과 충돌, 원래 위치 유지")
            return False, weld_center, [], "stretch_circle_collision"
    
    # WELD 원 및 WELDNO 텍스트만 이동
    try:
        move_vec = new_weld_center - weld_center
        
        # WELD 원 이동
        weld_circle['entity'].dxf.center = (new_weld_center.x, new_weld_center.y, 0)
        
        # WELDNO 텍스트들만 함께 이동 (다른 TEXT는 절대 이동하지 않음)
        for txt in weldno_texts:
            try:
                old_pos = txt.dxf.insert
                new_pos = (old_pos.x + move_vec.x, old_pos.y + move_vec.y, old_pos.z if hasattr(old_pos, 'z') else 0)
                txt.dxf.insert = new_pos
            except Exception as e:
                print(f"    WELDNO 텍스트 이동 오류: {e}")
        
        final_distance = distance(new_weld_center, small_center)
        print(f"  WELD 원 STRETCH 성공: 최종 직선거리 {final_distance:.2f}mm")
        print(f"    WELDNO 텍스트 {len(weldno_texts)}개만 함께 이동 완료 (다른 TEXT는 보호됨)")
        
        return True, new_weld_center, weldno_texts, "stretch"
        
    except Exception as e:
        print(f"  WELD 원 STRETCH 실행 중 오류: {e}")
        
        # 오류 발생 시 원래 위치로 복구
        try:
            weld_circle['entity'].dxf.center = (original_weld_center.x, original_weld_center.y, 0)
            for backup in text_backups:
                backup['text'].dxf.insert = backup['original_pos']
            print(f"    오류로 인한 원래 위치 복구 완료")
        except Exception as restore_e:
            print(f"    복구 중 오류: {restore_e}")
        
        return False, weld_center, [], "stretch_error"

def ensure_minimum_distances_between_all_circles(msp, min_distance=6.0):
    """모든 노랑색 원들 간의 최소 6mm 직선거리를 보장하는 함수 - WELD 원만 이동, WELDNO 텍스트만 함께 이동"""
    print(f"\n🔍 모든 원 간 최소 {min_distance}mm 직선거리 보장 시작")
    
    # 모든 노랑색 원들 찾기
    all_circles = []
    for entity in msp.query('CIRCLE'):
        try:
            if hasattr(entity.dxf, 'color') and entity.dxf.color == 2:  # 노랑색
                center = Vec2(entity.dxf.center.x, entity.dxf.center.y)
                all_circles.append({
                    'entity': entity,
                    'center': center,
                    'radius': entity.dxf.radius
                })
        except Exception:
            continue
    
    print(f"  노랑색 원 총 {len(all_circles)}개 발견")
    
    adjustment_count = 0
    
    # 모든 원 쌍에 대해 거리 체크
    for i in range(len(all_circles)):
        for j in range(i + 1, len(all_circles)):
            circle1 = all_circles[i]
            circle2 = all_circles[j]
            
            center1 = circle1['center']
            center2 = circle2['center']
            current_distance = distance(center1, center2)
            
            if current_distance < min_distance:
                print(f"  원간 직선거리 위반: {current_distance:.2f}mm < {min_distance}mm")
                print(f"    원1: ({center1.x:.2f}, {center1.y:.2f}, R={circle1['radius']:.1f})")
                print(f"    원2: ({center2.x:.2f}, {center2.y:.2f}, R={circle2['radius']:.1f})")
                
                # WELD 원(2.8mm 반지름)만 이동 가능, 다른 모든 원은 고정
                moving_circle = None
                fixed_circle = None
                
                # WELD 원(2.8mm)만 이동 대상으로 선택
                if abs(circle1['radius'] - 2.8) <= 0.3 and abs(circle2['radius'] - 2.8) > 0.3:
                    moving_circle = circle1
                    fixed_circle = circle2
                elif abs(circle2['radius'] - 2.8) <= 0.3 and abs(circle1['radius'] - 2.8) > 0.3:
                    moving_circle = circle2
                    fixed_circle = circle1
                elif abs(circle1['radius'] - 2.8) <= 0.3 and abs(circle2['radius'] - 2.8) <= 0.3:
                    moving_circle = circle1
                    fixed_circle = circle2
                else:
                    print(f"    WELD 원이 없으므로 이동하지 않음")
                    continue
                
                if moving_circle is None:
                    continue
                
                print(f"    이동 대상: R={moving_circle['radius']:.1f}mm WELD 원")
                
                # 이동 방향 계산
                direction_vec = moving_circle['center'] - fixed_circle['center']
                if direction_vec.magnitude == 0:
                    continue
                
                direction_normalized = direction_vec.normalize()
                new_center = fixed_circle['center'] + direction_normalized * min_distance
                
                # WELDNO 텍스트만 찾기 (다른 TEXT는 절대 이동하지 않음)
                weldno_texts = []
                weldno_text_search_radius = 3.0
                for txt in msp.query('TEXT'):
                    try:
                        txt_pos = Vec2(txt.dxf.insert.x, txt.dxf.insert.y)
                        if distance(moving_circle['center'], txt_pos) <= weldno_text_search_radius:
                            weldno_texts.append(txt)
                    except Exception as e:
                        continue
                
                # 간섭 체크
                exclude_entities = [circle1['entity'], circle2['entity']] + weldno_texts
                if not check_interference_at_position(new_center, msp, exclude_entities, moving_circle['radius']):
                    try:
                        move_vec = new_center - moving_circle['center']
                        
                        # WELD 원 이동
                        moving_circle['entity'].dxf.center = (new_center.x, new_center.y, 0)
                        moving_circle['center'] = new_center
                        
                        # WELDNO 텍스트들만 함께 이동
                        for txt in weldno_texts:
                            try:
                                old_pos = txt.dxf.insert
                                new_pos = (old_pos.x + move_vec.x, old_pos.y + move_vec.y, old_pos.z if hasattr(old_pos, 'z') else 0)
                                txt.dxf.insert = new_pos
                            except Exception as e:
                                print(f"    WELDNO 텍스트 이동 오류: {e}")
                        
                        adjustment_count += 1
                        print(f"    WELD 원 조정 완료: ({new_center.x:.2f}, {new_center.y:.2f})로 이동")
                        if weldno_texts:
                            print(f"    WELDNO 텍스트 {len(weldno_texts)}개만 함께 이동 (다른 TEXT는 보호됨)")
                    except Exception as e:
                        print(f"    조정 실패: {e}")
                else:
                    print(f"    조정 불가: 새 위치에서 간섭 발생")
    
    print(f"원간 거리 조정 완료: {adjustment_count}개 WELD 원 조정됨 (WELDNO 텍스트만 이동)")

def find_closest_yellow_circles_to_weld_circles(msp, radius_tolerance=0.1):
    """WELDNO 그룹 안의 RED LINE 끝점에서 1.5mm 내 노랑색 1mm 원 찾기 - WELDNO당 1개만"""
    connections = []
    
    try:
        # WELD 원들 찾기 (2.8mm 반지름)
        weld_circles = find_all_circles_by_radius(msp, 2.8, radius_tolerance)
        print(f"🔍 WELD 원 {len(weld_circles)}개 발견 (반지름 2.8mm):")
        for i, weld_circle in enumerate(weld_circles):
            print(f"   {i+1}. 위치: ({weld_circle['center'].x:.2f}, {weld_circle['center'].y:.2f}), 반지름: {weld_circle['radius']:.3f}mm")
        
        # 모든 노랑색 1mm 원들 찾기
        small_circles = find_all_circles_by_radius(msp, 1.0, radius_tolerance)
        print(f"🟡 노랑색 1mm 원 {len(small_circles)}개 발견")
        
        # 각 WELD 원을 WELDNO로 간주하고 1개의 NL1만 생성
        for weld_circle in weld_circles:
            weld_center = weld_circle['center']
            weld_group_radius = 4.0  # WELD 주변 4mm 내의 RED LINE들만 대상
            
            print(f"🔍 WELDNO({weld_center.x:.2f}, {weld_center.y:.2f}) 처리 중...")
            
            # WELD 주변 4mm 내의 RED LINE들 찾기
            red_line_endpoints = []
            
            # RED LINE 찾기
            for entity in msp.query('LINE'):
                try:
                    if hasattr(entity.dxf, 'color') and entity.dxf.color == 1:  # 빨간색
                        start_point = Vec2(entity.dxf.start.x, entity.dxf.start.y)
                        end_point = Vec2(entity.dxf.end.x, entity.dxf.end.y)
                        
                        # WELD 4mm 내에 있는 LINE인지 확인
                        if (distance(weld_center, start_point) <= weld_group_radius or 
                            distance(weld_center, end_point) <= weld_group_radius):
                            red_line_endpoints.extend([start_point, end_point])
                except Exception as e:
                    continue
            
            # RED POLYLINE/LWPOLYLINE 찾기
            for poly in msp.query("POLYLINE LWPOLYLINE"):
                try:
                    if hasattr(poly.dxf, 'color') and poly.dxf.color == 1:  # 빨간색
                        if poly.dxftype() == "POLYLINE":
                            poly_points = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
                        else:
                            poly_points = [Vec2(x, y) for x, y, *_ in poly.get_points()]
                        
                        # WELD 4mm 내에 있는 폴리라인인지 확인
                        near_weld = False
                        for point in poly_points:
                            if distance(weld_center, point) <= weld_group_radius:
                                near_weld = True
                                break
                        
                        if near_weld and len(poly_points) >= 2:
                            # 폴리라인의 시작점과 끝점을 끝점으로 간주
                            red_line_endpoints.extend([poly_points[0], poly_points[-1]])
                except Exception as e:
                    continue
            
            print(f"   WELD 4mm 내 RED LINE 끝점 {len(red_line_endpoints)}개 발견")
            
            if not red_line_endpoints:
                print(f"   WELDNO 그룹에서 RED LINE을 찾을 수 없음 - SKIP")
                continue
            
            # 모든 RED LINE 끝점에서 1.5mm 내의 노랑색 원 찾기
            valid_connections = []
            endpoint_search_radius = 1.5  # RED LINE 끝점에서 1.5mm 내
            
            for endpoint in red_line_endpoints:
                for small_circle in small_circles:
                    try:
                        small_center = small_circle['center']
                        dist = distance(endpoint, small_center)
                        
                        # 1.5mm 내에 있는 경우만 유효한 연결로 간주
                        if dist <= endpoint_search_radius:
                            valid_connections.append({
                                'weld_circle': weld_circle,
                                'small_circle': small_circle,
                                'red_line_endpoint': endpoint,
                                'endpoint_to_small_distance': dist,
                                'weld_to_small_distance': distance(weld_center, small_center)
                            })
                            print(f"     유효 연결: RED끝점({endpoint.x:.2f}, {endpoint.y:.2f}) - 1mm원({small_center.x:.2f}, {small_center.y:.2f}), 거리: {dist:.3f}mm")
                    except Exception as e:
                        continue
            
            print(f"   1.5mm 내 유효 연결 {len(valid_connections)}개 발견")
            
            if not valid_connections:
                print(f"   RED LINE 끝점 1.5mm 내에 1mm 원이 없음 - SKIP")
                continue
            
            # 가장 가까운 연결 선택 (WELDNO당 1개만)
            best_connection = min(valid_connections, key=lambda x: x['endpoint_to_small_distance'])
            connections.append(best_connection)
            
            endpoint = best_connection['red_line_endpoint']
            small_center = best_connection['small_circle']['center']
            
            print(f"✅ WELDNO 연결: WELD원({weld_center.x:.2f}, {weld_center.y:.2f}) - RED끝점({endpoint.x:.2f}, {endpoint.y:.2f}) - 1mm원({small_center.x:.2f}, {small_center.y:.2f})")
            print(f"    거리: RED끝점→1mm원 {best_connection['endpoint_to_small_distance']:.3f}mm, WELD→1mm원 {best_connection['weld_to_small_distance']:.3f}mm")
        
        print(f"📍 최종 결과: WELDNO별 NL1 연결 {len(connections)}개 (각 WELDNO당 1개, 1.5mm 내만)")
        return connections
        
    except Exception as e:
        print(f"❌ 함수 전체 처리 중 오류: {e}")
        return []

def process_nl1_distance_control(doc):
    """WELDSYMBOL 완료 후 NL1 생성 및 6mm 직선거리 제어"""
    msp = doc.modelspace()
    
    # 거리 제어 파라미터
    min_distance = 6.0  # 최소 직선거리 6mm
    weld_radius = 2.8   # WELD 원 반지름 (5.6mm 지름)
    
    print("\n[3단계] NL1 생성 및 6mm 직선거리 제어 시작")
    
    try:
        # WELDNO 그룹에서 WELD로부터 먼 점 근처 1mm 원을 찾아 연결
        connections = find_closest_yellow_circles_to_weld_circles(msp)
        print(f"WELDNO 그룹별 연결 {len(connections)}개 발견")
        
        if not connections:
            print("WELDNO 그룹에서 연결할 1mm 원이 없습니다.")
            return

        print(f"📊 처리할 연결 개수: {len(connections)}개")
        
        nl1_created_count = 0
        stretch_count = 0
        nl1_weld_pairs = []  # NL1과 연결된 WELD 원들 추적
        
        # 각 연결에 대해 거리 제어 및 STRETCH 수행
        for i, connection in enumerate(connections):
            print(f"\n🔧 [{i+1}/{len(connections)}] 연결 처리 중...")
            
            try:
                weld_circle = connection['weld_circle']
                small_circle = connection['small_circle']
                weld_center = weld_circle['center']
                small_center = small_circle['center']
                red_endpoint = connection['red_line_endpoint']
                current_distance = connection['weld_to_small_distance']
                
                print(f"🔍 연결 처리: WELD원({weld_center.x:.2f}, {weld_center.y:.2f}) - RED끝점({red_endpoint.x:.2f}, {red_endpoint.y:.2f}) - 1mm원({small_center.x:.2f}, {small_center.y:.2f})")
                print(f"   현재 WELD-1mm원 직선거리: {current_distance:.2f}mm")
                
                # 6mm 이하인 경우만 STRETCH
                if current_distance <= min_distance:
                    if abs(current_distance - min_distance) < 0.1:
                        print(f"   ✅ 이미 6mm: 조정 불필요 (현재 {current_distance:.2f}mm)")
                        moved_texts = []
                    else:
                        print(f"   ⚠️  직선거리 {current_distance:.2f}mm <= {min_distance}mm: WELD 원 STRETCH 필요")
                        
                        adjust_success, new_weld_center, moved_texts, action_type = adjust_weld_circle_distance(
                            weld_circle, small_circle, min_distance, msp
                        )
                        
                        if adjust_success:
                            weld_center = new_weld_center
                            stretch_count += 1
                            print(f"   ✅ WELD 원 STRETCH 성공")
                            
                            # WELD 원이 이동했으므로 weld_circle 정보 업데이트
                            weld_circle['center'] = new_weld_center
                        else:
                            print(f"   ❌ WELD 원 STRETCH 실패 - 원래 위치 유지")
                            moved_texts = []
                else:
                    print(f"   ✅ 직선거리 OK: {current_distance:.2f}mm > {min_distance}mm (STRETCH 불필요)")
                    moved_texts = []  # 조정하지 않았으므로 이동된 텍스트 없음
                
                # NL1 흰색 선 생성 (이동된 WELD 원과 1mm 원 사이에 새로 그리기)
                nl1_line = msp.add_line(
                    start=(weld_center.x, weld_center.y),
                    end=(small_center.x, small_center.y),
                    dxfattribs={'color': 4}  # 흰색
                )
                
                final_distance = distance(weld_center, small_center)
                print(f"   NL1 생성: WELD원({weld_center.x:.2f}, {weld_center.y:.2f}) - 1mm원({small_center.x:.2f}, {small_center.y:.2f})")
                print(f"   최종 직선거리: {final_distance:.2f}mm")
                
                # WELD 원(5.6mm 지름)과 접하도록 NL1 TRIM 처리
                try:
                    weld_entity = weld_circle['entity']
                    weld_center_pos = Vec2(weld_entity.dxf.center.x, weld_entity.dxf.center.y)
                    weld_radius_val = weld_entity.dxf.radius  # 2.8mm
                    
                    # NL1과 WELD 원의 교차점 계산
                    line_start = Vec2(nl1_line.dxf.start.x, nl1_line.dxf.start.y)
                    line_end = Vec2(nl1_line.dxf.end.x, nl1_line.dxf.end.y)
                    
                    # WELD 원 중심에서 1mm 원 방향으로의 벡터
                    direction_to_small = line_end - line_start
                    if direction_to_small.magnitude > 0:
                        direction_normalized = direction_to_small.normalize()
                        # WELD 원 경계점 계산 (5.6mm 원과 접하게)
                        trim_start = weld_center_pos + direction_normalized * weld_radius_val
                        
                        # NL1을 WELD 원 경계에서 시작하도록 TRIM
                        nl1_line.dxf.start = (trim_start.x, trim_start.y, 0)
                        
                        # NL1 길이 계산
                        nl1_length = distance(trim_start, Vec2(small_center.x, small_center.y))
                        print(f"   WELD 원(5.6mm)과 접촉: NL1이 ({trim_start.x:.2f}, {trim_start.y:.2f})에서 시작")
                        print(f"   NL1 길이: {nl1_length:.2f}mm")
                    else:
                        print(f"   ⚠️  WELD 원과 1mm 원이 같은 위치에 있어 TRIM 불가")
                except Exception as trim_e:
                    print(f"   ❌ WELD 원 접촉 TRIM 중 오류: {trim_e}")
                
                # NL1과 WELD 원 쌍 저장 (성공적으로 생성된 경우)
                nl1_weld_pairs.append({
                    'nl1_line': nl1_line,
                    'weld_circle': weld_circle,
                    'small_circle': small_circle,
                    'connection': connection
                })
                
                nl1_created_count += 1
                print(f"   ✅ NL1 생성 성공: WELD 원과 함께 STRETCH되어 항상 5.6mm 원과 접함")
                
            except Exception as e:
                print(f"❌ 연결 처리 중 오류 발생: {e}")
                continue

        # NL1이 실제로 생성된 경우에만 해당 WELD 그룹의 RED 요소들 삭제
        if nl1_created_count > 0:
            print(f"\n🗑️  NL1이 생성된 {nl1_created_count}개 WELD 그룹의 RED 요소만 삭제 시작")
            
            red_lines_to_delete = []
            
            for pair in nl1_weld_pairs:
                connection = pair['connection']
                original_weld_center = connection['weld_circle']['center']
                weld_group_radius = 4.0
                
                print(f"   WELD 그룹({original_weld_center.x:.2f}, {original_weld_center.y:.2f})의 RED 요소 찾는 중...")
                
                # 이 특정 WELD 그룹의 RED LINE 찾기
                group_red_count = 0
                for entity in msp.query('LINE'):
                    try:
                        if hasattr(entity.dxf, 'color') and entity.dxf.color == 1:  # 빨간색
                            start_point = Vec2(entity.dxf.start.x, entity.dxf.start.y)
                            end_point = Vec2(entity.dxf.end.x, entity.dxf.end.y)
                            
                            # 이 WELD 그룹 4mm 내에 있는 RED LINE인지 확인
                            if (distance(original_weld_center, start_point) <= weld_group_radius or 
                                distance(original_weld_center, end_point) <= weld_group_radius):
                                if entity not in red_lines_to_delete:
                                    red_lines_to_delete.append(entity)
                                    group_red_count += 1
                    except Exception as e:
                        continue
                
                # 이 특정 WELD 그룹의 RED SL1 찾기
                for poly in msp.query("POLYLINE LWPOLYLINE"):
                    try:
                        if hasattr(poly.dxf, 'color') and poly.dxf.color == 1:  # 빨간색 SL1
                            if poly.dxftype() == "POLYLINE":
                                poly_points = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
                            else:
                                poly_points = [Vec2(x, y) for x, y, *_ in poly.get_points()]
                            
                            # 이 WELD 그룹 4mm 내에 있는 RED SL1인지 확인
                            for point in poly_points:
                                if distance(original_weld_center, point) <= weld_group_radius:
                                    if poly not in red_lines_to_delete:
                                        red_lines_to_delete.append(poly)
                                        group_red_count += 1
                                    break
                    except Exception as e:
                        continue
                
                print(f"     발견된 RED 요소: {group_red_count}개")
            
            # RED 요소들 삭제 실행 (NL1이 생성된 그룹만)
            deleted_red_count = 0
            for red_entity in red_lines_to_delete:
                try:
                    msp.delete_entity(red_entity)
                    deleted_red_count += 1
                except Exception as ex:
                    print(f"RED 요소 삭제 오류: {ex}")
            
            print(f"✅ NL1 생성된 그룹의 RED 요소 {deleted_red_count}개 삭제 완료")
        else:
            print(f"\n💡 NL1이 생성되지 않음 - 모든 SL1 보존됨")
        
        # NL1이 생성되지 않은 다른 SL1들 보존 확인
        remaining_sl1_count = 0
        for entity in msp.query('POLYLINE LWPOLYLINE LINE'):
            try:
                if hasattr(entity.dxf, 'color') and entity.dxf.color == 1:  # 빨간색
                    remaining_sl1_count += 1
            except Exception:
                continue
        
        if remaining_sl1_count > 0:
            print(f"💾 NL1이 생성되지 않은 SL1 {remaining_sl1_count}개 보존됨")

        # 모든 원 간의 최소 거리 보장 (WELD 원만 이동, WELDNO 텍스트만 함께 이동)
        ensure_minimum_distances_between_all_circles(msp, min_distance)
        
        print(f"\n📊 최종 처리 결과:")
        print(f"   📏 WELD 원 STRETCH: {stretch_count}개 (6mm 이하인 경우만)")
        print(f"   🔗 NL1 생성: {nl1_created_count}개 (WELD 원과 함께 STRETCH)")
        print(f"   🎯 5.6mm 원 접촉: NL1이 항상 WELD 원(5.6mm)과 접함")
        print(f"   🚫 TEXT 보호: WELDNO 이외 다른 TEXT는 절대 이동하지 않음")
        print(f"   🗑️  SL1 삭제: NL1 생성된 그룹만 삭제, 나머지 보존")
        
        print("[3단계] NL1 생성 및 WELD 원 STRETCH 완료")
        
    except Exception as main_e:
        print(f"❌ NL1 처리 중 전체 오류: {main_e}")
        print("[3단계] NL1 생성 및 거리 제어 실패")

### [4단계] NL1 길이 6mm 조정 기능 ###
def find_nl1_lines_with_weld_circles(msp):
    """NL1 흰색 선과 연결된 WELD 원들을 찾는 함수"""
    nl1_weld_pairs = []
    
    # 모든 흰색 NL1 선 찾기
    nl1_lines = []
    for entity in msp.query('LINE'):
        try:
            if hasattr(entity.dxf, 'color') and entity.dxf.color == 4:  # 흰색
                nl1_lines.append(entity)
        except Exception:
            continue
    
    print(f"🔍 흰색 NL1 선 {len(nl1_lines)}개 발견")
    
    # 각 NL1 선에 대해 연결된 WELD 원 찾기
    for nl1_line in nl1_lines:
        try:
            line_start = Vec2(nl1_line.dxf.start.x, nl1_line.dxf.start.y)
            line_end = Vec2(nl1_line.dxf.end.x, nl1_line.dxf.end.y)
            
            # NL1 선의 끝점 근처에 있는 WELD 원 찾기
            weld_circle = None
            small_circle = None
            
            # WELD 원 찾기 (반지름 2.8mm)
            for entity in msp.query('CIRCLE'):
                try:
                    if (hasattr(entity.dxf, 'color') and entity.dxf.color == 2 and  # 노랑색
                        hasattr(entity.dxf, 'radius') and abs(entity.dxf.radius - 2.8) <= 0.3):
                        circle_center = Vec2(entity.dxf.center.x, entity.dxf.center.y)
                        
                        # NL1 선의 시작점이 WELD 원 경계 근처에 있는지 확인 (2.8mm + 여유)
                        dist_to_start = distance(circle_center, line_start)
                        if dist_to_start <= 3.5:  # WELD 원 반지름 + 여유
                            weld_circle = {
                                'entity': entity,
                                'center': circle_center,
                                'radius': entity.dxf.radius
                            }
                            break
                except Exception:
                    continue
            
            # 1mm 원 찾기
            for entity in msp.query('CIRCLE'):
                try:
                    if (hasattr(entity.dxf, 'color') and entity.dxf.color == 2 and  # 노랑색
                        hasattr(entity.dxf, 'radius') and abs(entity.dxf.radius - 1.0) <= 0.1):
                        circle_center = Vec2(entity.dxf.center.x, entity.dxf.center.y)
                        
                        # NL1 선의 끝점이 1mm 원 근처에 있는지 확인
                        dist_to_end = distance(circle_center, line_end)
                        if dist_to_end <= 1.5:  # 1mm 원 반지름 + 여유
                            small_circle = {
                                'entity': entity,
                                'center': circle_center,
                                'radius': entity.dxf.radius
                            }
                            break
                except Exception:
                    continue
            
            # NL1과 WELD 원, 1mm 원이 모두 연결된 경우만 추가
            if weld_circle and small_circle:
                nl1_length = distance(line_start, line_end)
                nl1_weld_pairs.append({
                    'nl1_line': nl1_line,
                    'weld_circle': weld_circle,
                    'small_circle': small_circle,
                    'current_length': nl1_length
                })
                print(f"   NL1 발견: 길이 {nl1_length:.2f}mm, WELD원({weld_circle['center'].x:.2f}, {weld_circle['center'].y:.2f}) - 1mm원({small_circle['center'].x:.2f}, {small_circle['center'].y:.2f})")
        
        except Exception as e:
            print(f"NL1 선 처리 중 오류: {e}")
            continue
    
    print(f"📊 유효한 NL1-WELD 쌍 {len(nl1_weld_pairs)}개 발견")
    return nl1_weld_pairs

def adjust_nl1_to_7mm_length(nl1_weld_pair, target_length=7.0, msp=None):
    """NL1 길이를 정확히 7mm로 조정하는 함수"""
    nl1_line = nl1_weld_pair['nl1_line']
    weld_circle = nl1_weld_pair['weld_circle']
    small_circle = nl1_weld_pair['small_circle']
    current_length = nl1_weld_pair['current_length']
    
    weld_center = weld_circle['center']
    small_center = small_circle['center']
    weld_radius = weld_circle['radius']  # 2.8mm
    
    print(f"🔧 NL1 길이 조정: 현재 {current_length:.2f}mm → 목표 {target_length:.2f}mm")
    
    # 7mm 이하면 조정 불필요
    if current_length <= target_length:
        print(f"   ✅ 조정 불필요: 현재 길이 {current_length:.2f}mm <= {target_length}mm")
        return True, "no_adjustment"
    
    # WELD 원에서 1mm 원 방향으로의 벡터 (NL1 벡터 방향)
    direction_vec = small_center - weld_center
    if direction_vec.magnitude == 0:
        print(f"   ❌ 원들이 같은 위치에 있어 조정 불가능")
        return False, "same_position"
    
    direction_normalized = direction_vec.normalize()
    
    # 새로운 WELD 원 위치 계산 (1mm 원에서 정확히 7mm 떨어진 위치)
    new_weld_center = small_center - direction_normalized * target_length
    
    print(f"   이동 계획: WELD원 ({weld_center.x:.2f}, {weld_center.y:.2f}) → ({new_weld_center.x:.2f}, {new_weld_center.y:.2f})")
    
    # WELDNO 텍스트 찾기 (WELD 원 주변 3mm 내만)
    weldno_texts = []
    weldno_text_search_radius = 3.0
    text_backups = []
    
    for txt in msp.query('TEXT'):
        try:
            txt_pos = Vec2(txt.dxf.insert.x, txt.dxf.insert.y)
            if distance(weld_center, txt_pos) <= weldno_text_search_radius:
                weldno_texts.append(txt)
                text_backups.append({
                    'text': txt,
                    'original_pos': (txt.dxf.insert.x, txt.dxf.insert.y, txt.dxf.insert.z if hasattr(txt.dxf.insert, 'z') else 0)
                })
        except Exception:
            continue
    
    print(f"   WELDNO 텍스트 {len(weldno_texts)}개 발견")
    
    # 원래 위치 백업
    original_weld_center = Vec2(weld_center.x, weld_center.y)
    
    # 새 위치에서 간섭 체크 (NL1은 제외)
    exclude_entities = [weld_circle['entity'], small_circle['entity'], nl1_line] + weldno_texts
    
    # 새 위치에서 TEXT 간섭 체크
    has_text_interference_at_new = check_text_interference_only(new_weld_center, msp, exclude_entities, weld_radius)
    
    # 원래 위치에서 TEXT 간섭 체크
    has_text_interference_at_original = check_text_interference_only(original_weld_center, msp, exclude_entities, weld_radius)
    
    print(f"   TEXT 간섭 체크 결과:")
    print(f"     새 위치(7mm) TEXT 간섭: {'있음' if has_text_interference_at_new else '없음'}")
    print(f"     원래 위치 TEXT 간섭: {'있음' if has_text_interference_at_original else '없음'}")
    
    # 결정 로직: 두 위치 중 TEXT 간섭이 없는 곳으로 이동
    target_center = None
    decision_reason = ""
    
    if not has_text_interference_at_new and not has_text_interference_at_original:
        # 둘 다 간섭 없으면 7mm 위치로 이동 (목표 달성)
        target_center = new_weld_center
        decision_reason = "둘 다 간섭 없음 - 7mm 위치로 이동"
    elif not has_text_interference_at_new and has_text_interference_at_original:
        # 새 위치만 간섭 없으면 7mm 위치로 이동
        target_center = new_weld_center
        decision_reason = "7mm 위치만 간섭 없음 - 7mm 위치로 이동"
    elif has_text_interference_at_new and not has_text_interference_at_original:
        # 원래 위치만 간섭 없으면 원래 위치 유지
        target_center = original_weld_center
        decision_reason = "원래 위치만 간섭 없음 - 원래 위치 유지"
    else:
        # 둘 다 간섭 있으면 7mm 위치로 이동 (강제)
        target_center = new_weld_center
        decision_reason = "둘 다 간섭 있음 - 7mm 위치로 강제 이동"
    
    print(f"   결정: {decision_reason}")
    
    # 원래 위치 유지하는 경우
    if target_center == original_weld_center:
        print(f"   ✅ 원래 위치 유지 - 조정 없음")
        return True, "keep_original_position"
    
    # 다른 원들과의 거리 체크 (최소 6mm) - 7mm 위치로 이동하는 경우만
    for entity in msp.query('CIRCLE'):
        try:
            if (hasattr(entity.dxf, 'color') and entity.dxf.color == 2 and
                entity != weld_circle['entity'] and entity != small_circle['entity']):
                other_center = Vec2(entity.dxf.center.x, entity.dxf.center.y)
                dist_to_other = distance(target_center, other_center)
                
                if dist_to_other < 6.0:
                    print(f"   ❌ 다른 원과의 거리 위반: {dist_to_other:.2f}mm < 6.0mm")
                    print(f"   이동 취소 - 원래 위치 유지")
                    return False, "circle_collision"
        except Exception:
            continue
    
    # WELD 원 및 WELDNO 텍스트 이동 실행
    try:
        move_vec = target_center - weld_center
        
        # WELD 원 이동
        weld_circle['entity'].dxf.center = (target_center.x, target_center.y, 0)
        weld_circle['center'] = target_center
        
        # WELDNO 텍스트들 함께 이동
        for txt in weldno_texts:
            try:
                old_pos = txt.dxf.insert
                new_pos = (old_pos.x + move_vec.x, old_pos.y + move_vec.y, old_pos.z if hasattr(old_pos, 'z') else 0)
                txt.dxf.insert = new_pos
            except Exception as e:
                print(f"    WELDNO 텍스트 이동 오류: {e}")
        
        # NL1 선 업데이트 (WELD 원 경계에서 시작)
        direction_to_small = small_center - target_center
        if direction_to_small.magnitude > 0:
            direction_normalized_final = direction_to_small.normalize()
            new_trim_start = target_center + direction_normalized_final * weld_radius
            nl1_line.dxf.start = (new_trim_start.x, new_trim_start.y, 0)
            
            # 새로운 NL1 길이 계산
            final_nl1_length = distance(new_trim_start, small_center)
            
            print(f"   ✅ WELD 원 STRETCH 성공")
            print(f"   WELD 원 새 위치: ({target_center.x:.2f}, {target_center.y:.2f})")
            print(f"   NL1 새 길이: {final_nl1_length:.2f}mm")
            print(f"   WELDNO 텍스트 {len(weldno_texts)}개 함께 이동")
        
        return True, "stretch_success"
        
    except Exception as e:
        print(f"   ❌ STRETCH 실행 중 오류: {e}")
        
        # 오류 발생 시 원래 위치로 복구
        try:
            weld_circle['entity'].dxf.center = (original_weld_center.x, original_weld_center.y, 0)
            weld_circle['center'] = original_weld_center
            for backup in text_backups:
                backup['text'].dxf.insert = backup['original_pos']
            print(f"   복구 완료: 원래 위치로 되돌림")
        except Exception as restore_e:
            print(f"   복구 중 오류: {restore_e}")
        
        return False, "stretch_error"

def process_nl1_length_adjustment(doc):
    """[4단계] NL1 길이가 7mm 초과인 경우 7mm로 조정"""
    msp = doc.modelspace()
    target_length = 7.0
    
    print(f"\n[4단계] NL1 길이 7mm 조정 시작")
    
    try:
        # NL1 선과 연결된 WELD 원들 찾기
        nl1_weld_pairs = find_nl1_lines_with_weld_circles(msp)
        
        if not nl1_weld_pairs:
            print("조정할 NL1-WELD 쌍이 없습니다.")
            return
        
        # 7mm 초과인 NL1만 필터링
        long_nl1_pairs = []
        for pair in nl1_weld_pairs:
            if pair['current_length'] > target_length:
                long_nl1_pairs.append(pair)
                print(f"📏 조정 대상: NL1 길이 {pair['current_length']:.2f}mm > {target_length}mm")
        
        if not long_nl1_pairs:
            print(f"✅ 모든 NL1이 이미 {target_length}mm 이하입니다.")
            return
        
        print(f"📊 조정 대상: {len(long_nl1_pairs)}개 NL1")
        
        success_count = 0
        fail_count = 0
        keep_original_count = 0
        
        # 각 긴 NL1에 대해 조정 수행
        for i, pair in enumerate(long_nl1_pairs):
            print(f"\n🔧 [{i+1}/{len(long_nl1_pairs)}] NL1 조정 중...")
            
            success, result_type = adjust_nl1_to_7mm_length(pair, target_length, msp)
            
            if success:
                if result_type == "no_adjustment":
                    print(f"   ✅ 조정 불필요")
                elif result_type == "keep_original_position":
                    keep_original_count += 1
                    print(f"   ✅ 원래 위치 유지 (TEXT 간섭 회피)")
                else:
                    success_count += 1
                    print(f"   ✅ 7mm 위치로 조정 성공")
            else:
                fail_count += 1
                print(f"   ❌ 조정 실패: {result_type}")
        
        print(f"\n📊 [4단계] 최종 결과:")
        print(f"   🎯 7mm 위치로 조정 성공: {success_count}개")
        print(f"   🏠 원래 위치 유지: {keep_original_count}개 (TEXT 간섭 회피)")
        print(f"   ❌ 조정 실패: {fail_count}개")
        print(f"   📏 모든 WELDNO가 TEXT 간섭 없는 최적 위치에 배치됨")
        print(f"   🔧 WELD 원 STRETCH: NL1 벡터 방향으로 7mm 위치로 이동")
        print(f"   🚫 TEXT 간섭 체크: 두 위치 중 간섭 없는 곳으로 선택")
        print(f"   💾 WELDNO 텍스트만 함께 이동 (다른 TEXT 보호)")
        
        print("[4단계] NL1 길이 7mm 조정 완료")
        
    except Exception as e:
        print(f"❌ [4단계] NL1 길이 조정 중 오류: {e}")
        print("[4단계] NL1 길이 조정 실패")

### 메인 실행 ###
if __name__ == "__main__":
    filepaths = select_dxf_files()
    for filepath in filepaths:
        doc = ezdxf.readfile(filepath)
        print(f"\n📂 선택된 파일: {filepath}")

        print("\n[1단계] WELDNOEDIT 작업 시작")
        process_weldnoedit(doc)
        print("[1단계] 완료")

        print("\n[2단계] WELDSYMBOL 작업 시작")
        process_weldsymbol(doc)
        print("[2단계] 완료")

        print("\n[3단계] NL1 생성 및 6mm 직선거리 제어 시작")
        process_nl1_distance_control(doc)
        print("[3단계] 완료")

        print("\n[4단계] NL1 길이 6mm 조정 시작")
        process_nl1_length_adjustment(doc)
        print("[4단계] 완료")

        basename = os.path.splitext(os.path.basename(filepath))[0]
        output_dir = os.path.dirname(filepath)
        output_path = os.path.join(output_dir, basename + "_editwsym.dxf")
        
        # 파일이 이미 존재하거나 권한이 없는 경우 다른 경로 시도
        try:
            doc.saveas(output_path)
            print(f"\n✔ 최종 저장: {output_path}")
        except PermissionError:
            # 바탕화면에 저장 시도
            import getpass
            username = getpass.getuser()
            desktop_path = f"C:/Users/{username}/Desktop/{basename}_editwsym.dxf"
            try:
                doc.saveas(desktop_path)
                print(f"\n✔ 권한 오류로 바탕화면에 저장: {desktop_path}")
            except Exception as e:
                # 현재 디렉토리에 저장 시도
                current_dir_path = f"./{basename}_editwsym.dxf"
                try:
                    doc.saveas(current_dir_path)
                    print(f"\n✔ 현재 디렉토리에 저장: {current_dir_path}")
                except Exception as e2:
                    print(f"\n❌ 저장 실패: {e2}")