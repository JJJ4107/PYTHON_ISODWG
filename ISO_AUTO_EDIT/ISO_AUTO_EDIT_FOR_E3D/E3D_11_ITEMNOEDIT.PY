import ezdxf
import os
import math
from ezdxf.math import Vec2
from tkinter import Tk, filedialog

def select_files():
    Tk().withdraw()
    return filedialog.askopenfilenames(
        title="DXF 파일 선택 (여러 개 가능)",
        filetypes=[("DXF files", "*.dxf")])

def distance(p1, p2):
    return math.hypot(p2.x - p1.x, p2.y - p1.y)

def set_entity_color(entity, color=1):
    try:
        if entity and hasattr(entity, "dxf") and hasattr(entity.dxf, "color"):
            entity.dxf.color = color
    except:
        pass

def get_line_midpoint(line):
    try:
        start = line.dxf.start
        end = line.dxf.end
        return Vec2((start.x + end.x) / 2, (start.y + end.y) / 2)
    except:
        return Vec2(0, 0)

def get_text_position(text):
    try:
        ins = getattr(text.dxf, "insert", None)
        if ins:
            return Vec2(ins.x, ins.y)
        loc = getattr(text.dxf, "location", None)
        if loc:
            return Vec2(loc[0], loc[1])
    except:
        pass
    return Vec2(0, 0)

def get_poly_points(pl):
    try:
        if pl.dxftype() == 'LWPOLYLINE':
            return [Vec2(pt[0], pt[1]) for pt in pl.get_points()]
        elif pl.dxftype() == 'POLYLINE':
            return [Vec2(v.dxf.location.x, v.dxf.location.y) for v in pl.vertices]
    except:
        pass
    return []

def rotate_point(pt, center, angle_deg):
    angle_rad = math.radians(angle_deg)
    dx, dy = pt.x - center.x, pt.y - center.y
    cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
    rx = dx * cos_a - dy * sin_a + center.x
    ry = dx * sin_a + dy * cos_a + center.y
    return Vec2(rx, ry)

def move_point(pt, offset):
    return Vec2(pt.x + offset.x, pt.y + offset.y)

def rotate_entity_around(entity, center, angle_deg):
    try:
        t = entity.dxftype()
        if t == "TEXT":
            pos = get_text_position(entity)
            rpos = rotate_point(pos, center, angle_deg)
            entity.dxf.insert = (rpos.x, rpos.y, 0)
            orig_angle = getattr(entity.dxf, 'rotation', 0)
            entity.dxf.rotation = (orig_angle + angle_deg) % 360
        elif t == "LINE":
            a = Vec2(entity.dxf.start.x, entity.dxf.start.y)
            b = Vec2(entity.dxf.end.x, entity.dxf.end.y)
            ra = rotate_point(a, center, angle_deg)
            rb = rotate_point(b, center, angle_deg)
            entity.dxf.start = (ra.x, ra.y, 0)
            entity.dxf.end = (rb.x, rb.y, 0)
        elif t in ("LWPOLYLINE", "POLYLINE"):
            points = get_poly_points(entity)
            new_points = [rotate_point(pt, center, angle_deg) for pt in points]
            if t == "LWPOLYLINE":
                entity.clear()
                for pt in new_points:
                    entity.append_points([(pt.x, pt.y)])
            else:
                for v, rpt in zip(entity.vertices, new_points):
                    v.dxf.location = (rpt.x, rpt.y, 0)
    except Exception as e:
        print(f"▶ 회전 오류: {entity} / {e}")

def move_entity(entity, offset):
    try:
        t = entity.dxftype()
        if t == "TEXT":
            pos = get_text_position(entity)
            npos = move_point(pos, offset)
            entity.dxf.insert = (npos.x, npos.y, 0)
        elif t == "LINE":
            a = Vec2(entity.dxf.start.x, entity.dxf.start.y)
            b = Vec2(entity.dxf.end.x, entity.dxf.end.y)
            na = move_point(a, offset)
            nb = move_point(b, offset)
            entity.dxf.start = (na.x, na.y, 0)
            entity.dxf.end = (nb.x, nb.y, 0)
        elif t in ("LWPOLYLINE", "POLYLINE"):
            points = get_poly_points(entity)
            new_points = [move_point(pt, offset) for pt in points]
            if t == "LWPOLYLINE":
                entity.clear()
                for pt in new_points:
                    entity.append_points([(pt.x, pt.y)])
            else:
                for v, npt in zip(entity.vertices, new_points):
                    v.dxf.location = (npt.x, npt.y, 0)
    except Exception as e:
        print(f"▶ 이동 오류: {entity} / {e}")

