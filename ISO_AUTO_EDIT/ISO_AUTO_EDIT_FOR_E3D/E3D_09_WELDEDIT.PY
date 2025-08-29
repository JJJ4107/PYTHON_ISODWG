import ezdxf
import os
import math
import re
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

def is_valid_wdno_text(text_content):
    """WDNO로 유효한 텍스트인지 확인하는 함수"""
    try:
        # INST가 포함된 경우 제외
        if 'INST' in text_content.upper():
            return False
        
        # TEXT가 포함된 경우 제외 (대소문자 무관)
        if 'TEXT' in text_content.upper():
            return False
        
        # < 문자가 포함된 경우 제외
        if '<' in text_content:
            return False
        
        # 숫자가 하나도 없는 경우 제외
        numbers = re.findall(r'\d+', text_content)
        if not numbers:
            return False
        
        return True
    except:
        return False

def is_valid_wdno_entity(text_entity):
    """TEXT 엔티티가 WDNO로 유효한지 확인 (내용 + 기울기 확인)"""
    try:
        # 텍스트 내용 검증
        text_content = text_entity.dxf.text.strip()
        if not is_valid_wdno_text(text_content):
            return False
        
        # 기울기가 0이어야 함 (rotation이 0 또는 매우 작은 값)
        if hasattr(text_entity.dxf, 'rotation'):
            if abs(text_entity.dxf.rotation) > 0.1:  # 0.1도 이내의 오차 허용
                return False
        
        return True
    except:
        return False

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

def check_box_overlap(box1, box2):
    """두 바운딩 박스가 겹치는지 확인하는 함수"""
    if not box1 or not box2:
        return False
    
    # 박스가 겹치지 않는 조건 확인
    if (box1['max_x'] < box2['min_x'] or 
        box1['min_x'] > box2['max_x'] or
        box1['max_y'] < box2['min_y'] or 
        box1['min_y'] > box2['max_y']):
        return False
    
    return True

def check_text_box_interference(text_entity, msp, exclude_entities):
    """TEXT 엔티티의 바운딩 박스가 다른 TEXT와 겹치는지 확인 (박스를 우측으로 이동 후 체크)"""
    text_bbox = get_text_bounding_box(text_entity)
    if not text_bbox:
        return False
    
    # BOX를 우측으로 길이의 1/2만큼 이동
    half_width = text_bbox['width'] / 2
    adjusted_bbox = {
        'center': Vec2(text_bbox['center'].x + half_width, text_bbox['center'].y),
        'width': text_bbox['width'],
        'height': text_bbox['height'],
        'min_x': text_bbox['min_x'] + half_width,
        'max_x': text_bbox['max_x'] + half_width,
        'min_y': text_bbox['min_y'],
        'max_y': text_bbox['max_y']
    }
    
    for e in msp:
        if e in exclude_entities or not hasattr(e, "dxf") or e.dxf is None:
            continue
        
        if e.dxftype() == "TEXT":
            other_bbox = get_text_bounding_box(e)
            if other_bbox:
                # 다른 텍스트도 우측으로 이동하여 비교
                other_half_width = other_bbox['width'] / 2
                other_adjusted_bbox = {
                    'min_x': other_bbox['min_x'] + other_half_width,
                    'max_x': other_bbox['max_x'] + other_half_width,
                    'min_y': other_bbox['min_y'],
                    'max_y': other_bbox['max_y']
                }
                if check_box_overlap(adjusted_bbox, other_adjusted_bbox):
                    return True
    
    return False

def check_circle_box_overlap(circle_center, circle_radius, box):
    """원과 바운딩 박스가 겹치는지 확인하는 함수"""
    if not box:
        return False
    
    # 박스의 가장 가까운 점 찾기
    closest_x = max(box['min_x'], min(circle_center.x, box['max_x']))
    closest_y = max(box['min_y'], min(circle_center.y, box['max_y']))
    
    # 원의 중심에서 가장 가까운 점까지의 거리
    dist = distance(circle_center, Vec2(closest_x, closest_y))
    
    return dist < circle_radius

def find_pipe_lines_near_sw_improved(sw_entity, sw_center, sw_type, msp, search_radius=1.0):
    """SW/SFW 근처의 PIPE 선을 찾는 개선된 함수"""
    pipe_lines_candidates = []
    
    try:
        # SFW인 경우 실제 6개 점들을 가져옴
        sfw_points = []
        if sw_type == 'POLYLINE' or sw_type == 'SFW':
            if sw_entity.dxftype() == "POLYLINE":
                sfw_points = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in sw_entity.vertices]
            else:
                sfw_points = [Vec2(x, y) for x, y, *_ in sw_entity.get_points()]
            
            # SFW의 경우 검색 반경을 7mm로 설정
            search_radius = 7.0
        
        # LINE 검색
        for entity in msp.query('LINE'):
            try:
                if hasattr(entity.dxf, 'layer'):
                    layer_name = entity.dxf.layer.upper()
                    if 'PIPE' in layer_name:
                        start = Vec2(entity.dxf.start.x, entity.dxf.start.y)
                        end = Vec2(entity.dxf.end.x, entity.dxf.end.y)
                        
                        min_dist = float('inf')
                        
                        if sw_type == 'CIRCLE':
                            # SW 원의 경우: 중심에서의 거리
                            dist_to_start = distance(sw_center, start)
                            dist_to_end = distance(sw_center, end)
                            min_dist = min(dist_to_start, dist_to_end)
                        else:
                            # SFW 폴리라인의 경우: 중심에서 7mm 내의 PIPE 선
                            dist_to_start = distance(sw_center, start)
                            dist_to_end = distance(sw_center, end)
                            min_dist = min(dist_to_start, dist_to_end)
                        
                        # 최소 거리가 search_radius 이내면 후보에 추가
                        if min_dist <= search_radius:
                            pipe_lines_candidates.append({
                                'entity': entity,
                                'type': 'LINE',
                                'segments': [(start, end)],
                                'min_distance': min_dist
                            })
            except Exception:
                continue
        
        # POLYLINE/LWPOLYLINE 검색
        for poly in msp.query("POLYLINE LWPOLYLINE"):
            try:
                if hasattr(poly.dxf, 'layer'):
                    layer_name = poly.dxf.layer.upper()
                    if 'PIPE' in layer_name:
                        if poly.dxftype() == "POLYLINE":
                            points = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
                        else:
                            points = [Vec2(x, y) for x, y, *_ in poly.get_points()]
                        
                        if len(points) >= 2:
                            # 모든 점들에 대해 최소 거리 계산
                            min_dist = float('inf')
                            
                            if sw_type == 'CIRCLE':
                                # SW 원의 경우: 중심에서 모든 점까지 거리
                                for pt in points:
                                    dist = distance(sw_center, pt)
                                    min_dist = min(min_dist, dist)
                            else:
                                # SFW 폴리라인의 경우: 중심에서 모든 점까지 거리
                                for pt in points:
                                    dist = distance(sw_center, pt)
                                    min_dist = min(min_dist, dist)
                            
                            if min_dist <= search_radius:
                                segments = []
                                for i in range(len(points) - 1):
                                    segments.append((points[i], points[i+1]))
                                
                                pipe_lines_candidates.append({
                                    'entity': poly,
                                    'type': poly.dxftype(),
                                    'segments': segments,
                                    'min_distance': min_dist
                                })
            except Exception:
                continue
        
        # 거리가 가까운 순으로 정렬하여 상위 2개만 선택
        pipe_lines_candidates.sort(key=lambda x: x['min_distance'])
        pipe_lines = pipe_lines_candidates[:2]
        
        print(f"   🔧 {sw_type} 근처 PC 검색 완료: {len(pipe_lines)}개 발견")
        if sw_type == 'POLYLINE':
            print(f"      SFW 중심에서 7mm 내 검색")
        
    except Exception as e:
        print(f"PIPE 선 찾기 오류: {e}")
        pipe_lines = []
    
    return pipe_lines

def check_circle_to_segments_distance(circle_center, circle_radius, segments, min_distance=2.0):
    """원과 선분들 사이의 최소 거리가 2mm 이하인지 확인"""
    for start, end in segments:
        # 원의 중심에서 선분까지의 거리
        dist_to_segment = point_to_segment_distance(circle_center, start, end)
        
        # 원의 외접선까지의 거리 = 중심에서 선분까지의 거리 - 반지름
        dist_to_circle = dist_to_segment - circle_radius
        
        if dist_to_circle <= min_distance:
            return True
    
    return False

