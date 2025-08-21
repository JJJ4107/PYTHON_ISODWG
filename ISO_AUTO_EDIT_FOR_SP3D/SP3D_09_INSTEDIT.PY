import ezdxf
import tkinter as tk
from tkinter import filedialog
import math
import os
from ezdxf.math import Vec2
from ezdxf.entities import Circle, Line, Text, MText
import numpy as np

def get_distance(p1, p2):
    """두 점 사이의 거리 계산"""
    return math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)

def get_circle_diameter(circle):
    """원의 지름 계산"""
    return circle.dxf.radius * 2

def is_point_in_circle(point, circle):
    """점이 원 안에 있는지 확인"""
    center = (circle.dxf.center.x, circle.dxf.center.y)
    return get_distance(point, center) < circle.dxf.radius

def is_text_horizontal(text):
    """텍스트가 수평(기울기 0)인지 확인"""
    if hasattr(text.dxf, 'rotation'):
        return abs(text.dxf.rotation) < 0.1 or abs(text.dxf.rotation - 360) < 0.1
    return True

def is_numeric_text(text):
    """텍스트가 숫자인지 확인"""
    text_content = ""
    if isinstance(text, Text):
        text_content = text.dxf.text
    elif isinstance(text, MText):
        text_content = text.text

    try:
        cleaned = text_content.replace(" ", "").replace(",", "")
        if cleaned:
            float(cleaned)
            return True
    except:
        pass
    return False

def get_line_center(line):
    """선분의 중심점 계산"""
    start = (line.dxf.start.x, line.dxf.start.y)
    end = (line.dxf.end.x, line.dxf.end.y)
    return ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)

def get_line_length(line):
    """선분의 길이 계산"""
    start = (line.dxf.start.x, line.dxf.start.y)
    end = (line.dxf.end.x, line.dxf.end.y)
    return get_distance(start, end)

def get_closest_point_to_center(line, center):
    """선분에서 중심점에 가장 가까운 점 찾기"""
    start = (line.dxf.start.x, line.dxf.start.y)
    end = (line.dxf.end.x, line.dxf.end.y)

    dist_start = get_distance(start, center)
    dist_end = get_distance(end, center)

    return start if dist_start < dist_end else end

def find_line_near_circle(circle, lines, max_distance=1.0):
    """원의 선분에서 max_distance 내에 접하는 라인 찾기"""
    center = Vec2(circle.dxf.center.x, circle.dxf.center.y)
    radius = circle.dxf.radius

    for line in lines:
        start = Vec2(line.dxf.start.x, line.dxf.start.y)
        end = Vec2(line.dxf.end.x, line.dxf.end.y)

        line_vec = end - start
        line_length = line_vec.magnitude
        if line_length == 0:
            continue

        line_dir = line_vec / line_length
        center_to_start = center - start
        projection_length = center_to_start.dot(line_dir)

        if projection_length < 0:
            closest_point = start
        elif projection_length > line_length:
            closest_point = end
        else:
            closest_point = start + line_dir * projection_length

        distance_to_circle = (center - closest_point).magnitude - radius

        if abs(distance_to_circle) <= max_distance:
            return line, (start.x, start.y), (end.x, end.y)

    return None, None, None

def find_lines_near_point(point, lines, max_distance=0.2, max_length=None):
    """점 근처의 라인들 찾기"""
    found_lines = []

    for line in lines:
        start = (line.dxf.start.x, line.dxf.start.y)
        end = (line.dxf.end.x, line.dxf.end.y)

        if get_distance(point, start) <= max_distance or get_distance(point, end) <= max_distance:
            if max_length is None or get_distance(start, end) <= max_length:
                found_lines.append(line)

    return found_lines

def get_line_angle(line):
    """라인의 기울기(각도) 계산"""
    dx = line.dxf.end.x - line.dxf.start.x
    dy = line.dxf.end.y - line.dxf.start.y
    return math.atan2(dy, dx)