def calc_angle_deg(pt1, pt2):
    dx = pt2.x - pt1.x
    dy = pt2.y - pt1.y
    return math.degrees(math.atan2(dy, dx))

def get_perpendicular_offset(angle_deg, length):
    angle_rad = math.radians(angle_deg + 90)
    return Vec2(math.cos(angle_rad) * length, math.sin(angle_rad) * length)

def get_entity_center(entities):
    """엔티티 그룹의 중심점 계산"""
    x_sum = 0; y_sum = 0; n = 0
    for ent in entities:
        if ent.dxftype() == "TEXT":
            pos = get_text_position(ent)
            x_sum += pos.x; y_sum += pos.y; n += 1
        elif ent.dxftype() == "LINE":
            a = Vec2(ent.dxf.start.x, ent.dxf.start.y)
            b = Vec2(ent.dxf.end.x, ent.dxf.end.y)
            x_sum += (a.x + b.x) / 2; y_sum += (a.y + b.y) / 2; n += 1
        elif ent.dxftype() in ("LWPOLYLINE", "POLYLINE"):
            pts = get_poly_points(ent)
            for pt in pts:
                x_sum += pt.x; y_sum += pt.y; n += 1
    return Vec2(x_sum/n, y_sum/n) if n else Vec2(0,0)

def get_pline_center(entity):
    """PLINE 엔티티(LINE 또는 POLYLINE)의 중심점 계산"""
    if entity.dxftype() == "LINE":
        start = Vec2(entity.dxf.start.x, entity.dxf.start.y)
        end = Vec2(entity.dxf.end.x, entity.dxf.end.y)
        return Vec2((start.x + end.x) / 2, (start.y + end.y) / 2)
    elif entity.dxftype() in ("LWPOLYLINE", "POLYLINE"):
        pts = get_poly_points(entity)
        if pts:
            cx = sum([p.x for p in pts]) / len(pts)
            cy = sum([p.y for p in pts]) / len(pts)
            return Vec2(cx, cy)
    return None

def get_pline_angle(entity):
    """PLINE의 기울기(각도) 계산"""
    if entity.dxftype() == "LINE":
        start = Vec2(entity.dxf.start.x, entity.dxf.start.y)
        end = Vec2(entity.dxf.end.x, entity.dxf.end.y)
        return calc_angle_deg(start, end)
    elif entity.dxftype() in ("LWPOLYLINE", "POLYLINE"):
        pts = get_poly_points(entity)
        if len(pts) >= 2:
            # 첫점과 끝점으로 각도 계산
            return calc_angle_deg(pts[0], pts[-1])
    return 0

def check_line_passes_near_point(entity, point, threshold=2.0):
    """LINE이나 폴리라인이 점 근처를 지나는지 확인"""
    if entity.dxftype() == "LINE":
        start = Vec2(entity.dxf.start.x, entity.dxf.start.y)
        end = Vec2(entity.dxf.end.x, entity.dxf.end.y)
        # 점에서 선분까지의 최단거리 계산
        line_vec = Vec2(end.x - start.x, end.y - start.y)
        line_len = math.sqrt(line_vec.x**2 + line_vec.y**2)
        if line_len == 0:
            return distance(point, start) <= threshold
        
        t = max(0, min(1, ((point.x - start.x) * line_vec.x + (point.y - start.y) * line_vec.y) / (line_len**2)))
        closest_point = Vec2(start.x + t * line_vec.x, start.y + t * line_vec.y)
        return distance(point, closest_point) <= threshold
        
    elif entity.dxftype() in ("LWPOLYLINE", "POLYLINE"):
        pts = get_poly_points(entity)
        # 모든 세그먼트에 대해 검사
        for i in range(len(pts) - 1):
            start = pts[i]
            end = pts[i + 1]
            line_vec = Vec2(end.x - start.x, end.y - start.y)
            line_len = math.sqrt(line_vec.x**2 + line_vec.y**2)
            if line_len == 0:
                if distance(point, start) <= threshold:
                    return True
                continue
            
            t = max(0, min(1, ((point.x - start.x) * line_vec.x + (point.y - start.y) * line_vec.y) / (line_len**2)))
            closest_point = Vec2(start.x + t * line_vec.x, start.y + t * line_vec.y)
            if distance(point, closest_point) <= threshold:
                return True
        # 마지막 점도 확인
        if pts and distance(point, pts[-1]) <= threshold:
            return True
    return False

