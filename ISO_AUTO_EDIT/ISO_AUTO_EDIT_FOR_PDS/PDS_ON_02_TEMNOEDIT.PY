import ezdxf
import os
import sys
import math
from ezdxf.math import Vec2

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
        pass

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
        pass

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
            return calc_angle_deg(pts[0], pts[-1])
    return 0

def check_line_passes_near_point(entity, point, threshold=2.0):
    """LINE이나 폴리라인이 점 근처를 지나는지 확인"""
    if entity.dxftype() == "LINE":
        start = Vec2(entity.dxf.start.x, entity.dxf.start.y)
        end = Vec2(entity.dxf.end.x, entity.dxf.end.y)
        line_vec = Vec2(end.x - start.x, end.y - start.y)
        line_len = math.sqrt(line_vec.x**2 + line_vec.y**2)
        if line_len == 0:
            return distance(point, start) <= threshold
        
        t = max(0, min(1, ((point.x - start.x) * line_vec.x + (point.y - start.y) * line_vec.y) / (line_len**2)))
        closest_point = Vec2(start.x + t * line_vec.x, start.y + t * line_vec.y)
        return distance(point, closest_point) <= threshold
        
    elif entity.dxftype() in ("LWPOLYLINE", "POLYLINE"):
        pts = get_poly_points(entity)
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
    except Exception as e:
        pass

class EntityCache:
    """엔티티 캐싱을 통한 성능 최적화 - 시간복잡도 O(n²) → O(n)으로 개선"""
    def __init__(self, msp):
        self.all_texts = list(msp.query('TEXT'))
        self.all_polylines = list(msp.query('LWPOLYLINE POLYLINE'))
        self.all_lines = list(msp.query('LINE'))
        
        # 텍스트 엔티티들을 미리 분류
        self.rotation_zero_texts = [t for t in self.all_texts if getattr(t.dxf, 'rotation', 0) == 0]
        self.bracket_texts = [t for t in self.rotation_zero_texts if '<' in t.dxf.text and '>' in t.dxf.text]
        
        # 폴리라인을 점 개수별로 미리 분류
        self.poly_by_points = {}
        for pl in self.all_polylines:
            pts = get_poly_points(pl)
            point_count = len(pts)
            if point_count not in self.poly_by_points:
                self.poly_by_points[point_count] = []
            self.poly_by_points[point_count].append((pl, pts))
        
        # PIPE 포함 레이어 엔티티들 미리 필터링
        self.pipe_lines = [line for line in self.all_lines if "PIPE" in line.dxf.layer.upper()]
        self.pipe_polylines = [pl for pl in self.all_polylines if "PIPE" in pl.dxf.layer.upper()]

