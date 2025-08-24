import ezdxf
import math
import os
import sys
import glob
from ezdxf.math import Vec2
from ezdxf.entities import Circle, Line, Text, MText
import numpy as np

def get_distance(p1, p2):
    return math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)

def get_circle_diameter(circle):
    return circle.dxf.radius * 2

def is_point_in_circle(point, circle):
    center = (circle.dxf.center.x, circle.dxf.center.y)
    return get_distance(point, center) < circle.dxf.radius

def is_text_horizontal(text):
    if hasattr(text.dxf, 'rotation'):
        return abs(text.dxf.rotation) < 0.1 or abs(text.dxf.rotation - 360) < 0.1
    return True

def is_numeric_text(text):
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
    start = (line.dxf.start.x, line.dxf.start.y)
    end = (line.dxf.end.x, line.dxf.end.y)
    return ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)

def get_line_length(line):
    start = (line.dxf.start.x, line.dxf.start.y)
    end = (line.dxf.end.x, line.dxf.end.y)
    return get_distance(start, end)

def get_closest_point_to_center(line, center):
    start = (line.dxf.start.x, line.dxf.start.y)
    end = (line.dxf.end.x, line.dxf.end.y)
    dist_start = get_distance(start, center)
    dist_end = get_distance(end, center)
    return start if dist_start < dist_end else end

def find_line_near_circle(circle, lines, max_distance=1.0):
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
    found_lines = []
    for line in lines:
        start = (line.dxf.start.x, line.dxf.start.y)
        end = (line.dxf.end.x, line.dxf.end.y)
        if get_distance(point, start) <= max_distance or get_distance(point, end) <= max_distance:
            if max_length is None or get_distance(start, end) <= max_length:
                found_lines.append(line)
    return found_lines

def get_line_angle(line):
    dx = line.dxf.end.x - line.dxf.start.x
    dy = line.dxf.end.y - line.dxf.start.y
    return math.atan2(dy, dx)

def move_entities(entities, dx, dy):
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
    """
    INNO 원 중심에서 15mm 내에서 3~5mm 길이의 ILINE 최대 4개 찾기.
    레이어: ISOTEXT 또는 ITEMPOS 허용.
    """
    inno_center = (inno_circle.dxf.center.x, inno_circle.dxf.center.y)
    ilines = []
    for line in lines:
        if line.dxf.layer not in ('ISOTEXT', 'ITEMPOS'):
            continue
        length = get_line_length(line)
        if not (3 <= length <= 5):
            continue
        line_center = get_line_center(line)
        if get_distance(inno_center, line_center) <= 15:
            ilines.append(line)
            try:
                line.dxf.color = 4  # CYAN
            except:
                pass
        if len(ilines) >= 4:
            break
    return ilines

def find_text_near_lines(ilines, texts, max_distance=3.0):
    """
    ILINE 중심에서 3mm 내의 기울기 0인 숫자 텍스트 찾기.
    """
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
    center_x = circle.dxf.center.x
    center_y = circle.dxf.center.y
    radius = circle.dxf.radius
    return (center_x, center_y + radius)

