import ezdxf
from ezdxf.math import Vec2
import tkinter as tk
from tkinter import filedialog
import os
import math
from collections import defaultdict

def get_text_bounding_box_center(text_entity):
    """텍스트의 바운딩 박스 중심점 계산"""
    try:
        # 텍스트의 삽입점
        insert = Vec2(text_entity.dxf.insert)
        text = text_entity.dxf.text
        height = text_entity.dxf.height
        
        # 대략적인 텍스트 너비 계산 (문자당 높이의 0.7배로 추정)
        width = len(text) * height * 0.7
        
        # 텍스트 정렬에 따른 중심점 계산
        halign = text_entity.dxf.halign if hasattr(text_entity.dxf, 'halign') else 0
        valign = text_entity.dxf.valign if hasattr(text_entity.dxf, 'valign') else 0
        
        # 수평 중심
        if halign == 0:  # LEFT
            center_x = insert.x + width / 2
        elif halign == 1:  # CENTER
            center_x = insert.x
        elif halign == 2:  # RIGHT
            center_x = insert.x - width / 2
        else:
            center_x = insert.x + width / 2
            
        # 수직 중심
        if valign == 0:  # BASELINE
            center_y = insert.y + height / 2
        elif valign == 1:  # BOTTOM
            center_y = insert.y + height / 2
        elif valign == 2:  # MIDDLE
            center_y = insert.y
        elif valign == 3:  # TOP
            center_y = insert.y - height / 2
        else:
            center_y = insert.y + height / 2
            
        return Vec2(center_x, center_y)
    except:
        # 에러 시 삽입점 반환
        return Vec2(text_entity.dxf.insert)

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
        if entity in used_texts:
            continue
            
        if contains_text and contains_text.upper() not in entity.dxf.text.upper():
            continue
        
        text_pos = Vec2(entity.dxf.insert)
        
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
        text = msp.add_text(
            text_value,
            dxfattribs={
                'height': height,
                'color': color,
                'layer': layer,
                'insert': (0, 0, 0),
                'halign': 1,
                'valign': 2
            }
        )
        
        try:
            from ezdxf.math import Matrix44
            transform = Matrix44.translate(center[0], center[1], 0)
            text.transform(transform)
            return text
            
        except Exception as e:
            try:
                msp.delete_entity(text)
            except:
                pass
            
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

def parse_tinfo(text):
    """TINFO 텍스트를 파싱하여 I1~I9 추출"""
    values = []
    parts = text.split(':')
    
    for i in range(1, min(10, len(parts))):  # 최대 9개까지
        after_colon = parts[i].strip()
        # 공백까지 또는 전체 문자열 추출
        space_index = after_colon.find(' ')
        if space_index != -1:
            value = after_colon[:space_index]
        else:
            value = after_colon
        values.append(value)
    
    # 9개가 안되면 빈 문자열로 채우기
    while len(values) < 9:
        values.append('')
    
    return values

def find_line_entities(msp, x, y, dx, dy, min_length=None, max_length=None):
    """특정 영역 내의 LINE 엔티티 찾기"""
    lines = []
    for entity in msp.query('LINE'):
        start = Vec2(entity.dxf.start)
        end = Vec2(entity.dxf.end)
        mid = (start + end) / 2
        
        # 중점이 영역 내에 있는지 확인
        if (x - dx <= mid.x <= x + dx and 
            y - dy <= mid.y <= y + dy):
            
            length = (end - start).magnitude
            if min_length is not None and length < min_length:
                continue
            if max_length is not None and length > max_length:
                continue
                
            lines.append(entity)
    
    return lines

def extend_line_to_x(entity, target_x):
    """라인의 가까운 점을 특정 X 좌표까지 확장"""
    start = Vec2(entity.dxf.start)
    end = Vec2(entity.dxf.end)
    
    # 어느 점이 target_x에 더 가까운지 확인
    if abs(start.x - target_x) < abs(end.x - target_x):
        # start 점을 확장
        direction = (start - end).normalize()
        new_start = Vec2(target_x, start.y + direction.y * (target_x - start.x) / direction.x)
        entity.dxf.start = (new_start.x, new_start.y)
    else:
        # end 점을 확장
        direction = (end - start).normalize()
        new_end = Vec2(target_x, end.y + direction.y * (target_x - end.x) / direction.x)
        entity.dxf.end = (new_end.x, new_end.y)