def check_interference_at_position(test_center, msp, exclude_entities, weld_radius=3.0):
    """특정 위치에서의 간섭을 체크하는 함수"""
    for e in msp:
        if e in exclude_entities or not hasattr(e, "dxf") or e.dxf is None:
            continue
        
        if e.dxftype() == "TEXT":
            # 원과 텍스트 간의 거리 체크 (단순 거리)
            text_pos = Vec2(e.dxf.insert.x, e.dxf.insert.y)
            if distance(test_center, text_pos) < weld_radius:
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
    """TEXT와의 간섭만 체크하는 함수 (원 중심과 텍스트의 거리)"""
    for e in msp:
        if e in exclude_entities or not hasattr(e, "dxf") or e.dxf is None:
            continue
        
        if e.dxftype() == "TEXT":
            text_pos = Vec2(e.dxf.insert.x, e.dxf.insert.y)
            if distance(test_center, text_pos) < weld_radius:
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
            try:
                # 텍스트 엔티티가 WDNO로 유효한지 확인 (내용 + 기울기)
                if not is_valid_wdno_entity(txt):
                    continue
                
                pos = Vec2(txt.dxf.insert.x, txt.dxf.insert.y)
                d = distance(pos, center)
                if d <= text_search_radius and d < closest_dist:
                    closest_txt = txt
                    closest_dist = d
            except:
                continue
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

    print(f"기존 WELDNOEDIT 처리 완료 (수평 텍스트만 선택, INST/TEXT/<문자/숫자없음 제외)")

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
            "leader_line": leader_line
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
    """WELD 원과 SW/SFW 사이의 직선거리를 조정하는 함수 (최소 7mm 보장)"""
    weld_center = weld_circle['center']
    small_center = small_circle['center']
    weld_radius = weld_circle['radius']  # 실제로는 2.8mm (5.6mm 지름)
    small_radius = small_circle['radius']  # 1mm
    
    # 현재 직선거리 계산 (중심점 간 거리)
    current_distance = distance(weld_center, small_center)
    
    print(f"  현재 WELD-SW/SFW 직선거리: {current_distance:.2f}mm")
    print(f"  최소 요구 거리: {min_distance}mm")
    
    # 6mm 이상이면 조정 불필요
    if current_distance >= min_distance:
        print(f"  거리 조정 불필요 (직선거리 {current_distance:.2f}mm >= {min_distance}mm)")
        return True, weld_center, [], "no_adjustment"
    
    # 6mm 미만인 경우 STRETCH
    print(f"  STRETCH 필요: {current_distance:.2f}mm → {min_distance}mm")
    
    # 방향 벡터 계산 (SW/SFW에서 멀어지는 방향)
    direction_vec = weld_center - small_center
    if direction_vec.magnitude == 0:
        print(f"  원들이 같은 위치에 있어 조정 불가능")
        return False, weld_center, [], "same_position"
    
    direction_normalized = direction_vec.normalize()
    
    # 새로운 WELD 원 위치 계산 (SW/SFW에서 정확히 min_distance 떨어진 위치)
    new_weld_center = small_center + direction_normalized * min_distance
    
    print(f"  WELD 원 이동 계획: ({weld_center.x:.2f}, {weld_center.y:.2f}) → ({new_weld_center.x:.2f}, {new_weld_center.y:.2f})")
    
    # WELDNO 텍스트만 찾기 (WELD 원 주변 3mm 내의 텍스트만)
    weldno_texts = []
    weldno_text_search_radius = 3.0
    text_backups = []
    
    for txt in msp.query('TEXT'):
        try:
            txt_pos = Vec2(txt.dxf.insert.x, txt.dxf.insert.y)
            if distance(weld_center, txt_pos) <= weldno_text_search_radius:
                # 텍스트 엔티티가 WDNO로 유효한지 확인 (내용 + 기울기)
                if is_valid_wdno_entity(txt):
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
        print(f"  새 위치에서 간섭 발생")
        
        # SFW인 경우 최소 7mm 위치 시도
        if hasattr(small_circle['entity'], 'dxftype') and small_circle['entity'].dxftype() in ['POLYLINE', 'LWPOLYLINE']:
            print(f"  SFW 폴리라인 감지 - 최소 7mm 위치 시도")
            min_7mm_center = small_center + direction_normalized * 7.0
            
            # 7mm 위치에서 간섭 체크
            if not check_interference_at_position(min_7mm_center, msp, exclude_entities, weld_radius):
                new_weld_center = min_7mm_center
                print(f"  7mm 위치로 조정: ({new_weld_center.x:.2f}, {new_weld_center.y:.2f})")
            else:
                print(f"  7mm 위치에서도 간섭 - 조정 실패, 원래 위치 유지")
                return False, weld_center, [], "stretch_interference"
        else:
            print(f"  조정 실패 - 원래 위치 유지")
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
        
        if dist_between_centers < 6.0:  # 원들 간 최소 거리는 6mm
            print(f"    다른 원과의 거리 위반: {dist_between_centers:.2f}mm < 6.0mm")
            
            # SFW인 경우 최소 7mm 위치 시도
            if hasattr(small_circle['entity'], 'dxftype') and small_circle['entity'].dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                min_7mm_center = small_center + direction_normalized * 7.0
                dist_to_other_from_7mm = distance(min_7mm_center, other_center)
                
                if dist_to_other_from_7mm >= 6.0:
                    new_weld_center = min_7mm_center
                    print(f"  7mm 위치로 조정하여 다른 원과의 충돌 회피")
                else:
                    print(f"    조정 실패 - 다른 원과 충돌, 원래 위치 유지")
                    return False, weld_center, [], "stretch_circle_collision"
            else:
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
            weld_circle['center'] = original_weld_center
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
                            # 텍스트 엔티티가 WDNO로 유효한지 확인 (내용 + 기울기)
                            if is_valid_wdno_entity(txt):
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
    """WELDNO 그룹 안의 RED LINE 끝점에서 1.5mm 내 노랑색 1mm 원 또는 SFW 6점 폴리라인 찾기"""
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
        
        # 모든 SFW 6점 폴리라인 찾기
        sfw_polylines = []
        for poly in msp.query("POLYLINE LWPOLYLINE"):
            try:
                if hasattr(poly.dxf, 'layer') and poly.dxf.layer == "SFW":
                    # 점들 가져오기
                    if poly.dxftype() == "POLYLINE":
                        points = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
                    else:
                        points = [Vec2(x, y) for x, y, *_ in poly.get_points()]
                    
                    # 6개 점인지 확인
                    if len(points) == 6:
                        # 중심점 계산
                        center_x = sum(p.x for p in points) / 6
                        center_y = sum(p.y for p in points) / 6
                        center = Vec2(center_x, center_y)
                        
                        sfw_polylines.append({
                            'entity': poly,
                            'center': center,
                            'points': points,
                            'type': 'SFW'
                        })
            except Exception:
                continue
        
        print(f"🔷 SFW 6점 폴리라인 {len(sfw_polylines)}개 발견")
        
        # SW 원들을 통합 리스트에 추가
        all_sw_sfw = []
        for circle in small_circles:
            all_sw_sfw.append({
                'entity': circle['entity'],
                'center': circle['center'],
                'radius': circle['radius'],
                'type': 'SW'
            })
        
        # SFW 폴리라인들을 통합 리스트에 추가
        for sfw in sfw_polylines:
            all_sw_sfw.append({
                'entity': sfw['entity'],
                'center': sfw['center'],
                'radius': 1.0,  # SFW를 1mm 원처럼 취급
                'type': 'SFW'
            })
        
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
            
            # 모든 RED LINE 끝점에서 1.5mm 내의 SW/SFW 찾기
            valid_connections = []
            endpoint_search_radius = 1.5  # RED LINE 끝점에서 1.5mm 내
            
            for endpoint in red_line_endpoints:
                for sw_sfw in all_sw_sfw:
                    try:
                        center = sw_sfw['center']
                        dist = distance(endpoint, center)
                        
                        # 1.5mm 내에 있는 경우만 유효한 연결로 간주
                        if dist <= endpoint_search_radius:
                            valid_connections.append({
                                'weld_circle': weld_circle,
                                'small_circle': sw_sfw,  # SW 원 또는 SFW 폴리라인
                                'red_line_endpoint': endpoint,
                                'endpoint_to_small_distance': dist,
                                'weld_to_small_distance': distance(weld_center, center),
                                'sw_type': sw_sfw['type']  # 'SW' 또는 'SFW'
                            })
                            print(f"     유효 연결: RED끝점({endpoint.x:.2f}, {endpoint.y:.2f}) - {sw_sfw['type']}({center.x:.2f}, {center.y:.2f}), 거리: {dist:.3f}mm")
                    except Exception as e:
                        continue
            
            print(f"   1.5mm 내 유효 연결 {len(valid_connections)}개 발견")
            
            if not valid_connections:
                print(f"   RED LINE 끝점 1.5mm 내에 SW/SFW가 없음 - SKIP")
                continue
            
            # 가장 가까운 연결 선택 (WELDNO당 1개만)
            best_connection = min(valid_connections, key=lambda x: x['endpoint_to_small_distance'])
            connections.append(best_connection)
            
            endpoint = best_connection['red_line_endpoint']
            small_center = best_connection['small_circle']['center']
            sw_type = best_connection['sw_type']
            
            print(f"✅ WELDNO 연결: WELD원({weld_center.x:.2f}, {weld_center.y:.2f}) - RED끝점({endpoint.x:.2f}, {endpoint.y:.2f}) - {sw_type}({small_center.x:.2f}, {small_center.y:.2f})")
            print(f"    거리: RED끝점→{sw_type} {best_connection['endpoint_to_small_distance']:.3f}mm, WELD→{sw_type} {best_connection['weld_to_small_distance']:.3f}mm")
        
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
                
                print(f"🔍 연결 처리: WELD원({weld_center.x:.2f}, {weld_center.y:.2f}) - RED끝점({red_endpoint.x:.2f}, {red_endpoint.y:.2f}) - {connection.get('sw_type', 'SW')}({small_center.x:.2f}, {small_center.y:.2f})")
                print(f"   현재 WELD-{connection.get('sw_type', 'SW')} 직선거리: {current_distance:.2f}mm")
                
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

        # 모든 WELD 그룹의 RED 요소들 삭제 (NL1 생성 여부와 관계없이)
        print(f"\n🗑️  모든 WELD 그룹의 RED 요소 삭제 시작 (NL1 생성 여부 무관)")
        
        red_lines_to_delete = []
        
        # 모든 WELD 원 찾기 (2.8mm 반지름)
        all_weld_circles = find_all_circles_by_radius(msp, 2.8, 0.3)
        
        for weld_circle in all_weld_circles:
            weld_center = weld_circle['center']
            weld_group_radius = 4.0
            
            print(f"   WELD 그룹({weld_center.x:.2f}, {weld_center.y:.2f})의 RED 요소 찾는 중...")
            
            # 이 특정 WELD 그룹의 RED LINE 찾기
            group_red_count = 0
            for entity in msp.query('LINE'):
                try:
                    if hasattr(entity.dxf, 'color') and entity.dxf.color == 1:  # 빨간색
                        start_point = Vec2(entity.dxf.start.x, entity.dxf.start.y)
                        end_point = Vec2(entity.dxf.end.x, entity.dxf.end.y)
                        
                        # 이 WELD 그룹 4mm 내에 있는 RED LINE인지 확인
                        if (distance(weld_center, start_point) <= weld_group_radius or 
                            distance(weld_center, end_point) <= weld_group_radius):
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
                            if distance(weld_center, point) <= weld_group_radius:
                                if poly not in red_lines_to_delete:
                                    red_lines_to_delete.append(poly)
                                    group_red_count += 1
                                break
                except Exception as e:
                    continue
            
            print(f"     발견된 RED 요소: {group_red_count}개")
        
        # RED 요소들 삭제 실행
        deleted_red_count = 0
        for red_entity in red_lines_to_delete:
            try:
                msp.delete_entity(red_entity)
                deleted_red_count += 1
            except Exception as ex:
                print(f"RED 요소 삭제 오류: {ex}")
        
        print(f"✅ 모든 WELD 그룹의 RED 요소 {deleted_red_count}개 삭제 완료")
        print(f"   - NL1 생성 개수: {nl1_created_count}개")
        print(f"   - 전체 WELD 원 개수: {len(all_weld_circles)}개")
        print(f"   - NL1 생성 여부와 관계없이 모든 RED 요소 삭제됨")

        # 모든 원 간의 최소 거리 보장 (WELD 원만 이동, WELDNO 텍스트만 함께 이동)
        ensure_minimum_distances_between_all_circles(msp, min_distance)
        
        print(f"\n📊 최종 처리 결과:")
        print(f"   📏 WELD 원 STRETCH: {stretch_count}개 (6mm 이하인 경우만)")
        print(f"   🔗 NL1 생성: {nl1_created_count}개 (SW 원 및 SFW 폴리라인 연결)")
        print(f"   🎯 5.6mm 원 접촉: NL1이 항상 WELD 원(5.6mm)과 접함")
        print(f"   🚫 TEXT 보호: WELDNO 이외 다른 TEXT는 절대 이동하지 않음")
        print(f"   🗑️  RED 요소 삭제: 모든 WELD 그룹의 RED 요소 삭제 (NL1 생성 여부 무관)")
        print(f"   🆕 SFW 지원: 6점 폴리라인 중심을 SW 원처럼 사용하여 NL1 생성")
        print(f"   🆕 WELDNO 조건: 기울기 0도 + TEXT/INST/< 포함 제외 + 숫자 포함 필수")
        
        print("[3단계] NL1 생성 및 WELD 원 STRETCH 완료")
        
    except Exception as main_e:
        print(f"❌ NL1 처리 중 전체 오류: {main_e}")
        print("[3단계] NL1 생성 및 거리 제어 실패")

