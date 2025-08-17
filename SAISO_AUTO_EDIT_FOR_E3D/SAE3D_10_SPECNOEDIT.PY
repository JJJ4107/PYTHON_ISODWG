import ezdxf
from ezdxf.math import Vec2
import tkinter as tk
from tkinter import filedialog
import os
import math
from collections import defaultdict

def get_polyline_points(entity):
    """폴리라인 또는 LW폴리라인의 점들을 가져오기"""
    points = []
    if entity.dxftype() == 'POLYLINE':
        for vertex in entity.vertices:
            points.append(Vec2(vertex.dxf.location))
    elif entity.dxftype() == 'LWPOLYLINE':
        points = [Vec2(p) for p in entity.get_points('xy')]
    return points

def get_polyline_segments(entity):
    """폴리라인의 선분들을 가져오기"""
    points = get_polyline_points(entity)
    segments = []
    for i in range(len(points) - 1):
        segments.append((points[i], points[i + 1]))
    if entity.is_closed and len(points) > 2:
        segments.append((points[-1], points[0]))
    return segments

def point_to_segment_distance(point, seg_start, seg_end):
    """점과 선분 사이의 최단 거리 계산"""
    line_vec = seg_end - seg_start
    point_vec = point - seg_start
    line_len = line_vec.magnitude
    
    if line_len == 0:
        return point_vec.magnitude
    
    t = max(0, min(1, point_vec.dot(line_vec) / (line_len * line_len)))
    projection = seg_start + line_vec * t
    return (point - projection).magnitude

def point_to_polyline_distance(point, entity):
    """점과 폴리라인 사이의 최단 거리 계산"""
    segments = get_polyline_segments(entity)
    min_dist = float('inf')
    
    for seg_start, seg_end in segments:
        dist = point_to_segment_distance(point, seg_start, seg_end)
        min_dist = min(min_dist, dist)
    
    return min_dist

def find_nearest_text_from_points(msp, polyline, max_dist, contains_text=None, used_texts=None):
    """폴리라인의 각 점에서 가장 가까운 텍스트 찾기 (중복 선택 방지)"""
    if used_texts is None:
        used_texts = set()
    
    points = get_polyline_points(polyline)
    nearest_text = None
    min_distance = float('inf')
    
    for entity in msp.query('TEXT'):
        # 이미 사용된 텍스트는 제외
        if entity in used_texts:
            continue
            
        if contains_text and contains_text.upper() not in entity.dxf.text.upper():
            continue
        
        text_pos = Vec2(entity.dxf.insert)
        
        # 각 점에서의 최소 거리 계산
        for point in points:
            dist = (text_pos - point).magnitude
            if dist <= max_dist and dist < min_distance:
                min_distance = dist
                nearest_text = entity
    
    return nearest_text

def find_text_in_region(msp, x, y, dx, dy):
    """특정 영역 내의 텍스트 찾기"""
    texts = []
    for entity in msp.query('TEXT'):
        text_pos = entity.dxf.insert
        if (x - dx <= text_pos[0] <= x + dx and 
            y - dy <= text_pos[1] <= y + dy):
            texts.append(entity)
    return texts

def add_text_to_circle(msp, center, text_value, height, color, layer):
    """원 중심에 텍스트 추가 - (0,0)에 생성 후 중심으로 이동"""
    try:
        # 1단계: (0, 0) 위치에 TEXT 생성
        text = msp.add_text(
            text_value,
            dxfattribs={
                'height': height,
                'color': color,
                'layer': layer,
                'insert': (0, 0, 0),  # (0, 0) 위치에 생성
                'halign': 1,  # CENTER
                'valign': 2   # MIDDLE
            }
        )
        
        # 2단계: transform을 사용하여 이동
        try:
            from ezdxf.math import Matrix44
            # 이동 변환 행렬 생성
            transform = Matrix44.translate(center[0], center[1], 0)
            # 텍스트에 변환 적용
            text.transform(transform)
            return text
            
        except Exception as e:
            # transform이 실패하면 삭제 후 재생성
            try:
                msp.delete_entity(text)
            except:
                pass
            
            # 원 중심에 새로 생성
            new_text = msp.add_text(
                text_value,
                dxfattribs={
                    'height': height,
                    'color': color,
                    'layer': layer,
                    'insert': (center[0], center[1], 0),
                    'halign': 1,
                    'valign': 2
                }
            )
            return new_text
        
    except Exception as e:
        # 최후의 시도: 원 중심에 직접 생성
        try:
            text = msp.add_text(
                text_value,
                dxfattribs={
                    'height': height,
                    'color': color,
                    'layer': layer,
                    'insert': (center[0], center[1], 0),
                    'halign': 1,
                    'valign': 2
                }
            )
            return text
        except:
            return None

