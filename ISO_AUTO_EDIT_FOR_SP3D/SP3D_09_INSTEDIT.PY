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

def find_line_near_circle(circle, lines, max_distance=1.0):
    """원의 선분에서 max_distance 내에 접하는 라인 찾기"""
    center = Vec2(circle.dxf.center.x, circle.dxf.center.y)
    radius = circle.dxf.radius
    
    for line in lines:
        start = Vec2(line.dxf.start.x, line.dxf.start.y)
        end = Vec2(line.dxf.end.x, line.dxf.end.y)
        
        # 라인과 원의 최단 거리 계산
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
            return line, start, end
            
    return None, None, None

def find_lines_near_point(point, lines, max_distance=0.2, max_length=None):
    """점 근처의 라인들 찾기"""
    found_lines = []
    
    for line in lines:
        start = (line.dxf.start.x, line.dxf.start.y)
        end = (line.dxf.end.x, line.dxf.end.y)
        
        # 점과 라인의 최단 거리 계산
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

def extend_line_to_circle(line, point_to_extend, circle):
    """라인을 원까지 확장"""
    center = Vec2(circle.dxf.center.x, circle.dxf.center.y)
    radius = circle.dxf.radius
    
    # 라인의 방향 벡터 계산
    start = Vec2(line.dxf.start.x, line.dxf.start.y)
    end = Vec2(line.dxf.end.x, line.dxf.end.y)
    
    if get_distance(point_to_extend, start) < 0.1:
        # start 점을 확장
        direction = (start - end).normalize()
        # 원과 라인의 교점 계산
        t = 2 * radius  # 충분히 긴 거리
        new_point = start + direction * t
        
        # 실제 교점 찾기
        for i in range(100):
            test_point = start + direction * (t * i / 100)
            if abs(get_distance((test_point.x, test_point.y), (center.x, center.y)) - radius) < 0.1:
                line.dxf.start = test_point
                break
    else:
        # end 점을 확장
        direction = (end - start).normalize()
        t = 2 * radius
        new_point = end + direction * t
        
        for i in range(100):
            test_point = end + direction * (t * i / 100)
            if abs(get_distance((test_point.x, test_point.y), (center.x, center.y)) - radius) < 0.1:
                line.dxf.end = test_point
                break