def process_document(doc):
    """in-memory 연동용 처리 함수"""
    msp = doc.modelspace()
    cache = EntityCache(msp)
    modified = False

    # 메인 처리 로직 - 캐시된 엔티티 사용으로 최적화
    for st1 in cache.bracket_texts:
        st1_pos = get_text_position(st1)

        # 오른쪽 25mm, Y±5mm 범위 내 숫자 텍스트 찾기 - 캐시 활용
        candidate_texts = []
        for e in cache.rotation_zero_texts:
            if e is st1:
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

        # 5점 폴리라인 찾기 - 캐시 활용
        min_poly_dist = float('inf')
        poly5_st2 = None
        if 5 in cache.poly_by_points:
            for pl, pts in cache.poly_by_points[5]:
                dx = pts[0].x - st1_pos.x
                dy = abs(pts[0].y - st1_pos.y)
                if 0 < dx <= 25 and dy <= 5:
                    cx = sum([p.x for p in pts])/5
                    cy = sum([p.y for p in pts])/5
                    center_poly = Vec2(cx, cy)
                    target_center = Vec2((st1_pos.x+text_st2_pos.x)/2, (st1_pos.y+text_st2_pos.y)/2)
                    d = distance(center_poly, target_center)
                    if d < min_poly_dist:
                        min_poly_dist = d
                        poly5_st2 = pl
        if not poly5_st2:
            continue

        # ITNO 그룹 설정
        st1.dxf.layer = "ITNO"
        text_st2.dxf.layer = "ITNO"
        poly5_st2.dxf.layer = "ITNO"
        set_entity_color(st1, 1)
        set_entity_color(text_st2, 1)
        set_entity_color(poly5_st2, 1)
        modified = True

        # ITNODN 텍스트 찾기
        itno_dn_text = None
        for e in cache.all_texts:
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

        # A1 찾기 - 2점 또는 3점 폴리라인
        found_A1 = None
        AP1, AP2 = None, None
        min_dist = float("inf")
        itemno_center_temp = Vec2((st1_pos.x + text_st2_pos.x) / 2, (st1_pos.y + text_st2_pos.y) / 2)
        
        for point_count in [2, 3]:
            if point_count in cache.poly_by_points:
                for pl, pts in cache.poly_by_points[point_count]:
                    closest_pt = None
                    farthest_pt = None
                    min_pt_dist = float("inf")
                    max_pt_dist = 0
                    
                    for pt in pts:
                        d = min(distance(pt, st1_pos), distance(pt, text_st2_pos))
                        if d < min_pt_dist:
                            min_pt_dist = d
                            closest_pt = pt
                        d_from_center = distance(pt, itemno_center_temp)
                        if d_from_center > max_pt_dist:
                            max_pt_dist = d_from_center
                            farthest_pt = pt
                    
                    if min_pt_dist < min_dist:
                        min_dist = min_pt_dist
                        found_A1 = pl
                        AP1 = closest_pt
                        AP2 = farthest_pt
                        
        if not found_A1:
            continue
        found_A1.dxf.layer = "A1"
        set_entity_color(found_A1, 4)

        # PLINE 찾기 - 캐시 활용
        found_PLINE = None
        min_pline_dist = float("inf")
        
        # 캐시된 PIPE LINE들 검색
        for line in cache.pipe_lines:
            if line is found_A1:
                continue
            if check_line_passes_near_point(line, AP2, 2.0):
                center = get_pline_center(line)
                if center:
                    dist = distance(center, AP2)
                    if dist < min_pline_dist:
                        min_pline_dist = dist
                        found_PLINE = line
        
        # 캐시된 PIPE 폴리라인들 검색
        for pl in cache.pipe_polylines:
            if pl is found_A1:
                continue
            if check_line_passes_near_point(pl, AP2, 2.0):
                center = get_pline_center(pl)
                if center:
                    dist = distance(center, AP2)
                    if dist < min_pline_dist:
                        min_pline_dist = dist
                        found_PLINE = pl

        if not found_PLINE:
            continue

        # PPOS 계산
        ppos = get_pline_center(found_PLINE)
        if not ppos:
            continue
        
        pline_angle = get_pline_angle(found_PLINE)

        # AD1 찾기 - 캐시 활용
        found_AD1 = None
        min_ad1_dist = float("inf")
        
        if 3 in cache.poly_by_points:
            for pl, pts in cache.poly_by_points[3]:
                if pl is found_A1:
                    continue
                total_len = get_poly_total_length(pts)
                if total_len > 5:
                    continue
                    
                min_dist_to_ap2 = min(distance(pt, AP2) for pt in pts)
                
                if min_dist_to_ap2 < min_ad1_dist:
                    min_ad1_dist = min_dist_to_ap2
                    found_AD1 = pl
        
        if found_AD1:
            found_AD1.dxf.layer = "AD1"
            set_entity_color(found_AD1, 3)

        # ITEMNO 그룹 이동 및 회전
        itno_entities = [st1, text_st2, poly5_st2]
        if itno_dn_text:
            itno_entities.append(itno_dn_text)

        # 1. ITEMNO 중심을 PPOS로 이동
        itno_center_before = get_entity_center(itno_entities)
        itno_to_ppos_offset = Vec2(ppos.x - itno_center_before.x, ppos.y - itno_center_before.y)
        
        for ent in itno_entities:
            move_entity(ent, itno_to_ppos_offset)
        
        # 2. PPOS 중심으로 회전
        for ent in itno_entities:
            rotate_entity_around(ent, ppos, pline_angle)

        # 3. PLINE 수직 방향으로 이동
        move_distance_perp = 1.65 if itno_dn_text else 2.5
        perp_offset = get_perpendicular_offset(pline_angle, move_distance_perp)
        
        for ent in itno_entities:
            move_entity(ent, perp_offset)

        # 4. 각도 보정
        if pline_angle <= -89:
            set_mirrtext_zero(doc)
            for ent in itno_entities:
                rotate_entity_around(ent, ppos, 180)

        # 5. 텍스트 순서 보정
        st1_pos_current = get_text_position(st1)
        st2_pos_current = get_text_position(text_st2)
        
        if st1_pos_current.x > st2_pos_current.x:
            set_mirrtext_zero(doc)
            itno_center_before_correction = get_entity_center(itno_entities)
            
            for ent in itno_entities:
                rotate_entity_around(ent, itno_center_before_correction, 180)
            
            perp_offset_correction = get_perpendicular_offset(pline_angle, -6)
            for ent in itno_entities:
                move_entity(ent, perp_offset_correction)

        # 6. 엔티티 삭제 준비
        to_remove = []
        if found_A1:
            to_remove.append(found_A1)
        if found_AD1:
            to_remove.append(found_AD1)
            
            # AD1 접촉 ARROW LINE 찾기
            ad1_points = get_poly_points(found_AD1)
            for line in cache.all_lines:
                try:
                    if not hasattr(line, 'dxf') or not hasattr(line.dxf, 'layer'):
                        continue
                    if line.dxf.layer.upper() != "ARROW":
                        continue
                        
                    start = Vec2(line.dxf.start.x, line.dxf.start.y)
                    end = Vec2(line.dxf.end.x, line.dxf.end.y)
                    line_length = distance(start, end)
                    
                    if line_length > 1.0:
                        continue
                        
                    for ad1_pt in ad1_points:
                        if distance(ad1_pt, start) < 0.01 or distance(ad1_pt, end) < 0.01:
                            to_remove.append(line)
                            break
                except:
                    continue
        
        # 삭제 실행
        for entity in to_remove:
            try:
                msp.delete_entity(entity)
            except:
                pass

    return modified

def process_dxf_file(file_path):
    """DXF 파일 처리 함수"""
    try:
        doc = ezdxf.readfile(file_path)
    except Exception as e:
        return False

    modified = process_document(doc)
    
    if modified:
        save_path = os.path.splitext(file_path)[0] + "_ITNO.dxf"
        try:
            doc.saveas(save_path)
            return True
        except Exception as e:
            return False
    
    return False

def main():
    """메인 함수 - 커맨드라인 인자 처리"""
    if len(sys.argv) < 2:
        return
    
    dxf_files = sys.argv[1:]
    
    for file_path in dxf_files:
        if not os.path.exists(file_path):
            continue
        if not file_path.lower().endswith('.dxf'):
            continue
            
        process_dxf_file(file_path)

if __name__ == "__main__":
    main()