def get_poly_total_length(pts):
    """폴리라인 점들의 전체 길이 계산"""
    total_len = 0
    for i in range(len(pts) - 1):
        total_len += distance(pts[i], pts[i + 1])
    return total_len

def set_mirrtext_zero(doc):
    try:
        doc.header['$MIRRTEXT'] = 0
        print("   [MIRRTEXT=0] 설정 완료")
    except Exception as e:
        print(f"▶ MIRRTEXT=0 설정 오류: {e}")

def process_dxf(file_path):
    try:
        doc = ezdxf.readfile(file_path)
    except Exception as e:
        print(f"파일 열기 실패: {file_path} / {e}")
        return

    msp = doc.modelspace()
    modified = False

    for st1 in msp.query('TEXT'):
        if '<' not in st1.dxf.text or '>' not in st1.dxf.text:
            continue
        if getattr(st1.dxf, 'rotation', 0) != 0:
            continue
        st1_pos = get_text_position(st1)

        # 오른쪽 25mm, Y±5mm 범위 내 rotation==0 TEXT, 5 이하 숫자, 5점 폴리라인
        candidate_texts = []
        for e in msp.query('TEXT'):
            if e is st1:
                continue
            if getattr(e.dxf, 'rotation', 0) != 0:
                continue
            pos = get_text_position(e)
            dx = pos.x - st1_pos.x
            dy = abs(pos.y - st1_pos.y)
            try:
                is_digit = float(e.dxf.text.strip()) <= 5
            except:
                is_digit = False
            if 0 < dx <= 25 and dy <= 5 and is_digit:
                candidate_texts.append((dx, e))
        if not candidate_texts:
            continue
        candidate_texts.sort(key=lambda x: x[0])
        text_st2 = candidate_texts[0][1]
        text_st2_pos = get_text_position(text_st2)

        # 가장 가까운(거리 최소) 5점짜리 POLYLINE/LWPOLYLINE 1개만 찾기
        min_poly_dist = float('inf')
        poly5_st2 = None
        for e in msp.query('LWPOLYLINE POLYLINE'):
            pts = get_poly_points(e)
            if len(pts) == 5:
                dx = pts[0].x - st1_pos.x
                dy = abs(pts[0].y - st1_pos.y)
                if 0 < dx <= 25 and dy <= 5:
                    # 폴리라인 중심과 (st1, text_st2) 중간점 거리로 매칭
                    cx = sum([p.x for p in pts])/5
                    cy = sum([p.y for p in pts])/5
                    center_poly = Vec2(cx, cy)
                    target_center = Vec2((st1_pos.x+text_st2_pos.x)/2, (st1_pos.y+text_st2_pos.y)/2)
                    d = distance(center_poly, target_center)
                    if d < min_poly_dist:
                        min_poly_dist = d
                        poly5_st2 = e
        if not poly5_st2:
            continue

        # ITNO 그룹 확정 (색상, 레이어)
        st1.dxf.layer = "ITNO"
        text_st2.dxf.layer = "ITNO"
        poly5_st2.dxf.layer = "ITNO"
        set_entity_color(st1, 1)
        set_entity_color(text_st2, 1)
        set_entity_color(poly5_st2, 1)
        modified = True
        print(f"[ITNO 처리] ITEM: {st1.dxf.text}, 우측: {text_st2.dxf.text}, 5점 POLYLINE: {poly5_st2.dxf.handle}")

        # ITNODN (DN 또는 " 포함) TEXT
        itno_dn_text = None
        for e in msp.query('TEXT'):
            if e is st1 or e is text_st2:
                continue
            pos = get_text_position(e)
            dx = abs(pos.x - st1_pos.x)
            dy = st1_pos.y - pos.y
            if dx <= 2.0 and 0 < dy <= 4.0:
                text_upper = e.dxf.text.upper()
                if "DN" in text_upper or '"' in e.dxf.text:
                    itno_dn_text = e
                    break
        if itno_dn_text:
            itno_dn_text.dxf.layer = "ITNODN"
            set_entity_color(itno_dn_text, 1)
            print(f"   [ITNODN 추가] DN 또는 \" 포함 TEXT: '{itno_dn_text.dxf.text}' 포함")

        # 1. 가장 가까운 2점 또는 3점 폴리라인 (A1) 찾기
        found_A1 = None
        AP1, AP2 = None, None
        min_dist = float("inf")
        # ITEMNO 중심 미리 계산
        itemno_center_temp = Vec2((st1_pos.x + text_st2_pos.x) / 2, (st1_pos.y + text_st2_pos.y) / 2)
        
        for pl in msp.query('LWPOLYLINE POLYLINE'):
            pts = get_poly_points(pl)
            if len(pts) not in [2, 3]:  # 2점 또는 3점 폴리라인만 대상
                continue
            
            # 각 점에서 ITEMNO까지의 거리 계산
            closest_pt = None
            farthest_pt = None
            min_pt_dist = float("inf")
            max_pt_dist = 0
            
            for pt in pts:
                d = min(distance(pt, st1_pos), distance(pt, text_st2_pos))
                if d < min_pt_dist:
                    min_pt_dist = d
                    closest_pt = pt
                # ITEMNO 중심에서 가장 먼 점도 찾기
                d_from_center = distance(pt, itemno_center_temp)
                if d_from_center > max_pt_dist:
                    max_pt_dist = d_from_center
                    farthest_pt = pt
            
            # 전체 후보 중 가장 가까운 것 선택
            if min_pt_dist < min_dist:
                min_dist = min_pt_dist
                found_A1 = pl
                AP1 = closest_pt  # ITEMNO에 가장 가까운 점
                AP2 = farthest_pt  # ITEMNO에서 가장 먼 점
                
        if not found_A1:
            continue
        found_A1.dxf.layer = "A1"
        set_entity_color(found_A1, 4)  # CYAN = 4
        pts_count = len(get_poly_points(found_A1))
        print(f"   [A1] <...>에서 가장 가까운 {pts_count}점 POLYLINE/LWPOLYLINE {found_A1.dxf.handle} (CYAN 색상)")

        # 2. PLINE 찾기 (AP2에서 2mm 이내를 지나는 PIPE 텍스트 포함 레이어)
        found_PLINE = None
        min_pline_dist = float("inf")
        
        # LINE 검색
        for line in msp.query('LINE'):
            if line is found_A1:
                continue
            
            # 레이어에 PIPE 텍스트 포함 확인
            if "PIPE" not in line.dxf.layer.upper():
                continue
                
            # AP2에서 2mm 이내를 지나는지 확인
            if check_line_passes_near_point(line, AP2, 2.0):
                # 중심점과 AP2의 거리로 우선순위 결정
                center = get_pline_center(line)
                if center:
                    dist = distance(center, AP2)
                    if dist < min_pline_dist:
                        min_pline_dist = dist
                        found_PLINE = line
        
        # 폴리라인 검색
        for pl in msp.query('LWPOLYLINE POLYLINE'):
            if pl is found_A1:
                continue
                
            # 레이어에 PIPE 텍스트 포함 확인
            if "PIPE" not in pl.dxf.layer.upper():
                continue
                
            # AP2에서 2mm 이내를 지나는지 확인
            if check_line_passes_near_point(pl, AP2, 2.0):
                # 중심점과 AP2의 거리로 우선순위 결정
                center = get_pline_center(pl)
                if center:
                    dist = distance(center, AP2)
                    if dist < min_pline_dist:
                        min_pline_dist = dist
                        found_PLINE = pl

        if not found_PLINE:
            print(f"   [PLINE 없음] AP2에서 2mm 이내를 지나는 PIPE 포함 레이어를 찾을 수 없습니다.")
            continue
        else:
            print(f"   [PLINE] PIPE 포함 레이어 발견: {found_PLINE.dxf.handle} ({found_PLINE.dxf.layer} 레이어)")

        # PPOS 계산
        ppos = get_pline_center(found_PLINE)
        if not ppos:
            print(f"   [PPOS 오류] PLINE 중심점 계산 실패. 처리 건너뜁니다.")
            continue
        print(f"   [PPOS] PLINE 중심점: ({ppos.x:.2f}, {ppos.y:.2f})")
        
        # PLINE 기울기 계산
        pline_angle = get_pline_angle(found_PLINE)
        print(f"   [PLINE 기울기] {pline_angle:.2f}° (수평=0°, 수직위=90°, 수직아래=-90°)")

        # 3. AD1 찾기 (AP2에서 3점, 전체 길이 5 이하)
        found_AD1 = None
        min_ad1_dist = float("inf")
        
        for pl in msp.query('LWPOLYLINE POLYLINE'):
            if pl is found_A1:
                continue
            pts = get_poly_points(pl)
            
            if len(pts) == 3:
                # 전체 길이 계산
                total_len = get_poly_total_length(pts)
                if total_len > 5:
                    continue
                    
                # AP2에서 가장 가까운 점까지의 거리
                min_dist_to_ap2 = min(distance(pt, AP2) for pt in pts)
                
                if min_dist_to_ap2 < min_ad1_dist:
                    min_ad1_dist = min_dist_to_ap2
                    found_AD1 = pl
        
        if found_AD1:
            found_AD1.dxf.layer = "AD1"
            set_entity_color(found_AD1, 3)  # GREEN = 3
            total_len = get_poly_total_length(get_poly_points(found_AD1))
            print(f"   [AD1] 3점 폴리라인 발견: {found_AD1.dxf.handle}, 전체 길이={total_len:.2f}mm, AP2에서 거리={min_ad1_dist:.2f}mm")
        else:
            print(f"   [AD1 없음] 조건에 맞는 3점 폴리라인을 찾을 수 없습니다.")

        # 4. ITEMNO 그룹 이동 및 회전
        # ITNO 그룹 구성
        itno_entities = [st1, text_st2, poly5_st2]
        if itno_dn_text:
            itno_entities.append(itno_dn_text)

        print("\n   ========== ITEMNO 변환 상세 정보 ==========")
        
        # 이동 전 ITEMNO 중심점
        itno_center_before = get_entity_center(itno_entities)
        print(f"   [이동 전] ITEMNO 중심점: ({itno_center_before.x:.2f}, {itno_center_before.y:.2f})")
        
        # 1. ITEMNO 중심을 PPOS로 이동
        itno_to_ppos_offset = Vec2(ppos.x - itno_center_before.x, ppos.y - itno_center_before.y)
        move_distance = math.sqrt(itno_to_ppos_offset.x**2 + itno_to_ppos_offset.y**2)
        print(f"   [이동1] ITEMNO중심→PPOS 오프셋: ({itno_to_ppos_offset.x:.2f}, {itno_to_ppos_offset.y:.2f})")
        print(f"   [이동1] 이동 거리: {move_distance:.2f}mm")
        
        for ent in itno_entities:
            move_entity(ent, itno_to_ppos_offset)
        print(f"   [이동1 실행] ITEMNO 중심을 PPOS로 이동 완료")
        
        # 2. PPOS 중심으로 PLINE 기울기만큼 회전
        for ent in itno_entities:
            rotate_entity_around(ent, ppos, pline_angle)
        print(f"   [회전 실행] PPOS 중심으로 {pline_angle:.2f}° 회전 완료")

        # 3. PLINE 수직 방향으로 이동 (DN/" 포함 여부에 따라 거리 조정)
        perp_angle = pline_angle + 90
        move_distance_perp = 1.65 if itno_dn_text else 2.5
        perp_offset = get_perpendicular_offset(pline_angle, move_distance_perp)
        print(f"   [이동2] PLINE 수직 방향: {perp_angle:.2f}°")
        print(f"   [이동2] 수직 이동 거리: {move_distance_perp}mm (DN/\" {'포함' if itno_dn_text else '미포함'})")
        print(f"   [이동2] 수직 이동 벡터: ({perp_offset.x:.2f}, {perp_offset.y:.2f})")
        
        for ent in itno_entities:
            move_entity(ent, perp_offset)
        print(f"   [이동2 실행] PLINE 수직 방향으로 {move_distance_perp}mm 이동 완료")
        
        # 최종 위치 확인
        itno_center_final = get_entity_center(itno_entities)
        print(f"   [최종 위치] ITEMNO 중심점: ({itno_center_final.x:.2f}, {itno_center_final.y:.2f})")
        print("   ==========================================\n")

        # 5. 각도 보정 및 텍스트 순서 보정
        # 5-1. PLINE 각도가 -89도 이하일 때 180도 회전
        if pline_angle <= -89:
            set_mirrtext_zero(doc)
            print(f"\n   [각도 보정] PLINE 각도가 {pline_angle:.2f}° (≤-89°)이므로 PPOS 중심으로 180도 회전")
            for ent in itno_entities:
                rotate_entity_around(ent, ppos, 180)
            print("   [각도 보정] 180도 회전 완료, MIRRTEXT=0 설정")

        # 5-2. ST1.x > ST2.x일 때 180도 회전 후 PLINE 직교 방향 -6mm 이동
        st1_pos_current = get_text_position(st1)
        st2_pos_current = get_text_position(text_st2)
        
        if st1_pos_current.x > st2_pos_current.x:
            set_mirrtext_zero(doc)
            print(f"\n   [텍스트 순서 보정] <...> 텍스트가 숫자보다 오른쪽에 있음")
            print(f"   [텍스트 순서 보정] ST1 X: {st1_pos_current.x:.2f} > ST2 X: {st2_pos_current.x:.2f}")
            
            # ITEMNO 그룹 중심점 계산
            itno_center_before_correction = get_entity_center(itno_entities)
            
            # 180도 회전 (중심점 기준)
            for ent in itno_entities:
                rotate_entity_around(ent, itno_center_before_correction, 180)
            print(f"   [텍스트 순서 보정] 중심점({itno_center_before_correction.x:.2f}, {itno_center_before_correction.y:.2f}) 기준 180도 회전 완료")
            
            # PLINE 직교 방향으로 -6mm 이동
            perp_offset_correction = get_perpendicular_offset(pline_angle, -6)
            for ent in itno_entities:
                move_entity(ent, perp_offset_correction)
            print(f"   [텍스트 순서 보정] PLINE 직교 방향으로 -6mm 추가 이동 완료")
            print(f"   [텍스트 순서 보정] 이동 벡터: ({perp_offset_correction.x:.2f}, {perp_offset_correction.y:.2f})")

        # 6. A1과 AD1 삭제
        to_remove = []
        if found_A1:
            to_remove.append((found_A1, f"A1: {getattr(found_A1.dxf, 'handle', 'unknown')}"))
        if found_AD1:
            to_remove.append((found_AD1, f"AD1: {getattr(found_AD1.dxf, 'handle', 'unknown')}"))
            
        # 7. AD1의 어느 한점과 접하는 1mm 이하의 ARROW 레이어 LINE 삭제
        if found_AD1:
            ad1_points = get_poly_points(found_AD1)
            for line in msp.query('LINE'):
                try:
                    if not hasattr(line, 'dxf') or not hasattr(line.dxf, 'layer'):
                        continue
                    if line.dxf.layer.upper() != "ARROW":
                        continue
                        
                    start = Vec2(line.dxf.start.x, line.dxf.start.y)
                    end = Vec2(line.dxf.end.x, line.dxf.end.y)
                    line_length = distance(start, end)
                    
                    # 1mm 이하 LINE만
                    if line_length > 1.0:
                        continue
                        
                    # AD1의 어느 한점과 접하는지 확인
                    for ad1_pt in ad1_points:
                        if distance(ad1_pt, start) < 0.01 or distance(ad1_pt, end) < 0.01:
                            handle = getattr(line.dxf, 'handle', 'unknown')
                            to_remove.append((line, f"ARROW LINE: {handle} (AD1 접촉, 길이={line_length:.3f}mm)"))
                            break
                except Exception as ex:
                    print(f"   [검사오류] ARROW LINE 검사 중 오류: {ex}")
                    continue
        
        # 삭제 실행
        deleted_count = 0
        for entity, description in to_remove:
            try:
                msp.delete_entity(entity)
                print(f"   [삭제] {description}")
                deleted_count += 1
            except Exception as ex:
                print(f"   [삭제오류] {description} / {ex}")

        print(f"   [삭제완료] 총 {deleted_count}개 엔티티 삭제")

    save_path = os.path.splitext(file_path)[0] + "_ITNO.dxf"
    try:
        doc.saveas(save_path)
        print(f"[✔] 저장 완료: {os.path.basename(save_path)}")
    except Exception as e:
        print(f"[!] 저장 오류: {e}")

if __name__ == "__main__":
    files = select_files()
    if not files:
        print("❗ DXF 파일을 선택하지 않았습니다.")
    else:
        for f in files:
            process_dxf(f)
        print("▶ 모든 파일 처리 완료.")