def move_entities(entities, dx, dy):
    """엔티티들을 이동"""
    for entity in entities:
        if isinstance(entity, Circle):
            entity.dxf.center = Vec2(entity.dxf.center.x + dx, entity.dxf.center.y + dy)
        elif isinstance(entity, Line):
            entity.dxf.start = Vec2(entity.dxf.start.x + dx, entity.dxf.start.y + dy)
            entity.dxf.end = Vec2(entity.dxf.end.x + dx, entity.dxf.end.y + dy)
        elif isinstance(entity, (Text, MText)):
            if hasattr(entity.dxf, 'insert'):
                entity.dxf.insert = Vec2(entity.dxf.insert[0] + dx, entity.dxf.insert[1] + dy)

def check_line_circle_intersection(line, circle):
    """라인과 원의 교차 여부 확인 (개선된 버전)"""
    center = Vec2(circle.dxf.center.x, circle.dxf.center.y)
    radius = circle.dxf.radius

    start = Vec2(line.dxf.start.x, line.dxf.start.y)
    end = Vec2(line.dxf.end.x, line.dxf.end.y)

    if (end - start).magnitude < 0.001:
        return (start - center).magnitude <= radius

    d = end - start
    f = start - center

    a = d.dot(d)
    b = 2 * f.dot(d)
    c = f.dot(f) - radius * radius

    start_dist = (start - center).magnitude
    end_dist = (end - center).magnitude

    if start_dist <= radius or end_dist <= radius:
        return True

    discriminant = b*b - 4*a*c

    if discriminant < 0:
        return False

    discriminant = math.sqrt(discriminant)

    if a != 0:
        t1 = (-b - discriminant) / (2*a)
        t2 = (-b + discriminant) / (2*a)

        if (-0.001 <= t1 <= 1.001) or (-0.001 <= t2 <= 1.001):
            return True

        if t1 < 0 and t2 > 1:
            return True

    t = max(0, min(1, -f.dot(d) / a))
    closest_point = start + d * t
    distance = (closest_point - center).magnitude

    return distance <= radius + 0.001

def find_ilines_near_circle(inno_circle, lines):
    """INNO 원 중심에서 15mm 내에서 3~5mm 길이의 ISOTEXT 레이어 LINE 4개 찾기"""
    inno_center = (inno_circle.dxf.center.x, inno_circle.dxf.center.y)
    ilines = []

    for line in lines:
        if line.dxf.layer != 'ISOTEXT':
            continue

        length = get_line_length(line)
        if not (3 <= length <= 5):
            continue

        line_center = get_line_center(line)

        if get_distance(inno_center, line_center) <= 15:
            ilines.append(line)

            # [NEW] ILINE을 찾는 즉시 CYAN 지정 (추가 요청)
            try:
                line.dxf.color = 4  # CYAN
            except:
                pass

        if len(ilines) >= 4:
            break

    return ilines

def find_text_near_lines(ilines, texts, max_distance=3.0):
    """ILINE 중심에서 3mm 내의 기울기 0인 숫자 텍스트 찾기"""
    it_texts = []

    for line in ilines:
        line_center = get_line_center(line)

        for text in texts:
            if hasattr(text.dxf, 'insert'):
                text_pos = (text.dxf.insert[0], text.dxf.insert[1])
            else:
                continue

            if (get_distance(line_center, text_pos) <= max_distance and
                is_text_horizontal(text) and
                is_numeric_text(text) and
                text not in it_texts):
                it_texts.append(text)
                break

    return it_texts

def get_circle_top_point(circle):
    """원의 수직 끝점 (Y값이 가장 큰 접점) 계산"""
    center_x = circle.dxf.center.x
    center_y = circle.dxf.center.y
    radius = circle.dxf.radius
    return (center_x, center_y + radius)