def process_dxf_file(filepath):
    """DXF 파일 처리"""
    try:
        # DXF 파일 읽기
        doc = ezdxf.readfile(filepath)
        msp = doc.modelspace()
        
        # 1. ISOTEXT 레이어의 원 중 지름이 11-18mm인 원 찾기
        inno_circles = []
        for entity in msp:
            if isinstance(entity, Circle) and entity.dxf.layer == 'ISOTEXT':
                diameter = get_circle_diameter(entity)
                if 11 <= diameter <= 18:
                    inno_circles.append(entity)
                    entity.dxf.layer = 'INNO'
                    entity.dxf.color = 4  # CYAN
        
        if not inno_circles:
            print(f"No circles with diameter 11-18mm found in ISOTEXT layer in {filepath}")
            return
        
        # 각 INNO 원에 대해 처리
        all_entities_to_modify = []
        used_del2_circles = []  # 이미 사용된 DEL2 원들을 추적
        
        for inno in inno_circles:
            inno_center = (inno.dxf.center.x, inno.dxf.center.y)
            
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
                        entity.dxf.color = 2  # YELLOW
            
            # INSTNO = INNO + ITAG
            instno_entities = [inno] + itag_texts
            
            # 3. 원의 선분에서 1mm 내에 접하는 ISOTEXT 레이어 LINE 찾기 (A1)
            isotext_lines = [e for e in msp if isinstance(e, Line) and e.dxf.layer == 'ISOTEXT']
            a1_line, ap1, ap2 = find_line_near_circle(inno, isotext_lines, 1.0)
            
            if not a1_line:
                continue
            
            a1_line.dxf.color = 4  # CYAN
            
            # AP1은 INNO에 가까운 점, AP2는 먼 점
            if get_distance(ap1, inno_center) > get_distance(ap2, inno_center):
                ap1, ap2 = ap2, ap1
            
            # 4. AP2 점 0.2mm 내에서 길이 2mm 이하 LINE 2개와 추가 LINE 찾기 (DEL1)
            all_lines = [e for e in msp if isinstance(e, Line)]
            lines_near_ap2 = find_lines_near_point(ap2, all_lines, 0.2, 2.0)
            
            del1_lines = []
            if len(lines_near_ap2) >= 2:
                del1_lines.extend(lines_near_ap2[:2])
                
                # 추가 1mm 이하 LINE 찾기
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
            
            # DEL1이 찾아지지 않으면 추가 검색
            if len(del1_lines) < 3:
                # AP2에서 0.2mm 내에 접하는 A1과 동일한 방향의 LINE 찾기
                for line in all_lines:
                    if line == a1_line:
                        continue
                    
                    start = (line.dxf.start.x, line.dxf.start.y)
                    end = (line.dxf.end.x, line.dxf.end.y)
                    
                    # AP2와 가까운 점 찾기
                    if get_distance(ap2, start) <= 0.2:
                        # A1 라인 연장 (합치기)
                        if get_distance(ap1, a1_line.dxf.start) < 0.1:
                            a1_line.dxf.start = Vec2(end[0], end[1])
                        else:
                            a1_line.dxf.end = Vec2(end[0], end[1])
                        ap2 = end
                        
                        # 새로운 AP2에서 다시 DEL1 찾기
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
                        # A1 라인 연장 (합치기)
                        if get_distance(ap1, a1_line.dxf.start) < 0.1:
                            a1_line.dxf.start = Vec2(start[0], start[1])
                        else:
                            a1_line.dxf.end = Vec2(start[0], start[1])
                        ap2 = start
                        
                        # 새로운 AP2에서 다시 DEL1 찾기
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
            
            # DEL1 라인들을 CYAN으로 변경
            for line in del1_lines:
                line.dxf.color = 4  # CYAN
            
            # 5. AP2에서 10mm 내의 FITTINGS 레이어 원 찾기 (TYPE1/DEL2)
            del2_circle = None
            for entity in msp:
                if isinstance(entity, Circle) and entity.dxf.layer == 'FITTINGS':
                    # 이미 사용된 DEL2인지 확인
                    if entity in used_del2_circles:
                        continue
                        
                    diameter = get_circle_diameter(entity)
                    if 5 <= diameter <= 8:
                        circle_center = (entity.dxf.center.x, entity.dxf.center.y)
                        if get_distance(ap2, circle_center) <= 10:
                            del2_circle = entity
                            del2_circle.dxf.color = 4  # CYAN
                            used_del2_circles.append(entity)  # 사용된 DEL2로 표시
                            break
            
            if not del2_circle:
                continue
            
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
                
                # 라인이 DEL2 원을 접하는지 확인
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
            
            # 7. INSTNO를 INNO 중심에서 DEL2 중심으로 이동
            dx = del2_circle.dxf.center.x - inno.dxf.center.x
            dy = del2_circle.dxf.center.y - inno.dxf.center.y
            move_entities(instno_entities, dx, dy)
            
            # 8. INLINE의 기울기로 INSTNO를 AP4에서 AP3 방향으로 15mm 이동
            angle = get_line_angle(inline)
            # AP4에서 AP3 방향 벡터
            direction = Vec2(ap3[0] - ap4[0], ap3[1] - ap4[1]).normalize()
            move_dx = direction.x * 15
            move_dy = direction.y * 15
            move_entities(instno_entities, move_dx, move_dy)
            
            # 9. INLINE의 AP3 점을 INNO 선분까지 확장
            extend_line_to_circle(inline, ap3, inno)
            
            # 10. 모든 엔티티를 INSTNO 레이어로 변경하고 CYAN 색상으로
            # DEL1, DEL2, A1은 삭제하고 나머지만 처리
            entities_to_delete = del1_lines + [del2_circle, a1_line]
            entities_to_modify = instno_entities + [inline, inno]
            
            # 삭제할 엔티티들 삭제
            for entity in entities_to_delete:
                if entity:
                    try:
                        msp.delete_entity(entity)
                    except:
                        pass
            
            # 나머지 엔티티들 처리
            for entity in entities_to_modify:
                if entity:
                    entity.dxf.layer = 'INSTNO'
                    if entity not in itag_texts:  # ITAG는 YELLOW 유지
                        entity.dxf.color = 4  # CYAN
                    all_entities_to_modify.append(entity)
        
        # 11. 파일 저장
        base_name = os.path.splitext(os.path.basename(filepath))[0]
        output_path = os.path.join(os.path.dirname(filepath), f"{base_name}_INST.DXF")
        doc.saveas(output_path)
        print(f"Processed file saved as: {output_path}")
        
    except Exception as e:
        print(f"Error processing {filepath}: {str(e)}")

def main():
    """메인 함수 - 파일 선택 대화상자 표시"""
    root = tk.Tk()
    root.withdraw()  # 메인 윈도우 숨기기
    
    # 파일 선택 대화상자
    file_paths = filedialog.askopenfilenames(
        title="Select DXF files",
        filetypes=[("DXF files", "*.dxf"), ("All files", "*.*")]
    )
    
    if not file_paths:
        print("No files selected.")
        return
    
    # 선택된 모든 파일 처리
    for filepath in file_paths:
        print(f"\nProcessing: {filepath}")
        process_dxf_file(filepath)
    
    print("\nAll files processed.")

if __name__ == "__main__":
    main()