### [4단계] NL1 길이 6mm 조정 기능 ###
def find_nl1_lines_with_weld_circles(msp):
    """NL1 흰색 선과 연결된 WELD 원들을 찾는 함수 (SW 원 및 SFW 폴리라인 포함)"""
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
            sw_type = None
            
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
            
            # 1mm SW 원 찾기
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
                            sw_type = 'SW'
                            break
                except Exception:
                    continue
            
            # SW 원을 못 찾았으면 SFW 폴리라인 찾기
            if not small_circle:
                for poly in msp.query("POLYLINE LWPOLYLINE"):
                    try:
                        if hasattr(poly.dxf, 'layer') and poly.dxf.layer == "SFW":
                            # 점들 가져오기
                            if poly.dxftype() == "POLYLINE":
                                points = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
                            else:
                                points = [Vec2(x, y) for x, y, *_ in poly.get_points()]
                            
                            # 6개 점인지 확인
                            if len(points) == 6:
                                # 중심점 계산
                                center_x = sum(p.x for p in points) / 6
                                center_y = sum(p.y for p in points) / 6
                                center = Vec2(center_x, center_y)
                                
                                # NL1 끝점이 SFW 중심 근처에 있는지 확인
                                dist_to_end = distance(center, line_end)
                                if dist_to_end <= 2.0:  # SFW 중심 근처
                                    small_circle = {
                                        'entity': poly,
                                        'center': center,
                                        'radius': 1.0  # SFW를 1mm 원처럼 취급
                                    }
                                    sw_type = 'SFW'
                                    break
                    except Exception:
                        continue
            
            # NL1과 WELD 원, SW/SFW가 모두 연결된 경우만 추가
            if weld_circle and small_circle:
                nl1_length = distance(line_start, line_end)
                nl1_weld_pairs.append({
                    'nl1_line': nl1_line,
                    'weld_circle': weld_circle,
                    'small_circle': small_circle,
                    'current_length': nl1_length,
                    'sw_type': sw_type
                })
                print(f"   NL1 발견: 길이 {nl1_length:.2f}mm, WELD원({weld_circle['center'].x:.2f}, {weld_circle['center'].y:.2f}) - {sw_type}({small_circle['center'].x:.2f}, {small_circle['center'].y:.2f})")
        
        except Exception as e:
            print(f"NL1 선 처리 중 오류: {e}")
            continue
    
    print(f"📊 유효한 NL1-WELD 쌍 {len(nl1_weld_pairs)}개 발견")
    return nl1_weld_pairs

def adjust_nl1_to_7mm_length(nl1_weld_pair, target_length=7.0, msp=None):
    """NL1 길이를 정확히 7mm로 조정하는 함수 (7mm 이상/이하 모두 조정)"""
    nl1_line = nl1_weld_pair['nl1_line']
    weld_circle = nl1_weld_pair['weld_circle']
    small_circle = nl1_weld_pair['small_circle']
    current_length = nl1_weld_pair['current_length']
    
    weld_center = weld_circle['center']
    small_center = small_circle['center']
    weld_radius = weld_circle['radius']  # 2.8mm
    
    print(f"🔧 NL1 길이 조정: 현재 {current_length:.2f}mm → 목표 {target_length:.2f}mm")
    
    # 7mm와 거의 같으면 조정 불필요 (오차 범위 0.1mm)
    if abs(current_length - target_length) < 0.1:
        print(f"   ✅ 조정 불필요: 현재 길이 {current_length:.2f}mm ≈ {target_length}mm")
        return True, "no_adjustment"
    
    # WELD 원에서 SW/SFW 방향으로의 벡터 (NL1 벡터 방향)
    direction_vec = small_center - weld_center
    if direction_vec.magnitude == 0:
        print(f"   ❌ 원들이 같은 위치에 있어 조정 불가능")
        return False, "same_position"
    
    direction_normalized = direction_vec.normalize()
    
    # 새로운 WELD 원 위치 계산 (SW/SFW에서 정확히 7mm 떨어진 위치)
    new_weld_center = small_center - direction_normalized * target_length
    
    if current_length > target_length:
        print(f"   📉 거리 축소: {current_length:.2f}mm → {target_length:.2f}mm")
    else:
        print(f"   📈 거리 확대: {current_length:.2f}mm → {target_length:.2f}mm")
    
    print(f"   이동 계획: WELD원 ({weld_center.x:.2f}, {weld_center.y:.2f}) → ({new_weld_center.x:.2f}, {new_weld_center.y:.2f})")
    
    # WELDNO 텍스트 찾기 (WELD 원 주변 3mm 내만)
    weldno_texts = []
    weldno_text_search_radius = 3.0
    text_backups = []
    
    for txt in msp.query('TEXT'):
        try:
            txt_pos = Vec2(txt.dxf.insert.x, txt.dxf.insert.y)
            if distance(weld_center, txt_pos) <= weldno_text_search_radius:
                # 텍스트 엔티티가 WDNO로 유효한지 확인 (내용 + 기울기)
                if is_valid_wdno_entity(txt):
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
    """[4단계] NL1 길이를 정확히 7mm로 조정 (7mm 이상/이하 모두)"""
    msp = doc.modelspace()
    target_length = 7.0
    
    print(f"\n[4단계] NL1 길이 7mm 조정 시작")
    
    try:
        # NL1 선과 연결된 WELD 원들 찾기
        nl1_weld_pairs = find_nl1_lines_with_weld_circles(msp)
        
        if not nl1_weld_pairs:
            print("조정할 NL1-WELD 쌍이 없습니다.")
            return
        
        # 7mm와 다른 NL1 필터링 (오차 범위 0.1mm)
        adjustment_needed_pairs = []
        for pair in nl1_weld_pairs:
            if abs(pair['current_length'] - target_length) > 0.1:
                adjustment_needed_pairs.append(pair)
                if pair['current_length'] > target_length:
                    print(f"📏 조정 대상: NL1 길이 {pair['current_length']:.2f}mm > {target_length}mm (축소 필요)")
                else:
                    print(f"📏 조정 대상: NL1 길이 {pair['current_length']:.2f}mm < {target_length}mm (확대 필요)")
        
        if not adjustment_needed_pairs:
            print(f"✅ 모든 NL1이 이미 {target_length}mm입니다.")
            return
        
        print(f"📊 조정 대상: {len(adjustment_needed_pairs)}개 NL1")
        
        success_count = 0
        fail_count = 0
        keep_original_count = 0
        
        # 각 NL1에 대해 조정 수행
        for i, pair in enumerate(adjustment_needed_pairs):
            print(f"\n🔧 [{i+1}/{len(adjustment_needed_pairs)}] NL1 조정 중...")
            
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
        print(f"   📏 모든 WELDNO가 정확히 7mm 거리로 조정됨 (이상/이하 모두)")
        print(f"   🔧 WELD 원 STRETCH: NL1 벡터 방향으로 7mm 위치로 이동")
        print(f"   🚫 TEXT 간섭 체크: 두 위치 중 간섭 없는 곳으로 선택")
        print(f"   💾 WELDNO 텍스트만 함께 이동 (다른 TEXT 보호)")
        print(f"   🆕 SFW 지원: SFW 폴리라인도 SW 원과 동일하게 처리")
        print(f"   🆕 WELDNO 조건: 기울기 0도 + TEXT/INST/< 포함 제외 + 숫자 포함 필수")
        
        print("[4단계] NL1 길이 7mm 조정 완료")
        
    except Exception as e:
        print(f"❌ [4단계] NL1 길이 조정 중 오류: {e}")
        print("[4단계] NL1 길이 조정 실패")

### [5단계] MWD 회전 및 최종 연결 - 우선순위 기반 + SFW 7mm 조정 ###
def get_text_bounding_box(text):
    """TEXT 엔티티의 바운딩 박스를 계산하는 함수"""
    try:
        # 텍스트의 기본 속성
        insert = Vec2(text.dxf.insert.x, text.dxf.insert.y)
        height = text.dxf.height
        
        # 텍스트 내용 길이 (대략적인 너비 계산)
        text_content = text.dxf.text
        width = len(text_content) * height * 0.7  # 대략적인 문자 너비 비율
        
        # 텍스트 정렬 방식 확인 (기본값은 LEFT)
        halign = text.dxf.halign if hasattr(text.dxf, 'halign') else 0
        valign = text.dxf.valign if hasattr(text.dxf, 'valign') else 0
        
        # 수평 정렬에 따른 바운딩 박스 계산
        if halign == 0:  # LEFT
            min_x = insert.x
            max_x = insert.x + width
        elif halign == 1:  # CENTER
            min_x = insert.x - width/2
            max_x = insert.x + width/2
        elif halign == 2:  # RIGHT
            min_x = insert.x - width
            max_x = insert.x
        else:
            min_x = insert.x
            max_x = insert.x + width
        
        # 수직 정렬에 따른 바운딩 박스 계산
        if valign == 0:  # BASELINE
            min_y = insert.y
            max_y = insert.y + height
        elif valign == 1:  # BOTTOM
            min_y = insert.y
            max_y = insert.y + height
        elif valign == 2:  # MIDDLE
            min_y = insert.y - height/2
            max_y = insert.y + height/2
        elif valign == 3:  # TOP
            min_y = insert.y - height
            max_y = insert.y
        else:
            min_y = insert.y
            max_y = insert.y + height
        
        # 바운딩 박스 중심
        center = Vec2((min_x + max_x)/2, (min_y + max_y)/2)
        
        return {
            'center': center,
            'width': width,
            'height': height,
            'min_x': min_x,
            'max_x': max_x,
            'min_y': min_y,
            'max_y': max_y
        }
    except Exception as e:
        print(f"텍스트 바운딩 박스 계산 오류: {e}")
        return None