def process_dxf_file(filepath):
    """DXF 파일 처리"""
    try:
        doc = ezdxf.readfile(filepath)
        msp = doc.modelspace()

        any_changes_made = False

        # 1. ISOTEXT 레이어의 원 중 지름이 11-18mm인 원 찾기
        inno_circles = []
        for entity in msp:
            if isinstance(entity, Circle) and entity.dxf.layer == 'ISOTEXT':
                diameter = get_circle_diameter(entity)
                if 11 <= diameter <= 18:
                    inno_circles.append(entity)

                    # [NEW] INNO를 찾는 즉시 CYAN 지정 (추가 요청)
                    try:
                        entity.dxf.color = 4  # CYAN
                    except:
                        pass

        if not inno_circles:
            print(f"No circles with diameter 11-18mm found in ISOTEXT layer in {filepath}")
            base_name = os.path.splitext(os.path.basename(filepath))[0]
            output_path = os.path.join(os.path.dirname(filepath), f"{base_name}_INST.DXF")
            doc.saveas(output_path)
            print(f"File saved without changes as: {output_path}")
            return

        all_texts = [e for e in msp if isinstance(e, (Text, MText))]

        for inno in inno_circles:
            inno_center = (inno.dxf.center.x, inno.dxf.center.y)

            del2_found = False

            a1_extension_lines = []
            extension_lines_original_state = []

            # 2. INNO 원 안의 기울기 0인 텍스트 찾기 (ITAG)
            itag_texts = []
            for entity in msp:
                if isinstance(entity, (Text, MText)):
                    if hasattr(entity.dxf, 'insert'):
                        text_pos = (entity.dxf.insert[0], entity.dxf.insert[1])
                    else:
                        continue

                    if is_point_in_circle(text_pos, inno) and is_text_horizontal(entity):
                        itag_texts.append(entity)

            instno_entities = [inno] + itag_texts

            # NEW: ILINE과 IT 찾기
            all_lines = [e for e in msp if isinstance(e, Line)]
            ilines = find_ilines_near_circle(inno, all_lines)

            itemno_entities = []
            it_texts = []

            if ilines:
                it_texts = find_text_near_lines(ilines, all_texts)
                itemno_entities = ilines + it_texts

                # ILINE 중에서 INNO 중심과 가장 가까운 점 찾기 (IP)
                min_distance = float('inf')
                ip_point = None
                for iline in ilines:
                    closest_point = get_closest_point_to_center(iline, inno_center)
                    dist = get_distance(closest_point, inno_center)
                    if dist < min_distance:
                        min_distance = dist
                        ip_point = closest_point

                instno_entities.extend(itemno_entities)

            # 3. 원의 선분에서 1mm 내에 접하는 ISOTEXT 레이어 LINE 찾기 (A1)
            isotext_lines = [e for e in msp if isinstance(e, Line) and e.dxf.layer == 'ISOTEXT']
            a1_line_original, ap1_original, ap2_original = find_line_near_circle(inno, isotext_lines, 1.0)

            if not a1_line_original:
                continue

            a1_line = a1_line_original
            ap1 = ap1_original
            ap2 = ap2_original
            original_start = Vec2(a1_line.dxf.start.x, a1_line.dxf.start.y)
            original_end = Vec2(a1_line.dxf.end.x, a1_line.dxf.end.y)

            if get_distance(ap1, inno_center) > get_distance(ap2, inno_center):
                ap1, ap2 = ap2, ap1

            # 4. AP2 점 0.2mm 내에서 길이 2mm 이하 LINE 2개와 추가 LINE 찾기 (DEL1)
            all_lines = [e for e in msp if isinstance(e, Line)]
            lines_near_ap2 = find_lines_near_point(ap2, all_lines, 0.2, 2.0)

            del1_lines = []
            if len(lines_near_ap2) >= 2:
                del1_lines.extend(lines_near_ap2[:2])

                for line in lines_near_ap2[:2]:
                    start = (line.dxf.start.x, line.dxf.start.y)
                    end = (line.dxf.end.x, line.dxf.end.y)

                    additional_lines = find_lines_near_point(start, all_lines, 0.2, 1.0)
                    additional_lines.extend(find_lines_near_point(end, all_lines, 0.2, 1.0))

                    for add_line in additional_lines:
                        if add_line not in del1_lines and len(del1_lines) < 3:
                            del1_lines.append(add_line)
                            break

                    if len(del1_lines) >= 3:
                        break

            if len(del1_lines) < 3:
                for line in all_lines:
                    if line == a1_line:
                        continue

                    start = (line.dxf.start.x, line.dxf.start.y)
                    end = (line.dxf.end.x, line.dxf.end.y)

                    if get_distance(ap2, start) <= 0.2:
                        extension_lines_original_state.append({
                            'line': line,
                            'start': Vec2(line.dxf.start.x, line.dxf.start.y),
                            'end': Vec2(line.dxf.end.x, line.dxf.end.y)
                        })

                        if get_distance(ap1, a1_line.dxf.start) < 0.1:
                            a1_line.dxf.start = Vec2(end[0], end[1])
                        else:
                            a1_line.dxf.end = Vec2(end[0], end[1])
                        ap2 = end

                        a1_extension_lines.append(line)

                        lines_near_ap2 = find_lines_near_point(ap2, all_lines, 0.2, 2.0)
                        del1_lines = []
                        if len(lines_near_ap2) >= 2:
                            del1_lines.extend(lines_near_ap2[:2])

                            for line2 in lines_near_ap2[:2]:
                                start2 = (line2.dxf.start.x, line2.dxf.start.y)
                                end2 = (line2.dxf.end.x, line2.dxf.end.y)

                                additional_lines = find_lines_near_point(start2, all_lines, 0.2, 1.0)
                                additional_lines.extend(find_lines_near_point(end2, all_lines, 0.2, 1.0))

                                for add_line in additional_lines:
                                    if add_line not in del1_lines and len(del1_lines) < 3:
                                        del1_lines.append(add_line)
                                        break

                                if len(del1_lines) >= 3:
                                    break
                        break
                    elif get_distance(ap2, end) <= 0.2:
                        extension_lines_original_state.append({
                            'line': line,
                            'start': Vec2(line.dxf.start.x, line.dxf.start.y),
                            'end': Vec2(line.dxf.end.x, line.dxf.end.y)
                        })

                        if get_distance(ap1, a1_line.dxf.start) < 0.1:
                            a1_line.dxf.start = Vec2(start[0], start[1])
                        else:
                            a1_line.dxf.end = Vec2(start[0], start[1])
                        ap2 = start

                        a1_extension_lines.append(line)

                        lines_near_ap2 = find_lines_near_point(ap2, all_lines, 0.2, 2.0)
                        del1_lines = []
                        if len(lines_near_ap2) >= 2:
                            del1_lines.extend(lines_near_ap2[:2])

                            for line2 in lines_near_ap2[:2]:
                                start2 = (line2.dxf.start.x, line2.dxf.start.y)
                                end2 = (line2.dxf.end.x, line2.dxf.end.y)

                                additional_lines = find_lines_near_point(start2, all_lines, 0.2, 1.0)
                                additional_lines.extend(find_lines_near_point(end2, all_lines, 0.2, 1.0))

                                for add_line in additional_lines:
                                    if add_line not in del1_lines and len(del1_lines) < 3:
                                        del1_lines.append(add_line)
                                        break

                                if len(del1_lines) >= 3:
                                    break
                        break

            # 5. AP2에서 10mm 내의 FITTINGS 레이어 원 찾기 (TYPE1/DEL2)
            del2_circle = None
            for entity in msp:
                if isinstance(entity, Circle) and entity.dxf.layer == 'FITTINGS':
                    if entity in []:
                        pass

                    diameter = get_circle_diameter(entity)
                    if 5 <= diameter <= 8:
                        circle_center = (entity.dxf.center.x, entity.dxf.center.y)
                        if get_distance(ap2, circle_center) <= 10:
                            del2_circle = entity
                            # [NEW] DEL2를 찾는 즉시 CYAN 지정 (추가 요청)
                            try:
                                del2_circle.dxf.color = 4  # CYAN
                            except:
                                pass
                            del2_found = True
                            break

            if not del2_found:
                print(f"No DEL2 circle found for INNO at ({inno_center[0]:.2f}, {inno_center[1]:.2f})")
                if a1_line:
                    a1_line.dxf.start = original_start
                    a1_line.dxf.end = original_end
                for state in extension_lines_original_state:
                    state['line'].dxf.start = state['start']
                    state['line'].dxf.end = state['end']
                continue

            # ===== 이하 DEL2가 발견된 경우에만 실행되는 코드 =====
            any_changes_made = True

            # INNO와 ITAG 색상/레이어 변경 (기존 로직 유지)
            inno.dxf.layer = 'INNO'
            inno.dxf.color = 4  # CYAN
            for entity in itag_texts:
                entity.dxf.color = 2  # YELLOW

            # ILINE과 IT 색상 변경 (기존 로직 유지: ILINE/IT은 MAGENTA)
            for iline in ilines:
                iline.dxf.color = 6  # MAGENTA
            for it in it_texts:
                it.dxf.color = 6  # MAGENTA

            # IP에서 INNO 수직 끝점으로 ITEMNO 이동
            if itemno_entities and 'ip_point' in locals() and ip_point:
                top_point = get_circle_top_point(inno)
                dx = top_point[0] - ip_point[0]
                dy = top_point[1] - ip_point[1]
                move_entities(itemno_entities, dx, dy)

            # A1 색상 변경
            a1_line.dxf.color = 4  # CYAN

            # DEL1 색상 변경
            for line in del1_lines:
                line.dxf.color = 4  # CYAN

            # DEL2 색상 변경 (이미 위에서 CYAN, 여기서도 유지)
            del2_circle.dxf.color = 4  # CYAN

            # 6. DEL2 원을 접하는 FITTINGS 레이어 LINE 찾기 (INLINE)
            fittings_lines = [e for e in msp if isinstance(e, Line) and e.dxf.layer == 'FITTINGS']
            inline = None
            ap3 = None
            ap4 = None

            for line in fittings_lines:
                if line == a1_line or line in del1_lines:
                    continue

                start = (line.dxf.start.x, line.dxf.start.y)
                end = (line.dxf.end.x, line.dxf.end.y)
                del2_center = (del2_circle.dxf.center.x, del2_circle.dxf.center.y)

                dist_start = get_distance(start, del2_center)
                dist_end = get_distance(end, del2_center)

                if abs(dist_start - del2_circle.dxf.radius) < 1.0 or abs(dist_end - del2_circle.dxf.radius) < 1.0:
                    inline = line
                    inline.dxf.color = 4  # CYAN
                    if dist_start < dist_end:
                        ap3 = start
                        ap4 = end
                    else:
                        ap3 = end
                        ap4 = start
                    break

            if not inline:
                continue

            # 7. INSTNO를 INNO 중심에서 DEL2 중심으로 이동 (ITEMNO 포함)
            dx = del2_circle.dxf.center.x - inno.dxf.center.x
            dy = del2_circle.dxf.center.y - inno.dxf.center.y
            move_entities(instno_entities, dx, dy)

            # 8. INLINE의 기울기로 INSTNO를 AP4에서 AP3 방향으로 15mm 이동 (ITEMNO 포함)
            angle = get_line_angle(inline)
            direction = Vec2(ap3[0] - ap4[0], ap3[1] - ap4[1]).normalize()
            move_dx = direction.x * 15
            move_dy = direction.y * 15
            move_entities(instno_entities, move_dx, move_dy)

            # 8-1. DL 레이어 LINE과 INNO 원의 간섭 체크
            dl_lines = [e for e in msp if isinstance(e, Line) and e.dxf.layer.upper() == 'DL']
            interference_found = False

            print(f"\n=== Interference Check for INNO at ({inno.dxf.center.x:.2f}, {inno.dxf.center.y:.2f}) ===")
            print(f"INNO radius: {inno.dxf.radius:.2f}")

            if dl_lines:
                print(f"Found {len(dl_lines)} DL layer lines")
                for idx, dl_line in enumerate(dl_lines):
                    start = (dl_line.dxf.start.x, dl_line.dxf.start.y)
                    end = (dl_line.dxf.end.x, dl_line.dxf.end.y)

                    line_vec = Vec2(end[0] - start[0], end[1] - start[1])
                    line_length = line_vec.magnitude
                    if line_length > 0:
                        line_dir = line_vec / line_length
                        center_to_start = Vec2(inno.dxf.center.x - start[0], inno.dxf.center.y - start[1])
                        projection = center_to_start.dot(line_dir)
                        projection = max(0, min(line_length, projection))
                        closest_point = Vec2(start[0], start[1]) + line_dir * projection
                        min_distance = (Vec2(inno.dxf.center.x, inno.dxf.center.y) - closest_point).magnitude

                        print(f"  DL line {idx}: ({start[0]:.2f},{start[1]:.2f}) to ({end[0]:.2f},{end[1]:.2f})")
                        print(f"    Min distance to INNO center: {min_distance:.2f} (radius: {inno.dxf.radius:.2f})")

                    if check_line_circle_intersection(dl_line, inno):
                        interference_found = True
                        print(f"  >>> INTERFERENCE DETECTED with DL line {idx}!")
                        break

                if not interference_found:
                    print("  No interference detected with any DL lines")
            else:
                all_layers = set(e.dxf.layer for e in msp if isinstance(e, Line))
                print(f"No DL layer lines found. Available line layers: {list(all_layers)}")

                dl_like_layers = [layer for layer in all_layers if 'DL' in layer.upper()]
                if dl_like_layers:
                    print(f"Found similar layers: {dl_like_layers}")

            # 8-2. 간섭이 발생하면 4mm 추가 이동
            if interference_found:
                additional_move_dx = direction.x * 4
                additional_move_dy = direction.y * 4
                move_entities(instno_entities, additional_move_dx, additional_move_dy)
                print(f">>> Additional 4mm movement applied: dx={additional_move_dx:.2f}, dy={additional_move_dy:.2f}")

            # 9. INLINE의 AP3 점을 INNO 선분까지 확장
            start = (inline.dxf.start.x, inline.dxf.start.y)
            end = (inline.dxf.end.x, inline.dxf.end.y)

            dist_start_to_del2 = get_distance(start, (del2_circle.dxf.center.x, del2_circle.dxf.center.y))
            dist_end_to_del2 = get_distance(end, (del2_circle.dxf.center.x, del2_circle.dxf.center.y))

            if dist_start_to_del2 < dist_end_to_del2:
                inno_center_vec = Vec2(inno.dxf.center.x, inno.dxf.center.y)
                start_vec = Vec2(start[0], start[1])
                to_start = start_vec - inno_center_vec
                if to_start.magnitude > 0:
                    direction_to_boundary = to_start.normalize()
                    boundary_point = inno_center_vec + direction_to_boundary * inno.dxf.radius
                    inline.dxf.start = boundary_point
                    print(f"Extended INLINE start to INNO boundary: ({boundary_point.x:.2f}, {boundary_point.y:.2f})")
            else:
                inno_center_vec = Vec2(inno.dxf.center.x, inno.dxf.center.y)
                end_vec = Vec2(end[0], end[1])
                to_end = end_vec - inno_center_vec
                if to_end.magnitude > 0:
                    direction_to_boundary = to_end.normalize()
                    boundary_point = inno_center_vec + direction_to_boundary * inno.dxf.radius
                    inline.dxf.end = boundary_point
                    print(f"Extended INLINE end to INNO boundary: ({boundary_point.x:.2f}, {boundary_point.y:.2f})")

            # 10. 엔티티 정리
            entities_to_delete = del1_lines + [del2_circle, a1_line] + a1_extension_lines
            entities_to_modify = instno_entities + [inline, inno]

            for entity in entities_to_delete:
                if entity:
                    try:
                        msp.delete_entity(entity)
                    except:
                        pass

            for entity in entities_to_modify:
                if entity:
                    entity.dxf.layer = 'INSTNO'
                    if entity not in itag_texts and entity not in it_texts:
                        entity.dxf.color = 4  # CYAN

        base_name = os.path.splitext(os.path.basename(filepath))[0]
        output_path = os.path.join(os.path.dirname(filepath), f"{base_name}_INST.DXF")
        doc.saveas(output_path)

        if any_changes_made:
            print(f"Processed file saved as: {output_path}")
        else:
            print(f"File saved without changes as: {output_path}")

    except Exception as e:
        print(f"Error processing {filepath}: {str(e)}")

def main():
    """메인 함수 - 파일 선택 대화상자 표시"""
    root = tk.Tk()
    root.withdraw()

    file_paths = filedialog.askopenfilenames(
        title="Select DXF files",
        filetypes=[("DXF files", "*.dxf"), ("All files", "*.*")]
    )

    if not file_paths:
        print("No files selected.")
        return

    for filepath in file_paths:
        print(f"\nProcessing: {filepath}")
        process_dxf_file(filepath)

    print("\nAll files processed.")

if __name__ == "__main__":
    main()