def process_dxf_file(filepath):
    try:
        doc = ezdxf.readfile(filepath)
        msp = doc.modelspace()
        any_changes_made = False

        inno_circles = []
        for entity in msp:
            if isinstance(entity, Circle) and entity.dxf.layer == 'ISOTEXT':
                diameter = get_circle_diameter(entity)
                if 11 <= diameter <= 18:
                    inno_circles.append(entity)
                    try:
                        entity.dxf.color = 4  # CYAN
                    except:
                        pass

        if not inno_circles:
            base_name = os.path.splitext(os.path.basename(filepath))[0]
            output_path = os.path.join(os.path.dirname(filepath), f"{base_name}_INST.DXF")
            doc.saveas(output_path)
            return

        all_texts = [e for e in msp if isinstance(e, (Text, MText))]

        for inno in inno_circles:
            inno_center = (inno.dxf.center.x, inno.dxf.center.y)

            del2_found = False
            a1_extension_lines = []
            extension_lines_original_state = []

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

            all_lines = [e for e in msp if isinstance(e, Line)]
            ilines = find_ilines_near_circle(inno, all_lines)

            itemno_entities = []
            it_texts = []

            if ilines:
                it_texts = find_text_near_lines(ilines, all_texts)
                itemno_entities = ilines + it_texts
                min_distance = float('inf')
                ip_point = None
                for iline in ilines:
                    closest_point = get_closest_point_to_center(iline, inno_center)
                    dist = get_distance(closest_point, inno_center)
                    if dist < min_distance:
                        min_distance = dist
                        ip_point = closest_point
                instno_entities.extend(itemno_entities)

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

            del2_circle = None
            for entity in msp:
                if isinstance(entity, Circle) and entity.dxf.layer == 'FITTINGS':
                    diameter = get_circle_diameter(entity)
                    if 5 <= diameter <= 8:
                        circle_center = (entity.dxf.center.x, entity.dxf.center.y)
                        if get_distance(ap2, circle_center) <= 10:
                            del2_circle = entity
                            try:
                                del2_circle.dxf.color = 4  # CYAN
                            except:
                                pass
                            del2_found = True
                            break

            if not del2_found:
                if a1_line:
                    a1_line.dxf.start = original_start
                    a1_line.dxf.end = original_end
                for state in extension_lines_original_state:
                    state['line'].dxf.start = state['start']
                    state['line'].dxf.end = state['end']
                continue

            any_changes_made = True
            inno.dxf.layer = 'INNO'
            inno.dxf.color = 4
            for entity in itag_texts:
                entity.dxf.color = 2
            for iline in ilines:
                iline.dxf.color = 6
            for it in it_texts:
                it.dxf.color = 6

            if itemno_entities and 'ip_point' in locals() and ip_point:
                top_point = get_circle_top_point(inno)
                dx = top_point[0] - ip_point[0]
                dy = top_point[1] - ip_point[1]
                move_entities(itemno_entities, dx, dy)

            a1_line.dxf.color = 4
            for line in del1_lines:
                line.dxf.color = 4
            del2_circle.dxf.color = 4

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
                    inline.dxf.color = 4
                    if dist_start < dist_end:
                        ap3 = start
                        ap4 = end
                    else:
                        ap3 = end
                        ap4 = start
                    break
            if not inline:
                continue

            dx = del2_circle.dxf.center.x - inno.dxf.center.x
            dy = del2_circle.dxf.center.y - inno.dxf.center.y
            move_entities(instno_entities, dx, dy)

            angle = get_line_angle(inline)
            direction = Vec2(ap3[0] - ap4[0], ap3[1] - ap4[1]).normalize()
            move_dx = direction.x * 15
            move_dy = direction.y * 15
            move_entities(instno_entities, move_dx, move_dy)

            dl_lines = [e for e in msp if isinstance(e, Line) and e.dxf.layer.upper() == 'DL']
            interference_found = False
            for dl_line in dl_lines:
                if check_line_circle_intersection(dl_line, inno):
                    interference_found = True
                    break
            if interference_found:
                additional_move_dx = direction.x * 4
                additional_move_dy = direction.y * 4
                move_entities(instno_entities, additional_move_dx, additional_move_dy)

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
            else:
                inno_center_vec = Vec2(inno.dxf.center.x, inno.dxf.center.y)
                end_vec = Vec2(end[0], end[1])
                to_end = end_vec - inno_center_vec
                if to_end.magnitude > 0:
                    direction_to_boundary = to_end.normalize()
                    boundary_point = inno_center_vec + direction_to_boundary * inno.dxf.radius
                    inline.dxf.end = boundary_point

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
                        entity.dxf.color = 4

        base_name = os.path.splitext(os.path.basename(filepath))[0]
        output_path = os.path.join(os.path.dirname(filepath), f"{base_name}_INST.DXF")
        doc.saveas(output_path)

    except Exception:
        pass

def _expand_cli_paths(argv):
    paths = []
    for a in argv:
        expanded = glob.glob(a)
        if expanded:
            paths.extend(expanded)
        else:
            paths.append(a)
    uniq = []
    seen = set()
    for p in paths:
        ap = os.path.abspath(p)
        if ap not in seen and os.path.isfile(ap):
            seen.add(ap)
            uniq.append(ap)
    return uniq

def main():
    args = sys.argv[1:]
    if not args:
        return
    file_paths = _expand_cli_paths(args)
    for filepath in file_paths:
        process_dxf_file(filepath)

if __name__ == "__main__":
    main()