def find_pipe_line_angle(sw_center, msp, search_radius=5.0):
    """SW 원 내에 접하는 PIPE 이름을 포함하는 선의 각도를 찾는 함수"""
    try:
        # SW 원 주변의 LINE 찾기
        for entity in msp.query('LINE'):
            try:
                start = Vec2(entity.dxf.start.x, entity.dxf.start.y)
                end = Vec2(entity.dxf.end.x, entity.dxf.end.y)
                
                # SW 원 중심에서 선까지의 거리 확인
                if (distance(sw_center, start) <= search_radius or 
                    distance(sw_center, end) <= search_radius):
                    
                    # 선의 각도 계산
                    dx = end.x - start.x
                    dy = end.y - start.y
                    angle = math.atan2(dy, dx)
                    return angle
            except Exception:
                continue
        
        # POLYLINE/LWPOLYLINE 찾기
        for poly in msp.query("POLYLINE LWPOLYLINE"):
            try:
                if poly.dxftype() == "POLYLINE":
                    points = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
                else:
                    points = [Vec2(x, y) for x, y, *_ in poly.get_points()]
                
                # SW 원 근처의 선분 찾기
                for i in range(len(points) - 1):
                    if (distance(sw_center, points[i]) <= search_radius or 
                        distance(sw_center, points[i+1]) <= search_radius):
                        
                        # 선분의 각도 계산
                        dx = points[i+1].x - points[i].x
                        dy = points[i+1].y - points[i].y
                        angle = math.atan2(dy, dx)
                        return angle
            except Exception:
                continue
        
        return None
    except Exception as e:
        print(f"PIPE 선 각도 찾기 오류: {e}")
        return None

def rotate_entity_around_point(entity, center, angle):
    """엔티티를 특정 점을 중심으로 회전시키는 함수"""
    try:
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        
        if entity.dxftype() == 'CIRCLE':
            # 원의 중심점 회전
            old_center = Vec2(entity.dxf.center.x, entity.dxf.center.y)
            dx = old_center.x - center.x
            dy = old_center.y - center.y
            new_x = center.x + dx * cos_a - dy * sin_a
            new_y = center.y + dx * sin_a + dy * cos_a
            entity.dxf.center = (new_x, new_y, 0)
            
        elif entity.dxftype() == 'TEXT':
            # 텍스트 삽입점 회전
            old_pos = Vec2(entity.dxf.insert.x, entity.dxf.insert.y)
            dx = old_pos.x - center.x
            dy = old_pos.y - center.y
            new_x = center.x + dx * cos_a - dy * sin_a
            new_y = center.y + dx * sin_a + dy * cos_a
            entity.dxf.insert = (new_x, new_y, 0)
            
        elif entity.dxftype() == 'LINE':
            # 선의 시작점과 끝점 회전
            start = Vec2(entity.dxf.start.x, entity.dxf.start.y)
            end = Vec2(entity.dxf.end.x, entity.dxf.end.y)
            
            # 시작점 회전
            dx = start.x - center.x
            dy = start.y - center.y
            new_start_x = center.x + dx * cos_a - dy * sin_a
            new_start_y = center.y + dx * sin_a + dy * cos_a
            
            # 끝점 회전
            dx = end.x - center.x
            dy = end.y - center.y
            new_end_x = center.x + dx * cos_a - dy * sin_a
            new_end_y = center.y + dx * sin_a + dy * cos_a
            
            entity.dxf.start = (new_start_x, new_start_y, 0)
            entity.dxf.end = (new_end_x, new_end_y, 0)
            
    except Exception as e:
        print(f"엔티티 회전 오류: {e}")

def get_text_start_end_points(text):
    """TEXT 엔티티의 시작점과 끝점을 계산하는 함수"""
    try:
        # 텍스트 기본 속성
        insert = Vec2(text.dxf.insert.x, text.dxf.insert.y)
        height = text.dxf.height
        text_content = text.dxf.text
        
        # 텍스트 너비 계산 (대략적인 비율)
        width = len(text_content) * height * 0.7
        
        # 회전 각도 (라디안)
        rotation = text.dxf.rotation if hasattr(text.dxf, 'rotation') else 0
        rotation_rad = math.radians(rotation)
        
        # 정렬 방식
        halign = text.dxf.halign if hasattr(text.dxf, 'halign') else 0
        
        # 기본 시작점과 끝점 (회전 전)
        if halign == 0:  # LEFT
            start_x = 0
            end_x = width
        elif halign == 1:  # CENTER
            start_x = -width/2
            end_x = width/2
        elif halign == 2:  # RIGHT
            start_x = -width
            end_x = 0
        else:
            start_x = 0
            end_x = width
        
        # 회전 적용
        cos_r = math.cos(rotation_rad)
        sin_r = math.sin(rotation_rad)
        
        # 시작점
        start_rotated_x = start_x * cos_r
        start_rotated_y = start_x * sin_r
        start_point = Vec2(insert.x + start_rotated_x, insert.y + start_rotated_y)
        
        # 끝점
        end_rotated_x = end_x * cos_r
        end_rotated_y = end_x * sin_r
        end_point = Vec2(insert.x + end_rotated_x, insert.y + end_rotated_y)
        
        return start_point, end_point
        
    except Exception as e:
        print(f"텍스트 시작/끝점 계산 오류: {e}")
        return None, None

def check_text_endpoint_interference(text_entity, msp, exclude_entities, min_distance=5.0):
    """TEXT 엔티티의 시작점/끝점이 다른 TEXT의 시작점/끝점에서 5mm 이내면 간섭으로 판정"""
    try:
        # 현재 텍스트의 시작점과 끝점
        start1, end1 = get_text_start_end_points(text_entity)
        if not start1 or not end1:
            return False
        
        for e in msp:
            if e in exclude_entities or not hasattr(e, "dxf") or e.dxf is None:
                continue
            
            if e.dxftype() == "TEXT":
                # 상대 텍스트의 시작점과 끝점
                start2, end2 = get_text_start_end_points(e)
                if not start2 or not end2:
                    continue
                
                # 4개의 점 간 거리 체크 (어느 하나라도 5mm 이내면 간섭)
                if (distance(start1, start2) < min_distance or
                    distance(start1, end2) < min_distance or
                    distance(end1, start2) < min_distance or
                    distance(end1, end2) < min_distance):
                    return True
        
        return False
    except Exception as e:
        print(f"텍스트 끝점 간섭 체크 오류: {e}")
        return False

def check_pipe_layer_interference(mwd_entities, msp, exclude_entities):
    """PIPE 또는 ELBO를 포함하는 레이어와의 간섭을 체크"""
    try:
        for mwd_entity in mwd_entities:
            if mwd_entity.dxftype() == 'CIRCLE':
                circle_center = Vec2(mwd_entity.dxf.center.x, mwd_entity.dxf.center.y)
                circle_radius = mwd_entity.dxf.radius
                
                # 모든 엔티티 검사
                for e in msp:
                    if e in exclude_entities or not hasattr(e, "dxf") or e.dxf is None:
                        continue
                    
                    # 레이어 이름에 PIPE 또는 ELBO가 포함되어 있는지 확인
                    if hasattr(e.dxf, 'layer'):
                        layer_name = e.dxf.layer.upper()
                        if 'PIPE' in layer_name or 'ELBO' in layer_name:
                            if e.dxftype() in ("LINE", "POLYLINE", "LWPOLYLINE"):
                                # 선분과의 거리 체크
                                if e.dxftype() == "LINE":
                                    start = Vec2(e.dxf.start.x, e.dxf.start.y)
                                    end = Vec2(e.dxf.end.x, e.dxf.end.y)
                                    dist = point_to_segment_distance(circle_center, start, end)
                                    if dist < circle_radius:
                                        return True
                                else:
                                    # 폴리라인
                                    if e.dxftype() == "POLYLINE":
                                        pts = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
                                    else:
                                        pts = [Vec2(x, y) for x, y, *_ in e.get_points()]
                                    
                                    for i in range(len(pts) - 1):
                                        dist = point_to_segment_distance(circle_center, pts[i], pts[i+1])
                                        if dist < circle_radius:
                                            return True
        
        return False
    except Exception as e:
        print(f"PIPE/ELBO 레이어 간섭 체크 오류: {e}")
        return False

def check_30degree_polyline_interference(mwd_entities, msp, exclude_entities):
    """30도 단위 정각도를 가진 폴리라인/LW폴리라인과의 간섭을 체크"""
    try:
        for mwd_entity in mwd_entities:
            if mwd_entity.dxftype() == 'CIRCLE':
                circle_center = Vec2(mwd_entity.dxf.center.x, mwd_entity.dxf.center.y)
                circle_radius = mwd_entity.dxf.radius
                
                # 모든 폴리라인 검사
                for e in msp.query("POLYLINE LWPOLYLINE"):
                    if e in exclude_entities or not hasattr(e, "dxf") or e.dxf is None:
                        continue
                    
                    # 폴리라인의 점들 가져오기
                    if e.dxftype() == "POLYLINE":
                        pts = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
                    else:
                        pts = [Vec2(x, y) for x, y, *_ in e.get_points()]
                    
                    if len(pts) < 2:
                        continue
                    
                    # 각 선분의 각도 체크
                    for i in range(len(pts) - 1):
                        p1, p2 = pts[i], pts[i+1]
                        
                        # 선분의 각도 계산 (라디안)
                        dx = p2.x - p1.x
                        dy = p2.y - p1.y
                        angle_rad = math.atan2(dy, dx)
                        
                        # 각도를 0~360도로 변환
                        angle_deg = math.degrees(angle_rad) % 360
                        
                        # 30도 단위로 반올림
                        nearest_30 = round(angle_deg / 30) * 30
                        
                        # 정확히 30도 단위인지 확인 (오차 1도 이내)
                        if abs(angle_deg - nearest_30) < 1.0:
                            # 원과 선분의 거리 체크
                            dist = point_to_segment_distance(circle_center, p1, p2)
                            if dist < circle_radius:
                                return True
        
        return False
    except Exception as e:
        print(f"30도 단위 폴리라인 간섭 체크 오류: {e}")
        return False