def trim_line_to_y(entity, target_y):
    """수직선의 Y값이 작은 점을 특정 Y 좌표까지 트림"""
    start = Vec2(entity.dxf.start)
    end = Vec2(entity.dxf.end)
    
    # 수직선인지 확인
    if abs(start.x - end.x) > 0.1:
        return
    
    # Y값이 작은 점을 target_y로 설정
    if start.y < end.y:
        entity.dxf.start = (start.x, target_y)
    else:
        entity.dxf.end = (end.x, target_y)

def process_dxf_file(filepath):
    """DXF 파일 처리"""
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()
    
    # ===== 1차 작업 시작 =====
    print("Starting 1st phase...")
    
    # 1. X 20-30, Y 40-60 범위에서 Line: 포함 텍스트 찾기
    tinfo_candidates = []
    
    # 전체 영역에서 'Line:'으로 시작하는 텍스트 찾기
    for entity in msp.query('TEXT'):
        text_content = entity.dxf.text.strip()
        text_pos = entity.dxf.insert
        
        # 'Line:'으로 시작하고 X 범위 내에 있는 텍스트
        if text_content.startswith('Line:') and 20 <= text_pos[0] <= 30:
            tinfo_candidates.append({
                'entity': entity,
                'text': text_content,
                'position': Vec2(text_pos),
                'y': text_pos[1]
            })
    
    # Y 좌표로 내림차순 정렬 (위에서 아래로)
    tinfo_candidates.sort(key=lambda x: x['y'], reverse=True)
    
    # 중복 제거 및 최종 리스트 생성
    tinfo_list = []
    seen_texts = set()
    
    for candidate in tinfo_candidates:
        # 동일한 텍스트 내용은 중복으로 처리하지 않음
        if candidate['text'] not in seen_texts:
            tinfo_list.append(candidate)
            seen_texts.add(candidate['text'])
            print(f"Found unique TINFO at Y={candidate['y']:.1f}: {candidate['text'][:50]}...")
    
    print(f"Total unique TINFO found: {len(tinfo_list)}")
    
    # TNO 번호 부여 및 I1~I9 파싱
    tno_data = {}
    for idx, tinfo in enumerate(tinfo_list):
        tno = idx + 1
        i_values = parse_tinfo(tinfo['text'])
        tno_data[tno] = {
            'tinfo': tinfo,
            'i_values': i_values,  # [I1, I2, ..., I9]
        }
        print(f"TNO {tno}: {i_values}")
    
    print(f"Total TNO count: {len(tno_data)}")
    
    # 2. X541 Y548 위치에서 시작하여 '00' 값을 I1~I9로 교체
    tolerance = 3
    max_tno = len(tno_data)  # TNO 개수
    
    print(f"\nProcessing I1~I9 replacement for {max_tno} TNOs...")
    
    for tno in range(1, max_tno + 1):
        if tno not in tno_data:
            continue
            
        data = tno_data[tno]
        
        # TNO의 예상 Y 위치 계산
        expected_y = 548 - (tno - 1) * 10
        
        # 해당 Y 위치에서 '00' 텍스트들 찾기
        zero_texts = []
        for entity in msp.query('TEXT'):
            if entity.dxf.text == '00':
                text_pos = entity.dxf.insert
                if abs(text_pos[1] - expected_y) < tolerance and text_pos[0] > 541:
                    zero_texts.append({
                        'entity': entity,
                        'x': text_pos[0]
                    })
        
        if not zero_texts:
            print(f"TNO {tno}: No '00' texts found at Y={expected_y}")
            continue
        
        # X 좌표로 정렬
        zero_texts.sort(key=lambda z: z['x'])
        
        print(f"TNO {tno}: Found {len(zero_texts)} '00' texts at Y={expected_y}")
        
        # I1~I9 값으로 순차적으로 교체
        replaced_count = 0
        for i in range(min(9, len(zero_texts))):
            if i < len(data['i_values']) and data['i_values'][i]:
                zero_texts[i]['entity'].dxf.text = data['i_values'][i]
                zero_texts[i]['entity'].dxf.color = 2  # YELLOW
                replaced_count += 1
                print(f"  - Replaced '00' at X={zero_texts[i]['x']:.1f} with I{i+1}='{data['i_values'][i]}'")
        
        print(f"TNO {tno}: Replaced {replaced_count} values")
    
    print(f"\nCompleted I1~I9 replacement for {max_tno} TNOs")
    
    # 3. TNO 이후의 숫자 1-10 찾아서 DELNO로 저장
    max_tno = len(tno_data)
    last_tno_y = 548 - (max_tno - 1) * 10  # 마지막 TNO의 Y 위치
    
    print(f"\nSearching for DELNO after TNO (Y < {last_tno_y - 5})...")
    
    delno_list = []
    for i in range(1, 11):
        for entity in msp.query('TEXT'):
            if entity.dxf.text == str(i):
                text_pos = entity.dxf.insert
                # TNO 이후 (아래쪽)의 숫자만 선택
                if text_pos[1] < last_tno_y - 5:  # 5mm 여유
                    # X 위치도 확인 (대략 TNO와 비슷한 X 범위)
                    if 530 <= text_pos[0] <= 560:
                        delno_list.append({
                            'number': i,
                            'entity': entity,
                            'position': Vec2(text_pos)
                        })
                        print(f"Found DELNO {i} at ({text_pos[0]:.1f}, {text_pos[1]:.1f})")
    
    print(f"Found {len(delno_list)} DELNO entries after TNO")
    
    # 4. DELNO 중심 10mm 내 8mm CYAN 원 찾기 (DELC)
    entities_to_delete = []
    
    for delno in delno_list:
        center = delno['position']
        
        # 원 찾기
        for entity in msp.query('CIRCLE'):
            circle_center = Vec2(entity.dxf.center)
            if (circle_center - center).magnitude <= 10 and abs(entity.dxf.radius - 4) < 0.5:
                if entity.dxf.color == 4:  # CYAN
                    entities_to_delete.append(entity)
        
        # DELNO +X 방향 '00' 찾기 (DEL0)
        for entity in msp.query('TEXT'):
            if entity.dxf.text == '00':
                text_pos = Vec2(entity.dxf.insert)
                if text_pos.x > center.x and abs(text_pos.y - center.y) < tolerance:
                    entities_to_delete.append(entity)
        
        # DELNO 자체도 삭제 목록에 추가
        entities_to_delete.append(delno['entity'])
    
    # 5. 가장 큰 TNO 근처에서 FL 찾기
    if tno_data:
        max_tno = max(tno_data.keys())
        max_tno_pos = tno_data[max_tno]['tinfo']['position']
        
        # FL 찾기 (260-270mm 선) - TNO 위치에서 -Y 5~7mm, +X 5~7mm 범위
        fl_lines = []
        for entity in msp.query('LINE'):
            start = Vec2(entity.dxf.start)
            end = Vec2(entity.dxf.end)
            
            # 선의 어느 한 점이라도 범위 내에 있는지 확인
            for point in [start, end]:
                if (max_tno_pos.x + 5 <= point.x <= max_tno_pos.x + 7 and
                    max_tno_pos.y - 7 <= point.y <= max_tno_pos.y - 5):
                    
                    length = (end - start).magnitude
                    if 260 <= length <= 270:
                        fl_lines.append(entity)
                        break
        
        if fl_lines:
            fl = fl_lines[0]
            extend_line_to_x(fl, 506)
            fl_y = fl.dxf.start[1]  # FL의 Y 좌표
            
            # 6. DELNO 아래 영역의 선 처리
            for delno in delno_list:
                center = delno['position']
                
                # 120mm 이상 선 찾기
                lines = find_line_entities(msp, 
                                         center.x, 
                                         center.y - 22.5, 
                                         50, 17.5, 
                                         min_length=120)
                
                for line in lines:
                    length = get_polyline_length(line)
                    
                    if length >= 200:
                        entities_to_delete.append(line)
                    elif abs(length - 123) < 0.5:
                        # 수직선인지 확인
                        start = Vec2(line.dxf.start)
                        end = Vec2(line.dxf.end)
                        if abs(start.x - end.x) < 0.1:
                            trim_line_to_y(line, fl_y)
    
    # ===== 2차 작업 시작 =====
    print("Starting 2nd phase...")
    
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
    used_texts = set()
    
    for s1 in s1_polylines:
        info = {'s1': s1, 'p1': None, 'pt': None, 'm1': None, 'pa': None, 'p1_text': None, 'pp': None, 'pt_text': None}
        
        # PIPE 텍스트 찾기
        pipe_text = find_nearest_text_from_points(msp, s1, 10, 'PIPE', used_texts)
        if pipe_text:
            info['pa'] = pipe_text
            info['pa'].dxf.color = 4  # CYAN
            used_texts.add(pipe_text)
            
            pipe_text_content = pipe_text.dxf.text.upper()
            pt_value = pipe_text_content.replace('PIPE', '').strip()
            
            if not pt_value:
                pipe_pos = pipe_text.dxf.insert
                pt_texts = find_text_in_region(msp, pipe_pos[0], pipe_pos[1] - 7, 3, 3)
                if pt_texts:
                    pt_value = pt_texts[0].dxf.text.strip()
                    info['pt_text'] = pt_texts[0]
                    pt_texts[0].dxf.color = 4
                    entities_to_delete.append(pt_texts[0])
            
            info['pt'] = pt_value if pt_value else None
            
            # PP 처리
            pipe_pos = pipe_text.dxf.insert
            pp_texts = find_text_in_region(msp, pipe_pos[0], pipe_pos[1] - 7, 10, 3)
            
            if pp_texts:
                matl_found = False
                for pp_text in pp_texts:
                    if 'MATL' in pp_text.dxf.text.upper():
                        info['pp'] = pp_text
                        info['m1'] = pp_text
                        pp_text.dxf.color = 4
                        matl_found = True
                        break
                
                if not matl_found:
                    info['pp'] = info['pt']
            else:
                info['pp'] = info['pt']
        
        s1.dxf.color = 4
        
        if info['pa']:
            entities_to_delete.append(s1)
            entities_to_delete.append(info['pa'])
        
        if info['m1'] and isinstance(info['m1'], object) and hasattr(info['m1'], 'dxf'):
            entities_to_delete.append(info['m1'])
        
        if info['pt']:
            pt_values.add(info['pt'])
        
        s1_info.append(info)
    
    # PT와 I1 비교하여 SN 결정
    for info in s1_info:
        if not info['pt']:
            continue
        
        # I1과 매칭되는 TNO 찾기
        matching_tno = None
        for tno, data in tno_data.items():
            if data['i_values'][0] == info['pt']:  # I1과 비교
                matching_tno = tno
                break
        
        info['sn'] = matching_tno if matching_tno else 0
    
    # X630 Y550의 텍스트 삭제 (이미 생성하지 않음)
    
    # 나머지 2차 작업 처리
    used_ad3 = set()
    
    for info in s1_info:
        s1 = info['s1']
        
        if not info['pa'] or not info['pt'] or info['sn'] == 0:
            continue
        
        sn = info['sn']
        
        s1_points = get_polyline_points(s1)
        if not s1_points:
            continue
        
        # AD3 찾기
        ad3 = None
        s1_segments = get_polyline_segments(s1)
        
        for num_points in [2, 3]:
            for entity in msp.query('POLYLINE LWPOLYLINE'):
                if entity in used_ad3:
                    continue
                
                points = get_polyline_points(entity)
                if len(points) != num_points:
                    continue
                
                found = False
                for ad3_point in points:
                    for seg_start, seg_end in s1_segments:
                        dist = point_to_segment_distance(ad3_point, seg_start, seg_end)
                        if dist <= 1:
                            ad3 = entity
                            ad3.dxf.color = 1
                            used_ad3.add(entity)
                            entities_to_delete.append(ad3)
                            found = True
                            break
                    if found:
                        break
                
                if ad3:
                    break
            if ad3:
                break
        
        if not ad3:
            min_dist = float('inf')
            nearest_ad3 = None
            
            for num_points in [2, 3]:
                for entity in msp.query('POLYLINE LWPOLYLINE'):
                    if entity in used_ad3:
                        continue
                    
                    points = get_polyline_points(entity)
                    if len(points) != num_points:
                        continue
                    
                    entity_min_dist = float('inf')
                    for ad3_point in points:
                        for seg_start, seg_end in s1_segments:
                            dist = point_to_segment_distance(ad3_point, seg_start, seg_end)
                            entity_min_dist = min(entity_min_dist, dist)
                    
                    if entity_min_dist <= 10 and entity_min_dist < min_dist:
                        min_dist = entity_min_dist
                        nearest_ad3 = entity
            
            if nearest_ad3:
                ad3 = nearest_ad3
                ad3.dxf.color = 1
                used_ad3.add(ad3)
                entities_to_delete.append(ad3)
        
        if not ad3:
            continue
        
        # AP1, AP2 찾기
        ad3_points = get_polyline_points(ad3)
        if len(ad3_points) < 2:
            continue
        
        min_dist = float('inf')
        max_dist = 0
        ap1 = ap2 = None
        
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
        
        # AD2 찾기
        ad2 = None
        for entity in msp.query('POLYLINE LWPOLYLINE'):
            if entity == ad3:
                continue
                
            points = get_polyline_points(entity)
            if len(points) != 2:
                continue
            
            length = get_polyline_length(entity)
            if length > 10 or length <= 2.3:
                continue
            
            has_close_point = False
            for p in points:
                if (p - ap2).magnitude <= 0.5:
                    has_close_point = True
                    break
            
            if has_close_point:
                ad2 = entity
                ad2.dxf.color = 2
                break
        
        if not ad2:
            continue
        
        # AP3 찾기
        ad2_points = get_polyline_points(ad2)
        if (ad2_points[0] - ap2).magnitude > (ad2_points[1] - ap2).magnitude:
            ap3 = ad2_points[0]
        else:
            ap3 = ad2_points[1]
        
        # SC 원 그리기
        sc = msp.add_circle(
            center=(ap3.x, ap3.y),
            radius=4.1,
            dxfattribs={'color': 4}
        )
        
        # SC 이동
        ad2_length = get_polyline_length(ad2)
        move_dist = 4.1 + ad2_length
        direction = (ap2 - ap3).normalize()
        new_center = ap3 + direction * move_dist
        sc.dxf.center = (new_center.x, new_center.y)
        
        # SN 번호 텍스트 추가
        add_text_to_circle(msp, (new_center.x, new_center.y), str(sn), 3.5, 2, 'spoolno')
    
    # 엔티티 삭제
    print(f"\n=== Summary ===")
    print(f"TNO count: {len(tno_data)}")
    print(f"DELNO to delete: {len(delno_list)}")
    print(f"Total entities to delete: {len(entities_to_delete)}")
    
    for entity in entities_to_delete:
        try:
            msp.delete_entity(entity)
        except Exception as e:
            print(f"Error deleting entity: {e}")
    
    # 파일 저장
    base_name = os.path.splitext(os.path.basename(filepath))[0]
    output_path = os.path.join(os.path.dirname(filepath), f"{base_name}_SPNO.dxf")
    doc.saveas(output_path)
    print(f"Saved: {output_path}")

def main():
    """메인 함수"""
    root = tk.Tk()
    root.withdraw()
    
    file_paths = filedialog.askopenfilenames(
        title="Select DXF files",
        filetypes=[("DXF files", "*.dxf"), ("All files", "*.*")]
    )
    
    if not file_paths:
        print("No files selected")
        return
    
    for filepath in file_paths:
        try:
            print(f"Processing: {filepath}")
            process_dxf_file(filepath)
        except Exception as e:
            print(f"Error processing {filepath}: {str(e)}")

if __name__ == "__main__":
    main()