def find_nearest_polyline_with_points(msp, point, max_dist, num_points):
    """특정 점 근처의 특정 점 개수를 가진 폴리라인 찾기"""
    nearest = None
    min_dist = float('inf')
    
    for entity in msp.query('POLYLINE LWPOLYLINE'):
        points = get_polyline_points(entity)
        if len(points) != num_points:
            continue
        
        for p in points:
            dist = (point - p).magnitude
            if dist <= max_dist and dist < min_dist:
                min_dist = dist
                nearest = entity
    
    return nearest

def get_polyline_length(entity):
    """폴리라인의 길이 계산"""
    points = get_polyline_points(entity)
    length = 0
    for i in range(len(points) - 1):
        length += (points[i + 1] - points[i]).magnitude
    return length

def process_dxf_file(filepath):
    """DXF 파일 처리"""
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()
    
    # 1. spoolno 레이어의 폴리라인 찾기 (S1)
    s1_polylines = []
    for entity in msp.query('POLYLINE LWPOLYLINE'):
        if entity.dxf.layer.lower() == 'spoolno':
            s1_polylines.append(entity)
    
    if not s1_polylines:
        print(f"No polylines found in 'spoolno' layer in {filepath}")
        return
    
    # 각 S1에 대한 정보 수집
    pt_values = set()
    s1_info = []
    used_texts = set()  # 중복 선택 방지를 위한 집합
    entities_to_delete = []  # 삭제할 엔티티들
    
    for s1 in s1_polylines:
        info = {'s1': s1, 'p1': None, 'pt': None, 'm1': None, 'pa': None, 'p1_text': None, 'pp': None, 'pt_text': None}
        
        # 2. PIPE 텍스트 찾기 (S1의 각 점에서 10mm 내에서 가장 가까운 것)
        pipe_text = find_nearest_text_from_points(msp, s1, 10, 'PIPE', used_texts)
        if pipe_text:
            # PA로 저장하고 CYAN 색상으로 변경
            info['pa'] = pipe_text
            info['pa'].dxf.color = 4  # CYAN
            used_texts.add(pipe_text)  # 사용된 텍스트로 표시
            
            # PIPE 값을 제외한 나머지를 PT로 저장
            pipe_text_content = pipe_text.dxf.text.upper()
            pt_value = pipe_text_content.replace('PIPE', '').strip()
            
            # PT 값이 없으면 PA 아래에서 찾기
            if not pt_value:
                pipe_pos = pipe_text.dxf.insert
                pt_texts = find_text_in_region(msp, pipe_pos[0], pipe_pos[1] - 7, 3, 3)
                if pt_texts:
                    pt_value = pt_texts[0].dxf.text.strip()
                    info['pt_text'] = pt_texts[0]  # PT 텍스트 엔티티 저장
                    # PT 텍스트를 CYAN으로 변경
                    pt_texts[0].dxf.color = 4  # CYAN
                    entities_to_delete.append(pt_texts[0])  # PT 텍스트 삭제 목록에 추가
            
            info['pt'] = pt_value if pt_value else None
            
            # PIPE 아래 영역에서 텍스트 찾기 (PP)
            pipe_pos = pipe_text.dxf.insert
            pp_texts = find_text_in_region(msp, pipe_pos[0], pipe_pos[1] - 7, 10, 3)
            
            if pp_texts:
                # PP 텍스트 중 MATL이 포함된 것이 있는지 확인
                matl_found = False
                for pp_text in pp_texts:
                    if 'MATL' in pp_text.dxf.text.upper():
                        info['pp'] = pp_text
                        info['m1'] = pp_text
                        pp_text.dxf.color = 4  # CYAN
                        matl_found = True
                        break
                
                # MATL이 없으면 PP = PT
                if not matl_found:
                    info['pp'] = info['pt']
            else:
                # PP 텍스트가 없으면 PP = PT
                info['pp'] = info['pt']
        
        else:
            # PIPE 텍스트를 찾지 못한 경우 - PA가 없으므로 PT를 찾을 수 없음
            info['pt'] = None
        
        # 5. 색상 변경 (CYAN = index 4)
        s1.dxf.color = 4
        
        # PA가 있는 경우에만 S1을 삭제 목록에 추가
        if info['pa']:
            entities_to_delete.append(s1)  # S1 삭제 목록에 추가
            # PA 삭제 목록에 추가
            entities_to_delete.append(info['pa'])
        
        # PT가 별도의 텍스트 엔티티인 경우 삭제 목록에 추가
        if info.get('pt_text'):
            entities_to_delete.append(info['pt_text'])
        
        # M1(MATL 텍스트)을 삭제 목록에 추가
        if info['m1'] and isinstance(info['m1'], object) and hasattr(info['m1'], 'dxf'):
            entities_to_delete.append(info['m1'])
        
        if info['pt']:
            pt_values.add(info['pt'])
        
        s1_info.append(info)
    
    # 6. PT 값 정렬 및 순번 매기기
    sorted_pt = sorted(list(pt_values))
    pt_to_sn = {pt: idx + 1 for idx, pt in enumerate(sorted_pt)}
    
    # 7. SN + PT 출력
    start_x, start_y = 630, 550
    for idx, pt in enumerate(sorted_pt):
        sn = idx + 1
        text = f"{sn} {pt}"
        msp.add_text(
            text,
            dxfattribs={
                'insert': (start_x, start_y - idx * 10),
                'height': 3.5,
                'color': 2  # YELLOW
            }
        )
    
    # 8-13. 각 S1에 대한 추가 처리
    used_ad3 = set()  # AD3 중복 선택 방지를 위한 집합
    
    for info in s1_info:
        s1 = info['s1']
        
        # PA가 없으면 AD3를 찾지 않음
        if not info['pa']:
            continue
            
        if not info['pt']:
            continue
        
        sn = pt_to_sn.get(info['pt'], 0)
        if sn == 0:
            continue
        
        # S1의 점들 가져오기
        s1_points = get_polyline_points(s1)
        if not s1_points:
            continue
        
        # AD3 찾기 (2-3점 폴리라인)
        ad3 = None
        s1_segments = get_polyline_segments(s1)
        
        # 먼저 1mm 이내에서 찾기
        for num_points in [2, 3]:
            for entity in msp.query('POLYLINE LWPOLYLINE'):
                # 이미 사용된 AD3는 건너뛰기
                if entity in used_ad3:
                    continue
                
                points = get_polyline_points(entity)
                if len(points) != num_points:
                    continue
                
                # AD3의 점이 S1 선분에서 1mm 이내에 있는지 확인
                found = False
                for ad3_point in points:
                    for seg_start, seg_end in s1_segments:
                        dist = point_to_segment_distance(ad3_point, seg_start, seg_end)
                        if dist <= 1:  # 1mm 이내
                            ad3 = entity
                            ad3.dxf.color = 1  # RED 색상으로 변경
                            used_ad3.add(entity)  # 사용된 AD3로 표시
                            entities_to_delete.append(ad3)  # AD3 삭제 목록에 추가
                            found = True
                            break
                    if found:
                        break
                
                if ad3:
                    break
            if ad3:
                break
        
        # 1mm 이내에서 못 찾았으면 10mm 이내에서 가장 가까운 것 찾기
        if not ad3:
            min_dist = float('inf')
            nearest_ad3 = None
            
            for num_points in [2, 3]:
                for entity in msp.query('POLYLINE LWPOLYLINE'):
                    # 이미 사용된 AD3는 건너뛰기
                    if entity in used_ad3:
                        continue
                    
                    points = get_polyline_points(entity)
                    if len(points) != num_points:
                        continue
                    
                    # AD3의 점과 S1 선분 사이의 최소 거리 계산
                    entity_min_dist = float('inf')
                    for ad3_point in points:
                        for seg_start, seg_end in s1_segments:
                            dist = point_to_segment_distance(ad3_point, seg_start, seg_end)
                            entity_min_dist = min(entity_min_dist, dist)
                    
                    # 10mm 이내이고 가장 가까운 것 선택
                    if entity_min_dist <= 10 and entity_min_dist < min_dist:
                        min_dist = entity_min_dist
                        nearest_ad3 = entity
            
            if nearest_ad3:
                ad3 = nearest_ad3
                ad3.dxf.color = 1  # RED 색상으로 변경
                used_ad3.add(ad3)  # 사용된 AD3로 표시
                entities_to_delete.append(ad3)  # AD3 삭제 목록에 추가
        
        if not ad3:
            continue
        
        # AD3의 점들 중 S1 선분에 가장 가까운 점(AP1)과 먼 점(AP2) 찾기
        ad3_points = get_polyline_points(ad3)
        if len(ad3_points) < 2:
            continue
        
        min_dist = float('inf')
        max_dist = 0
        ap1 = ap2 = None
        
        # 각 AD3 점과 S1 선분들 사이의 최소 거리 계산
        for ad3_point in ad3_points:
            min_dist_to_s1 = float('inf')
            for seg_start, seg_end in s1_segments:
                dist = point_to_segment_distance(ad3_point, seg_start, seg_end)
                min_dist_to_s1 = min(min_dist_to_s1, dist)
            
            if min_dist_to_s1 < min_dist:
                min_dist = min_dist_to_s1
                ap1 = ad3_point
            if min_dist_to_s1 > max_dist:
                max_dist = min_dist_to_s1
                ap2 = ad3_point
        
        if not ap2:
            continue
        
        # AD2 찾기 (2점 폴리라인, AP2에서 0.5mm 이내)
        ad2 = None
        for entity in msp.query('POLYLINE LWPOLYLINE'):
            # AD3로 이미 선택된 것은 제외
            if entity == ad3:
                continue
                
            points = get_polyline_points(entity)
            if len(points) != 2:
                continue
            
            length = get_polyline_length(entity)
            if length > 10:
                continue
            
            # 점간 거리가 2.3mm 이하는 제외
            if length <= 2.3:
                continue
            
            # AP2와 0.5mm 이내에 접하는 점이 있는지 확인
            has_close_point = False
            for p in points:
                if (p - ap2).magnitude <= 0.5:
                    has_close_point = True
                    break
            
            if has_close_point:
                ad2 = entity
                ad2.dxf.color = 2  # YELLOW 색상으로 변경
                break
        
        if not ad2:
            continue
        
        # AP3 찾기 (AP2에서 먼 AD2 점)
        ad2_points = get_polyline_points(ad2)
        if (ad2_points[0] - ap2).magnitude > (ad2_points[1] - ap2).magnitude:
            ap3 = ad2_points[0]
        else:
            ap3 = ad2_points[1]
        
        # SC (원) 그리기 - 반지름 4.1mm (지름 8.2mm)
        sc = msp.add_circle(
            center=(ap3.x, ap3.y),
            radius=4.1,
            dxfattribs={'color': 4}  # CYAN
        )
        
        # SC 이동
        ad2_length = get_polyline_length(ad2)
        move_dist = 4.1 + ad2_length
        direction = (ap2 - ap3).normalize()
        new_center = ap3 + direction * move_dist
        sc.dxf.center = (new_center.x, new_center.y)
        
        # SN 번호 텍스트 추가 (NODE 원과 동일한 방식)
        add_text_to_circle(msp, (new_center.x, new_center.y), str(sn), 3.5, 2, 'spoolno')
    
    # 파일 저장
    base_name = os.path.splitext(os.path.basename(filepath))[0]
    output_path = os.path.join(os.path.dirname(filepath), f"{base_name}_SPNO.dxf")
    
    # 삭제할 엔티티들 제거
    print(f"Deleting {len(entities_to_delete)} entities...")
    for entity in entities_to_delete:
        try:
            msp.delete_entity(entity)
        except Exception as e:
            print(f"Error deleting entity: {e}")
    
    doc.saveas(output_path)
    print(f"Saved: {output_path}")

def main():
    """메인 함수"""
    # 파일 선택 다이얼로그
    root = tk.Tk()
    root.withdraw()
    
    file_paths = filedialog.askopenfilenames(
        title="Select DXF files",
        filetypes=[("DXF files", "*.dxf"), ("All files", "*.*")]
    )
    
    if not file_paths:
        print("No files selected")
        return
    
    # 각 파일 처리
    for filepath in file_paths:
        try:
            print(f"Processing: {filepath}")
            process_dxf_file(filepath)
        except Exception as e:
            print(f"Error processing {filepath}: {str(e)}")

if __name__ == "__main__":
    main()