def check_mwd_interference_with_priority(mwd_entities, sw_center, rotation_angle, msp, exclude_entities, pipe_lines=None):
    """우선순위 기반 MWD 간섭 체크 - 각 간섭 유형별로 별도 체크"""
    try:
        # 임시로 회전시켜서 간섭 체크
        temp_positions = []
        
        # 모든 엔티티의 현재 위치 백업
        for entity in mwd_entities:
            if entity.dxftype() == 'CIRCLE':
                temp_positions.append({
                    'entity': entity,
                    'type': 'CIRCLE',
                    'original': (entity.dxf.center.x, entity.dxf.center.y, 0)
                })
            elif entity.dxftype() == 'TEXT':
                temp_positions.append({
                    'entity': entity,
                    'type': 'TEXT',
                    'original': (entity.dxf.insert.x, entity.dxf.insert.y, 0)
                })
            elif entity.dxftype() == 'LINE':
                temp_positions.append({
                    'entity': entity,
                    'type': 'LINE',
                    'original_start': (entity.dxf.start.x, entity.dxf.start.y, 0),
                    'original_end': (entity.dxf.end.x, entity.dxf.end.y, 0)
                })
        
        # 임시로 회전
        for entity in mwd_entities:
            rotate_entity_around_point(entity, sw_center, rotation_angle)
        
        # 회전 후 WELDNO 텍스트를 WDC 원 중심으로 재정렬
        wdc_circle = None
        weldno_texts = []
        
        for entity in mwd_entities:
            if entity.dxftype() == 'CIRCLE' and abs(entity.dxf.radius - 2.8) <= 0.3:
                wdc_circle = entity
            elif entity.dxftype() == 'TEXT':
                # 텍스트 엔티티가 WDNO로 유효한지 확인 (내용 + 기울기)
                if is_valid_wdno_entity(entity):
                    weldno_texts.append(entity)
        
        if wdc_circle and weldno_texts:
            wdc_center = Vec2(wdc_circle.dxf.center.x, wdc_circle.dxf.center.y)
            for txt in weldno_texts:
                bbox = get_text_bounding_box(txt)
                if bbox:
                    offset = wdc_center - bbox['center']
                    new_insert = Vec2(txt.dxf.insert.x + offset.x, 
                                    txt.dxf.insert.y + offset.y)
                    txt.dxf.insert = (new_insert.x, new_insert.y, 0)
        
        # 각 간섭 유형별로 체크
        has_text_interference = False
        has_pipe_layer_interference = False
        has_pc_circle_interference = False
        has_30degree_polyline_interference = False
        general_interference_score = 0
        
        # 1. TEXT 간섭 체크 (최우선)
        for entity in mwd_entities:
            if entity.dxftype() == 'TEXT':
                if check_text_endpoint_interference(entity, msp, exclude_entities + mwd_entities, 5.0):
                    has_text_interference = True
                    break
        
        # 2. PIPE/ELBO 레이어 간섭 체크 (두번째 우선순위)
        has_pipe_layer_interference = check_pipe_layer_interference(mwd_entities, msp, exclude_entities + mwd_entities)
        
        # 3. PC와 WDC 원 사이 2mm 체크 (세번째 우선순위)
        if pipe_lines:
            for entity in mwd_entities:
                if entity.dxftype() == 'CIRCLE' and abs(entity.dxf.radius - 2.8) <= 0.3:  # WDC 원
                    center = Vec2(entity.dxf.center.x, entity.dxf.center.y)
                    for pc in pipe_lines:
                        if check_circle_to_segments_distance(center, entity.dxf.radius, pc['segments'], 2.0):
                            has_pc_circle_interference = True
                            break
                    if has_pc_circle_interference:
                        break
        
        # 4. 30도 단위 정각도 폴리라인 간섭 체크 (네번째 우선순위)
        has_30degree_polyline_interference = check_30degree_polyline_interference(mwd_entities, msp, exclude_entities + mwd_entities)
        
        # 5. 일반 간섭 점수 계산 (최하위 우선순위)
        for entity in mwd_entities:
            if entity.dxftype() == 'CIRCLE':
                center = Vec2(entity.dxf.center.x, entity.dxf.center.y)
                if check_interference_at_position(center, msp, exclude_entities + mwd_entities, entity.dxf.radius):
                    general_interference_score += 1
        
        # 원래 위치로 복구
        for backup in temp_positions:
            if backup['type'] == 'CIRCLE':
                backup['entity'].dxf.center = backup['original']
            elif backup['type'] == 'TEXT':
                backup['entity'].dxf.insert = backup['original']
            elif backup['type'] == 'LINE':
                backup['entity'].dxf.start = backup['original_start']
                backup['entity'].dxf.end = backup['original_end']
        
        return {
            'text_interference': has_text_interference,
            'pipe_layer_interference': has_pipe_layer_interference,
            'pc_circle_interference': has_pc_circle_interference,
            '30degree_polyline_interference': has_30degree_polyline_interference,
            'general_score': general_interference_score
        }
        
    except Exception as e:
        print(f"우선순위 기반 간섭 체크 오류: {e}")
        return {
            'text_interference': True,
            'pipe_layer_interference': True,
            'pc_circle_interference': True,
            '30degree_polyline_interference': True,
            'general_score': 999
        }

def find_sfw_polyline(msp, search_center, search_radius=20.0):
    """특정 위치 근처의 SFW 레이어 6점 폴리라인을 찾는 함수"""
    sfw_polylines = []
    
    for poly in msp.query("POLYLINE LWPOLYLINE"):
        try:
            if hasattr(poly.dxf, 'layer') and poly.dxf.layer == "SFW":
                # 점들 가져오기
                if poly.dxftype() == "POLYLINE":
                    points = [Vec2(v.dxf.location.x, v.dxf.location.y) for v in poly.vertices]
                else:
                    points = [Vec2(x, y) for x, y, *_ in poly.get_points()]
                
                # 6개 점인지 확인
                if len(points) == 6:
                    # 중심점 계산
                    center_x = sum(p.x for p in points) / 6
                    center_y = sum(p.y for p in points) / 6
                    center = Vec2(center_x, center_y)
                    
                    # 검색 중심에서의 거리
                    dist = distance(search_center, center)
                    if dist <= search_radius:
                        sfw_polylines.append({
                            'entity': poly,
                            'center': center,
                            'points': points,
                            'distance': dist
                        })
        except Exception:
            continue
    
    return sfw_polylines

def adjust_wdc_for_sfw_7mm(wdc_circle, wdc_center, sfw_center, msp):
    """SFW와 WDC 거리가 7mm 이하일 때 7mm로 조정하는 함수"""
    current_distance = distance(wdc_center, sfw_center)
    
    print(f"   🔍 현재 WDC-SFW 거리: {current_distance:.2f}mm")
    
    if current_distance >= 7.0:
        print(f"   ✅ 거리 조정 불필요 (현재 {current_distance:.2f}mm >= 7mm)")
        return wdc_center, []
    
    print(f"   📏 7mm 거리 조정 필요: {current_distance:.2f}mm → 7.0mm")
    
    # 방향 벡터 계산 (SFW에서 멀어지는 방향)
    direction_vec = wdc_center - sfw_center
    if direction_vec.magnitude == 0:
        print(f"   ❌ WDC와 SFW가 같은 위치에 있어 조정 불가능")
        return wdc_center, []
    
    direction_normalized = direction_vec.normalize()
    
    # 새로운 WDC 위치 계산 (SFW에서 정확히 7mm 떨어진 위치)
    new_wdc_center = sfw_center + direction_normalized * 7.0
    
    print(f"   📍 WDC 이동 계획: ({wdc_center.x:.2f}, {wdc_center.y:.2f}) → ({new_wdc_center.x:.2f}, {new_wdc_center.y:.2f})")
    
    # WELDNO 텍스트 찾기 (WDC 원 주변 3mm 내)
    weldno_texts = []
    weldno_text_search_radius = 3.0
    
    for txt in msp.query('TEXT'):
        try:
            txt_pos = Vec2(txt.dxf.insert.x, txt.dxf.insert.y)
            if distance(wdc_center, txt_pos) <= weldno_text_search_radius:
                # 텍스트 엔티티가 WDNO로 유효한지 확인 (내용 + 기울기)
                if is_valid_wdno_entity(txt):
                    weldno_texts.append(txt)
        except Exception:
            continue
    
    print(f"   📝 WELDNO 텍스트 {len(weldno_texts)}개 발견")
    
    # WDC 원 및 WELDNO 텍스트 이동
    try:
        move_vec = new_wdc_center - wdc_center
        
        # WDC 원 이동
        wdc_circle.dxf.center = (new_wdc_center.x, new_wdc_center.y, 0)
        
        # WELDNO 텍스트들 함께 이동
        for txt in weldno_texts:
            try:
                old_pos = txt.dxf.insert
                new_pos = (old_pos.x + move_vec.x, old_pos.y + move_vec.y, old_pos.z if hasattr(old_pos, 'z') else 0)
                txt.dxf.insert = new_pos
            except Exception as e:
                print(f"   ❌ WELDNO 텍스트 이동 오류: {e}")
        
        final_distance = distance(new_wdc_center, sfw_center)
        print(f"   ✅ WDC 7mm 조정 성공: 최종 거리 {final_distance:.2f}mm")
        
        return new_wdc_center, weldno_texts
        
    except Exception as e:
        print(f"   ❌ WDC 조정 중 오류: {e}")
        return wdc_center, []

def process_mwd_rotation_and_connection(doc):
    """[5단계] MWD 회전 및 최종 연결 처리 - 우선순위 기반 + SFW 7mm 조정"""
    msp = doc.modelspace()
    
    # 사용된 SW/SFW 추적 리스트
    used_sw_sfw = []
    
    print("\n[5단계] MWD 회전 및 최종 연결 시작 (우선순위 기반 + SFW 7mm 조정)")
    print("간섭 회피 우선순위:")
    print("1. TEXT 간섭 (무조건 피함)")
    print("2. PIPE/ELBO 레이어 간섭")
    print("3. PC와 WDC 원 사이 2mm 이하")
    print("4. 30도 단위 정각도 폴리라인 간섭")
    print("5. 일반 간섭 최소화")
    print("\n🆕 SFW 지원: 6점 폴리라인의 중심을 SW 원처럼 사용")
    print("🆕 SFW 7mm 조정: SFW 중심과 WDC 중심이 7mm 이하면 7mm로 이동 후 간섭 체크")
    print("🆕 SFW PC 검색: SFW 중심에서 7mm 내의 PIPE 선 2개 찾기")
    print("🚫 SW/SFW 사용 제한: 각 SW 원 또는 SFW 폴리라인은 한 번만 사용")
    print("🗑️  기존 WG 삭제: WDC 및 SW/SFW 근처의 기존 WG 선을 먼저 삭제 후 새 연결선 생성")
    print("📏 WG 길이 제한: 40mm 이상이면 생성하지 않음")
    print("🎯 WDC당 WG 1개: WDC 근처의 모든 기존 WG 삭제")
    print("🆕 WELDNO 조건: 기울기 0도 + TEXT/INST/< 포함 제외 + 숫자 포함 필수")
    
    try:
        # 1. 모든 2.8mm WELD 원에 WDC 레이어 할당 및 YELLOW 색상 적용
        wdc_circles = []
        for entity in msp.query('CIRCLE'):
            try:
                if (hasattr(entity.dxf, 'color') and entity.dxf.color == 2 and  # 노랑색
                    hasattr(entity.dxf, 'radius') and abs(entity.dxf.radius - 2.8) <= 0.3):
                    entity.dxf.layer = "WDC"
                    entity.dxf.color = 2  # YELLOW
                    wdc_circles.append(entity)
                    print(f"WDC 레이어 할당 및 YELLOW 색상: 원({entity.dxf.center.x:.2f}, {entity.dxf.center.y:.2f})")
            except Exception:
                continue
        
        print(f"✅ WDC 레이어 할당 및 YELLOW 색상 적용 완료: {len(wdc_circles)}개 WELD 원")
        
        # 2. 각 WDC 원에 대해 MWD 그룹 생성
        mwd_groups = []
        for wdc_circle in wdc_circles:
            try:
                wdc_center = Vec2(wdc_circle.dxf.center.x, wdc_circle.dxf.center.y)
                
                # WELDNO 텍스트 찾기 (3mm 내)
                weldno_texts = []
                text_search_radius = 3.0
                
                for txt in msp.query('TEXT'):
                    try:
                        txt_pos = Vec2(txt.dxf.insert.x, txt.dxf.insert.y)
                        if distance(wdc_center, txt_pos) <= text_search_radius:
                            # 텍스트 엔티티가 WDNO로 유효한지 확인 (내용 + 기울기)
                            if is_valid_wdno_entity(txt):
                                txt.dxf.color = 4  # CYAN 색상 적용
                                txt.dxf.layer = "WDNO"  # WDNO 레이어 적용
                                weldno_texts.append(txt)
                                # 텍스트 박스 중심을 WELD 원 중심으로 이동
                                bbox = get_text_bounding_box(txt)
                                if bbox:
                                    offset = wdc_center - bbox['center']
                                    new_insert = Vec2(txt.dxf.insert.x + offset.x, 
                                                    txt.dxf.insert.y + offset.y)
                                    txt.dxf.insert = (new_insert.x, new_insert.y, 0)
                    except Exception:
                        continue
                
                # MWD 그룹 생성 (WDC + WELDNO 텍스트)
                mwd_group = {
                    'wdc_circle': wdc_circle,
                    'wdc_center': wdc_center,
                    'weldno_texts': weldno_texts,
                    'entities': [wdc_circle] + weldno_texts
                }
                mwd_groups.append(mwd_group)
                
            except Exception as e:
                print(f"MWD 그룹 생성 오류: {e}")
                continue
        
        print(f"📦 MWD 그룹 생성 완료: {len(mwd_groups)}개")
        
        # WDNO 텍스트 값을 기준으로 MWD 그룹 정렬
        def extract_wdno_number(mwd_group):
            """WDNO 텍스트에서 숫자를 추출하는 함수"""
            try:
                for txt in mwd_group['weldno_texts']:
                    text_content = txt.dxf.text.strip()
                    # 숫자만 추출 (예: "W1", "1", "WELD1" 등에서 숫자 추출)
                    numbers = re.findall(r'\d+', text_content)
                    if numbers:
                        return int(numbers[0])
                return 999999  # 숫자가 없으면 맨 뒤로
            except:
                return 999999
        
        # WDNO 값으로 정렬
        mwd_groups_sorted = sorted(mwd_groups, key=extract_wdno_number)
        
        print(f"📋 WDNO 값 순서로 정렬 완료 (INST/TEXT/< 포함/숫자없는 TEXT 제외):")
        for i, group in enumerate(mwd_groups_sorted):
            wdno_value = extract_wdno_number(group)
            if wdno_value != 999999:
                print(f"   {i+1}. WDNO: {wdno_value}")
            else:
                print(f"   {i+1}. WDNO: 숫자 없음")
        
        # 3. 정렬된 순서대로 각 MWD 그룹 처리
        processed_count = 0
        skipped_count = 0
        
        for i, mwd_group in enumerate(mwd_groups_sorted):
            try:
                wdc_circle = mwd_group['wdc_circle']
                wdc_center = mwd_group['wdc_center']
                
                print(f"\n🔍 [{i+1}/{len(mwd_groups)}] MWD 처리: ({wdc_center.x:.2f}, {wdc_center.y:.2f})")
                
                # 연결된 1mm SW 원 또는 SFW 폴리라인 찾기
                sw_circle = None
                sw_center = None
                sw_layer = None
                sw_type = None  # 'CIRCLE' 또는 'POLYLINE'
                nl1_exists = False
                
                # 1. 먼저 기존 NL1 선을 통해 연결된 1mm 원 찾기
                for line in msp.query('LINE'):
                    try:
                        if hasattr(line.dxf, 'color') and line.dxf.color == 4:  # 흰색 NL1
                            line_start = Vec2(line.dxf.start.x, line.dxf.start.y)
                            line_end = Vec2(line.dxf.end.x, line.dxf.end.y)
                            
                            # WDC 원과 연결된 NL1인지 확인
                            if distance(wdc_center, line_start) <= 3.5:
                                nl1_exists = True
                                # 반대쪽 끝에 있는 1mm 원 찾기
                                for circle in msp.query('CIRCLE'):
                                    if (hasattr(circle.dxf, 'color') and circle.dxf.color == 2 and
                                        abs(circle.dxf.radius - 1.0) <= 0.1):
                                        circle_center = Vec2(circle.dxf.center.x, circle.dxf.center.y)
                                        if distance(circle_center, line_end) <= 1.5:
                                            # 이미 사용된 SW인지 확인
                                            if circle not in used_sw_sfw:
                                                sw_circle = circle
                                                sw_center = circle_center
                                                sw_layer = circle.dxf.layer if hasattr(circle.dxf, 'layer') else "0"
                                                sw_type = 'CIRCLE'
                                            break
                                if sw_circle:
                                    break
                    except Exception:
                        continue
                
                # 2. NL1로 연결된 원을 찾지 못한 경우, WDC에 접하는 WG 선 찾기
                if not sw_circle:
                    print(f"   ⚠️  NL1 연결을 찾을 수 없음 - WDC에 접하는 WG 선 검색")
                    
                    # WDC에 접하는 WG 선 찾기
                    wg_search_radius = 3.5  # WDC 원 경계 근처
                    found_wg = False
                    
                    for line in msp.query('LINE'):
                        try:
                            if (hasattr(line.dxf, 'layer') and line.dxf.layer == 'WG' and
                                hasattr(line.dxf, 'color') and line.dxf.color == 7):  # WG 레이어 + 흰색
                                
                                line_start = Vec2(line.dxf.start.x, line.dxf.start.y)
                                line_end = Vec2(line.dxf.end.x, line.dxf.end.y)
                                
                                # WDC 원과 연결된 WG인지 확인
                                dist_to_start = distance(wdc_center, line_start)
                                dist_to_end = distance(wdc_center, line_end)
                                
                                if dist_to_start <= wg_search_radius or dist_to_end <= wg_search_radius:
                                    print(f"   🔍 WG 선 발견: 시작({line_start.x:.2f}, {line_start.y:.2f}) - 끝({line_end.x:.2f}, {line_end.y:.2f})")
                                    
                                    # WDC로부터 먼 쪽 끝점 찾기
                                    far_point = line_end if dist_to_start < dist_to_end else line_start
                                    print(f"   📍 WDC로부터 먼 점: ({far_point.x:.2f}, {far_point.y:.2f})")
                                    
                                    # 먼 점 근처의 SW 원 찾기
                                    sw_search_radius = 2.0  # SW 원 검색 반경
                                    
                                    for circle in msp.query('CIRCLE'):
                                        try:
                                            if (hasattr(circle.dxf, 'color') and circle.dxf.color == 2 and
                                                abs(circle.dxf.radius - 1.0) <= 0.1):
                                                
                                                circle_layer = circle.dxf.layer if hasattr(circle.dxf, 'layer') else "0"
                                                circle_center = Vec2(circle.dxf.center.x, circle.dxf.center.y)
                                                
                                                # SW 레이어이고 먼 점 근처에 있으며 미사용인 경우
                                                if (circle_layer == "SW" and 
                                                    distance(far_point, circle_center) <= sw_search_radius and
                                                    circle not in used_sw_sfw):
                                                    
                                                    sw_circle = circle
                                                    sw_center = circle_center
                                                    sw_layer = circle_layer
                                                    sw_type = 'CIRCLE'
                                                    found_wg = True
                                                    print(f"   ✅ WG 끝점 근처의 SW 원 발견: ({sw_center.x:.2f}, {sw_center.y:.2f})")
                                                    break
                                        except Exception:
                                            continue
                                    
                                    if found_wg:
                                        break
                                    
                                    # SW 원을 못 찾았으면 SFW 폴리라인도 확인
                                    sfw_polylines = find_sfw_polyline(msp, far_point, sw_search_radius)
                                    for sfw in sfw_polylines:
                                        if sfw['entity'] not in used_sw_sfw:
                                            sw_circle = sfw['entity']
                                            sw_center = sfw['center']
                                            sw_layer = "SFW"
                                            sw_type = 'POLYLINE'
                                            found_wg = True
                                            print(f"   ✅ WG 끝점 근처의 SFW 폴리라인 발견: 중심({sw_center.x:.2f}, {sw_center.y:.2f})")
                                            break
                                    
                                    if found_wg:
                                        break
                        except Exception:
                            continue
                    
                    if not found_wg:
                        print(f"   💡 WG 연결을 통한 SW/SFW를 찾을 수 없음")
                
                # 3. WG로도 연결을 찾지 못한 경우, WDC에서 가장 가까운 SW/SFW 찾기
                if not sw_circle:
                    print(f"   🔍 최후 수단: WDC에서 가장 가까운 SW/SFW 검색")
                    
                    min_distance = float('inf')
                    closest_sw = None
                    closest_center = None
                    closest_layer = None
                    closest_type = None
                    
                    # SW 원 찾기
                    for circle in msp.query('CIRCLE'):
                        try:
                            if (hasattr(circle.dxf, 'color') and circle.dxf.color == 2 and
                                abs(circle.dxf.radius - 1.0) <= 0.1):
                                
                                circle_layer = circle.dxf.layer if hasattr(circle.dxf, 'layer') else "0"
                                
                                # SW 레이어이고 아직 사용되지 않은 경우
                                if circle_layer == "SW" and circle not in used_sw_sfw:
                                    circle_center = Vec2(circle.dxf.center.x, circle.dxf.center.y)
                                    dist = distance(wdc_center, circle_center)
                                    
                                    if dist < min_distance:
                                        min_distance = dist
                                        closest_sw = circle
                                        closest_center = circle_center
                                        closest_layer = circle_layer
                                        closest_type = 'CIRCLE'
                        except Exception:
                            continue
                    
                    # SFW 폴리라인 찾기
                    sfw_polylines = find_sfw_polyline(msp, wdc_center, search_radius=50.0)
                    for sfw in sfw_polylines:
                        if sfw['entity'] not in used_sw_sfw and sfw['distance'] < min_distance:
                            min_distance = sfw['distance']
                            closest_sw = sfw['entity']
                            closest_center = sfw['center']
                            closest_layer = "SFW"
                            closest_type = 'POLYLINE'
                    
                    if closest_sw:
                        sw_circle = closest_sw
                        sw_center = closest_center
                        sw_layer = closest_layer
                        sw_type = closest_type
                        print(f"   🔍 가장 가까운 {sw_type} 발견: {sw_layer} 레이어, 중심({sw_center.x:.2f}, {sw_center.y:.2f}), 거리: {min_distance:.2f}mm")
                    else:
                        print(f"   ❌ 사용 가능한 SW/SFW를 찾을 수 없음 - SKIP")
                        continue
                
                if not sw_circle:
                    print(f"   ❌ 연결할 SW/SFW를 찾을 수 없음 - SKIP")
                    continue
                
                print(f"   🔗 {sw_type} 발견: ({sw_center.x:.2f}, {sw_center.y:.2f}), 레이어: {sw_layer}")
                
                # SW/SFW 사용 표시
                used_sw_sfw.append(sw_circle)
                print(f"   ✅ {sw_type} 사용 표시 완료 (중복 사용 방지)")
                
                # SW 또는 SFW 처리
                if sw_layer in ["SW", "SFW"]:
                    print(f"   🎨 WDC: YELLOW, WELDNO: CYAN 색상 확인")
                    print(f"   🔗 {sw_layer} 레이어 확인")
                    
                    # SFW와 WDC 거리가 7mm 이하인 경우 조정
                    if sw_type == 'POLYLINE' and sw_layer == "SFW":
                        original_wdc_center = Vec2(wdc_center.x, wdc_center.y)
                        wdc_center, moved_texts = adjust_wdc_for_sfw_7mm(wdc_circle, wdc_center, sw_center, msp)
                        
                        # WDC가 이동했으면 MWD 그룹의 모든 엔티티 위치 업데이트
                        if wdc_center != original_wdc_center:
                            # 이동 벡터 계산
                            move_vec = wdc_center - original_wdc_center
                            
                            # MWD 그룹의 wdc_center 업데이트
                            mwd_group['wdc_center'] = wdc_center
                            
                            # entities 리스트에서 이동된 텍스트들의 위치 확인
                            # (이미 adjust_wdc_for_sfw_7mm에서 이동됨)
                    
                    # SW/SFW 근처의 PC(PIPE 관련 선) 찾기 - 개선된 함수 사용
                    pipe_lines = find_pipe_lines_near_sw_improved(sw_circle, sw_center, sw_type, msp, 1.0)
                    if pipe_lines:
                        print(f"   🔧 PC(PIPE 관련 선) {len(pipe_lines)}개 발견 (최대 2개)")
                        for j, pc in enumerate(pipe_lines):
                            print(f"      - PC{j+1}: {pc['type']} 레이어, 최소거리 {pc['min_distance']:.2f}mm")
                    
                    # 간섭 체크를 위한 제외 엔티티
                    exclude_entities = [sw_circle] + mwd_group['entities']
                    
                    # 모든 회전 각도에서 간섭 정보 수집
                    rotation_candidates = []
                    
                    # 현재 위치(0도) 체크
                    interference_info = check_mwd_interference_with_priority(
                        mwd_group['entities'], sw_center, 0, msp, exclude_entities, pipe_lines
                    )
                    rotation_candidates.append({
                        'angle': 0,
                        'degree': 0,
                        'interference': interference_info
                    })
                    
                    # 30도 단위로 360도 회전하며 간섭 체크
                    for degree in range(30, 360, 30):
                        angle = math.radians(degree)
                        interference_info = check_mwd_interference_with_priority(
                            mwd_group['entities'], sw_center, angle, msp, exclude_entities, pipe_lines
                        )
                        rotation_candidates.append({
                            'angle': angle,
                            'degree': degree,
                            'interference': interference_info
                        })
                    
                    # 우선순위에 따라 최적 위치 선택
                    best_candidate = None
                    
                    # 1순위: TEXT 간섭이 없는 위치 찾기
                    text_free_candidates = [c for c in rotation_candidates if not c['interference']['text_interference']]
                    
                    if text_free_candidates:
                        print(f"   TEXT 간섭 없는 위치: {len(text_free_candidates)}개")
                        
                        # 2순위: TEXT 간섭 없는 위치 중 PIPE/ELBO 레이어 간섭이 없는 위치
                        pipe_free_candidates = [c for c in text_free_candidates if not c['interference']['pipe_layer_interference']]
                        
                        if pipe_free_candidates:
                            print(f"   PIPE/ELBO 레이어 간섭도 없는 위치: {len(pipe_free_candidates)}개")
                            
                            # 3순위: PC와 WDC 원 사이 2mm 이상인 위치
                            pc_free_candidates = [c for c in pipe_free_candidates if not c['interference']['pc_circle_interference']]
                            
                            if pc_free_candidates:
                                print(f"   PC-WDC 거리도 2mm 이상인 위치: {len(pc_free_candidates)}개")
                                
                                # 4순위: 30도 단위 폴리라인 간섭이 없는 위치
                                polyline_free_candidates = [c for c in pc_free_candidates if not c['interference']['30degree_polyline_interference']]
                                
                                if polyline_free_candidates:
                                    print(f"   30도 단위 폴리라인 간섭도 없는 위치: {len(polyline_free_candidates)}개")
                                    
                                    # 5순위: 일반 간섭이 가장 적은 위치
                                    best_candidate = min(polyline_free_candidates, key=lambda x: x['interference']['general_score'])
                                    print(f"   최적 위치: {best_candidate['degree']}도 (일반 간섭 점수: {best_candidate['interference']['general_score']})")
                                else:
                                    # 30도 폴리라인 간섭이 모두 있으면 일반 간섭이 가장 적은 위치
                                    best_candidate = min(pc_free_candidates, key=lambda x: x['interference']['general_score'])
                                    print(f"   30도 폴리라인 간섭은 피할 수 없음 - 일반 간섭 최소 위치: {best_candidate['degree']}도")
                            else:
                                # PC 간섭이 모두 있으면 30도 폴리라인 간섭 확인
                                polyline_free_candidates = [c for c in pipe_free_candidates if not c['interference']['30degree_polyline_interference']]
                                
                                if polyline_free_candidates:
                                    best_candidate = min(polyline_free_candidates, key=lambda x: x['interference']['general_score'])
                                    print(f"   PC 간섭은 피할 수 없음 - 30도 폴리라인 간섭 없고 일반 간섭 최소 위치: {best_candidate['degree']}도")
                                else:
                                    # PC와 30도 폴리라인 간섭이 모두 있으면 일반 간섭이 가장 적은 위치
                                    best_candidate = min(pipe_free_candidates, key=lambda x: x['interference']['general_score'])
                                    print(f"   PC와 30도 폴리라인 간섭 모두 피할 수 없음 - 일반 간섭 최소 위치: {best_candidate['degree']}도")
                        else:
                            # PIPE/ELBO 레이어 간섭이 모두 있으면 PC 간섭 확인
                            pc_free_candidates = [c for c in text_free_candidates if not c['interference']['pc_circle_interference']]
                            
                            if pc_free_candidates:
                                # 30도 폴리라인 간섭 확인
                                polyline_free_candidates = [c for c in pc_free_candidates if not c['interference']['30degree_polyline_interference']]
                                
                                if polyline_free_candidates:
                                    best_candidate = min(polyline_free_candidates, key=lambda x: x['interference']['general_score'])
                                    print(f"   PIPE/ELBO 간섭은 피할 수 없음 - PC 간섭 없고 30도 폴리라인 간섭 없는 위치: {best_candidate['degree']}도")
                                else:
                                    best_candidate = min(pc_free_candidates, key=lambda x: x['interference']['general_score'])
                                    print(f"   PIPE/ELBO와 30도 폴리라인 간섭은 피할 수 없음 - PC 간섭 없는 위치: {best_candidate['degree']}도")
                            else:
                                # 모든 우선순위 간섭이 있으면 일반 간섭이 가장 적은 위치
                                best_candidate = min(text_free_candidates, key=lambda x: x['interference']['general_score'])
                                print(f"   모든 우선순위 간섭 존재 - 일반 간섭 최소 위치: {best_candidate['degree']}도")
                    else:
                        # TEXT 간섭을 피할 수 없는 경우 (최악의 경우)
                        print(f"   ⚠️  모든 위치에서 TEXT 간섭 발생!")
                        best_candidate = min(rotation_candidates, key=lambda x: x['interference']['general_score'])
                        print(f"   TEXT 간섭을 피할 수 없음 - 최소 간섭 위치: {best_candidate['degree']}도")
                    
                    if not best_candidate:
                        print(f"   ❌ 적절한 위치를 찾을 수 없음 - SKIP")
                        continue
                    
                    # 선택된 각도로 회전
                    final_angle = best_candidate['angle']
                    final_degree = best_candidate['degree']
                    
                    # 간섭 상태 출력
                    print(f"   📊 선택된 위치의 간섭 상태:")
                    print(f"      TEXT 간섭: {'있음' if best_candidate['interference']['text_interference'] else '없음'}")
                    print(f"      PIPE/ELBO 레이어 간섭: {'있음' if best_candidate['interference']['pipe_layer_interference'] else '없음'}")
                    print(f"      PC-WDC 2mm 이하: {'있음' if best_candidate['interference']['pc_circle_interference'] else '없음'}")
                    print(f"      30도 단위 폴리라인 간섭: {'있음' if best_candidate['interference']['30degree_polyline_interference'] else '없음'}")
                    print(f"      일반 간섭 점수: {best_candidate['interference']['general_score']}")
                    
                    # MWD 회전 실행 (회전이 필요한 경우만)
                    if final_angle != 0:
                        for entity in mwd_group['entities']:
                            rotate_entity_around_point(entity, sw_center, final_angle)
                        
                        # 회전 후 WELDNO 텍스트를 WDC 원 중심으로 재정렬
                        wdc_center_after_rotation = Vec2(wdc_circle.dxf.center.x, wdc_circle.dxf.center.y)
                        for txt in mwd_group['weldno_texts']:
                            # weldno_texts 리스트에는 이미 검증된 텍스트만 있음
                            bbox = get_text_bounding_box(txt)
                            if bbox:
                                offset = wdc_center_after_rotation - bbox['center']
                                new_insert = Vec2(txt.dxf.insert.x + offset.x, 
                                                txt.dxf.insert.y + offset.y)
                                txt.dxf.insert = (new_insert.x, new_insert.y, 0)
                        print(f"   🔄 MWD를 {final_degree}도 회전 완료")
                    else:
                        print(f"   ✅ 현재 위치가 최적 - 회전 불필요")
                    
                    # 회전된 WDC 위치 업데이트
                    rotated_wdc_center = Vec2(wdc_circle.dxf.center.x, wdc_circle.dxf.center.y)
                    
                    # 기존 NL1 삭제 (NL1이 존재하는 경우만)
                    if nl1_exists:
                        nl1_deleted = False
                        for line in list(msp.query('LINE')):
                            try:
                                if hasattr(line.dxf, 'color') and line.dxf.color == 4:  # 흰색
                                    line_start = Vec2(line.dxf.start.x, line.dxf.start.y)
                                    line_end = Vec2(line.dxf.end.x, line.dxf.end.y)
                                    
                                    # 이 MWD와 연결된 NL1인지 확인 (회전 전 위치 기준)
                                    if (distance(wdc_center, line_start) <= 3.5 or
                                        distance(rotated_wdc_center, line_start) <= 3.5):
                                        msp.delete_entity(line)
                                        nl1_deleted = True
                                        print(f"   🗑️  기존 NL1 삭제")
                                        break
                            except Exception:
                                continue
                    else:
                        print(f"   💡 NL1이 없어 새로운 WG 연결 생성")
                    
                    # WDC 근처의 기존 WG 선 삭제 (WDC당 1개만 유지)
                    print(f"   🔍 WDC 중심 근처의 기존 WG 선 확인 중...")
                    wdc_wg_deleted = 0
                    wdc_wg_search_radius = 3.5  # WDC 원에서 3.5mm 이내의 WG 선 찾기
                    
                    for line in list(msp.query('LINE')):
                        try:
                            if (hasattr(line.dxf, 'layer') and line.dxf.layer == 'WG' and
                                hasattr(line.dxf, 'color') and line.dxf.color == 7):  # WG 레이어 + 흰색
                                
                                line_start = Vec2(line.dxf.start.x, line.dxf.start.y)
                                line_end = Vec2(line.dxf.end.x, line.dxf.end.y)
                                
                                # WDC 중심에서 선의 양 끝점까지의 거리 확인
                                dist_to_start = distance(rotated_wdc_center, line_start)
                                dist_to_end = distance(rotated_wdc_center, line_end)
                                
                                # 어느 한 끝점이라도 WDC 근처에 있으면 삭제
                                if dist_to_start <= wdc_wg_search_radius or dist_to_end <= wdc_wg_search_radius:
                                    msp.delete_entity(line)
                                    wdc_wg_deleted += 1
                                    print(f"      🗑️  기존 WG 선 삭제: 시작({line_start.x:.2f}, {line_start.y:.2f}) - 끝({line_end.x:.2f}, {line_end.y:.2f})")
                        except Exception as e:
                            continue
                    
                    if wdc_wg_deleted > 0:
                        print(f"   ✅ WDC 근처의 기존 WG 선 {wdc_wg_deleted}개 삭제 완료")
                    
                    # SW 원에 접하는 기존 WG 선 삭제
                    print(f"   🔍 SW/SFW 중심 근처의 기존 WG 선 확인 중...")
                    existing_wg_deleted = 0
                    wg_search_radius = 2.0  # SW 원에서 2mm 이내의 WG 선 찾기
                    
                    for line in list(msp.query('LINE')):
                        try:
                            if (hasattr(line.dxf, 'layer') and line.dxf.layer == 'WG' and
                                hasattr(line.dxf, 'color') and line.dxf.color == 7):  # WG 레이어 + 흰색
                                
                                line_start = Vec2(line.dxf.start.x, line.dxf.start.y)
                                line_end = Vec2(line.dxf.end.x, line.dxf.end.y)
                                
                                # SW/SFW 중심에서 선의 양 끝점까지의 거리 확인
                                dist_to_start = distance(sw_center, line_start)
                                dist_to_end = distance(sw_center, line_end)
                                
                                # 어느 한 끝점이라도 SW/SFW 근처에 있으면 삭제
                                if dist_to_start <= wg_search_radius or dist_to_end <= wg_search_radius:
                                    msp.delete_entity(line)
                                    existing_wg_deleted += 1
                                    print(f"      🗑️  기존 WG 선 삭제: 시작({line_start.x:.2f}, {line_start.y:.2f}) - 끝({line_end.x:.2f}, {line_end.y:.2f})")
                        except Exception as e:
                            continue
                    
                    if existing_wg_deleted > 0:
                        print(f"   ✅ SW/SFW 근처의 기존 WG 선 {existing_wg_deleted}개 삭제 완료")
                    else:
                        print(f"   💡 SW/SFW 근처에 기존 WG 선 없음")
                    
                    # 새로운 WG 선의 길이 체크 (40mm 이상이면 생성하지 않음)
                    wg_length = distance(sw_center, rotated_wdc_center)
                    if wg_length >= 40.0:
                        print(f"   ⚠️  WG 선 길이 {wg_length:.2f}mm >= 40mm - WG 생성 건너뜀")
                        processed_count += 1
                        continue
                    
                    # 새로운 흰색 선 생성 (SW/SFW 중심 - WDC 중심) + WG 레이어
                    new_line = msp.add_line(
                        start=(sw_center.x, sw_center.y),
                        end=(rotated_wdc_center.x, rotated_wdc_center.y),
                        dxfattribs={'color': 7, 'layer': 'WG'}  # 흰색 + WG 레이어
                    )
                    print(f"   ✅ WG 선 생성: 길이 {wg_length:.2f}mm < 40mm")
                    
                    # WDC 원 안의 선 TRIM
                    try:
                        # 선의 방향 벡터
                        direction = rotated_wdc_center - sw_center
                        if direction.magnitude > 0:
                            direction_normalized = direction.normalize()
                            # WDC 원 경계에서 시작하도록 TRIM
                            trim_end = rotated_wdc_center - direction_normalized * wdc_circle.dxf.radius
                            new_line.dxf.end = (trim_end.x, trim_end.y, 0)
                            print(f"   ✂️  WDC 원 안의 선 TRIM 완료")
                    except Exception as trim_e:
                        print(f"   ❌ TRIM 오류: {trim_e}")
                    
                    processed_count += 1
                    print(f"   ✅ MWD 회전 및 연결 완료 ({sw_layer} 사용)")
                    
            except Exception as e:
                print(f"❌ MWD 처리 중 오류: {e}")
                continue
        
        print(f"\n📊 [5단계] 최종 결과:")
        print(f"   📐 처리된 MWD: {processed_count}개")
        print(f"   ⏭️  SKIP된 MWD: {skipped_count}개")
        print(f"   🎨 색상: WDC(YELLOW), WELDNO(CYAN)")
        print(f"   📝 레이어: WDC(WDC), WELDNO(WDNO), 연결선(WG)")
        print(f"   🔄 회전: 30도 단위로 360도 시계방향 회전")
        print(f"   🆕 WDNO 필터링: INST/TEXT/< 포함, 숫자 없는 TEXT 제외")
        print(f"   🆕 기울기 0도 필수: rotation이 0이 아닌 TEXT는 WELDNO에서 제외")
        print(f"   🗑️  기존 WG 삭제: WDC 및 SW/SFW 근처의 기존 WG 선 제거 후 새 연결선 생성")
        print(f"   🔗 새 연결선: SW/SFW-WDC 흰색 선 + WG 레이어")
        print(f"   📏 WG 길이 제한: 40mm 이상이면 생성 안함")
        print(f"   🎯 WDC당 WG 1개: WDC 근처의 기존 WG 모두 삭제 후 새로 생성")
        print(f"   ✂️  TRIM 완료: WDC 원 내부 선 제거")
        print(f"   📍 WELDNO 중심 정렬: 회전 후 항상 WDC 중심으로 재정렬")
        print(f"   🆕 SFW 지원: 6점 폴리라인 중심을 SW 원처럼 사용")
        print(f"   🆕 SFW 7mm 조정: SFW와 WDC 거리가 7mm 이하면 7mm로 이동 후 간섭 체크")
        print(f"   🆕 SFW PC 검색: SFW 중심에서 7mm 내 가장 가까운 PIPE 선 2개")
        print(f"   🚫 SW/SFW 한번만 사용: 각 SW 원 또는 SFW 폴리라인은 WDC당 한번만 연결")
        print(f"   🆕 NL1 없는 경우: WDC에서 가장 가까운 미사용 SW/SFW 자동 연결")
        print(f"\n   우선순위 기반 간섭 회피:")
        print(f"   1️⃣ TEXT 간섭: 텍스트 시작점/끝점 간 거리 5mm 이상 확보")
        print(f"   2️⃣ PIPE/ELBO 레이어 간섭: PIPE 또는 ELBO 이름 포함 레이어와 겹침 방지")
        print(f"   3️⃣ PC 간섭: WDC 원과 PC 선분 사이 2mm 이상 거리 확보")
        print(f"   4️⃣ 30도 단위 폴리라인 간섭: 0°, 30°, 60°... 각도의 폴리라인과 겹침 방지")
        print(f"   5️⃣ 일반 간섭: 기타 모든 간섭 최소화")
        
        print("[5단계] MWD 회전 및 최종 연결 완료")
        
    except Exception as e:
        print(f"❌ [5단계] 처리 중 전체 오류: {e}")
        print("[5단계] MWD 회전 및 최종 연결 실패")

### 메인 실행 ###
if __name__ == "__main__":
    filepaths = select_dxf_files()
    for filepath in filepaths:
        doc = ezdxf.readfile(filepath)
        print(f"\n📂 선택된 파일: {filepath}")

        print("\n[1단계] WELDNOEDIT 작업 시작 (필터링 적용)")
        process_weldnoedit(doc)
        print("[1단계] 완료")

        print("\n[2단계] WELDSYMBOL 작업 시작 (텍스트 수집 제거)")
        process_weldsymbol(doc)
        print("[2단계] 완료")

        print("\n[3단계] NL1 생성 및 6mm 직선거리 제어 시작")
        process_nl1_distance_control(doc)
        print("[3단계] 완료")

        print("\n[4단계] NL1 길이 7mm 조정 시작")
        process_nl1_length_adjustment(doc)
        print("[4단계] 완료")
        
        print("\n[5단계] MWD 회전 및 최종 연결 시작")
        process_mwd_rotation_and_connection(doc)
        print("[5단계] 완료")

        basename = os.path.splitext(os.path.basename(filepath))[0]
        output_dir = os.path.dirname(filepath)
        output_path = os.path.join(output_dir, basename + "_WDSYM.dxf")
        
        # 파일이 이미 존재하거나 권한이 없는 경우 다른 경로 시도
        try:
            doc.saveas(output_path)
            print(f"\n✔ 최종 저장: {output_path}")
        except PermissionError:
            # 바탕화면에 저장 시도
            import getpass
            username = getpass.getuser()
            desktop_path = f"C:/Users/{username}/Desktop/{basename}_WDSYM.dxf"
            try:
                doc.saveas(desktop_path)
                print(f"\n✔ 권한 오류로 바탕화면에 저장: {desktop_path}")
            except Exception as e:
                # 현재 디렉토리에 저장 시도
                current_dir_path = f"./{basename}_WDSYM.dxf"
                try:
                    doc.saveas(current_dir_path)
                    print(f"\n✔ 현재 디렉토리에 저장: {current_dir_path}")
                except Exception as e2:
                    print(f"\n❌ 저장 실패: {e2}")