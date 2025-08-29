import ezdxf
from ezdxf.math import Vec2
import tkinter as tk
from tkinter import filedialog
import os
import math
from collections import defaultdict
import re

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
                'style': 'ARIAL',
                'height': height,
                'color': color,
                'layer': layer,
                'width': 0.85,  # 폭 비율 0.85
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
                    'style': 'ARIAL',
                    'height': height,
                    'color': color,
                    'layer': layer,
                    'width': 0.85,  # 폭 비율 0.85
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
                    'style': 'ARIAL',
                    'height': height,
                    'color': color,
                    'layer': layer,
                    'width': 0.85,  # 폭 비율 0.85
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

def find_tinfo_texts(msp):
    """TINFO 텍스트 찾기 및 파싱"""
    tinfo_list = []
    
    print("\n=== Searching for TINFO texts ===")
    # X 20~30, Y 40~60 범위에서 'Line:' 포함 텍스트 모두 찾기
    initial_tinfos = []
    for entity in msp.query('TEXT'):
        text_pos = entity.dxf.insert
        text_content = entity.dxf.text
        
        # 디버깅: 범위 내 모든 텍스트 확인
        if 20 <= text_pos[0] <= 30 and 5 <= text_pos[1] <= 150:
            print(f"Found text at X={text_pos[0]}, Y={text_pos[1]}: {text_content[:50]}...")
            
            # 'Line:' 포함 여부 확인
            if 'Line:' in text_content:
                print(f"*** TINFO found at X={text_pos[0]}, Y={text_pos[1]}")
                initial_tinfos.append(entity)
    
    # Y값으로 내림차순 정렬 (가장 높은 것부터)
    if initial_tinfos:
        initial_tinfos.sort(key=lambda e: e.dxf.insert[1], reverse=True)
        tinfo_list.append(initial_tinfos[0])  # 가장 높은 것을 첫 번째로
        print(f"Starting from highest TINFO at Y={initial_tinfos[0].dxf.insert[1]}")
    
    if not tinfo_list:
        print("No TINFO found in initial search!")
        return []
    
    # Y -6mm 간격으로 계속 찾기
    if tinfo_list:
        current_y = tinfo_list[0].dxf.insert[1]
        while current_y > 0:
            current_y -= 6  # 6mm 간격
            for entity in msp.query('TEXT'):
                text_pos = entity.dxf.insert
                if (20 <= text_pos[0] <= 30 and 
                    current_y - 3 <= text_pos[1] <= current_y + 3 and  # 허용 범위 ±3mm
                    'Line:' in entity.dxf.text and
                    entity not in tinfo_list):
                    tinfo_list.append(entity)
                    break
    
    # TINFO 파싱
    tinfo_data = []
    for idx, tinfo in enumerate(tinfo_list):
        tno = idx + 1
        text = tinfo.dxf.text
        print(f"TINFO {tno}: {text}")  # 디버깅용
        
        # ':' 구분자로 파싱 - 개선된 로직
        i_values = []
        
        # 먼저 "Line:" 이후의 텍스트만 가져오기
        line_pos = text.find('Line:')
        if line_pos != -1:
            remaining_text = text[line_pos + 5:].strip()  # "Line:" 이후 텍스트
            
            # 첫 번째 값은 공백 전까지
            space_pos = remaining_text.find(' ')
            if space_pos != -1:
                i_values.append(remaining_text[:space_pos].strip())
                remaining_text = remaining_text[space_pos:].strip()
            else:
                i_values.append(remaining_text.strip())
                remaining_text = ""
            
            # 나머지는 패턴으로 파싱 (KEY:VALUE 형식)
            if remaining_text:
                pattern = r'(\w+):\s*([^\s]+(?:\s*\([^)]*\))?)'
                matches = re.findall(pattern, remaining_text)
                
                for key, value in matches:
                    i_values.append(value.strip())
                    print(f"  {key}: {value.strip()}")  # 디버깅용
        
        # I1~I9까지 채우기 (없으면 빈 문자열)
        while len(i_values) < 9:
            i_values.append('')
        
        tinfo_data.append({
            'tno': tno,
            'i_values': i_values,
            'text_entity': tinfo
        })
    
    return tinfo_data

def add_pipe_specification_texts(msp):
    """PIPE SPECIFICATION 관련 텍스트 추가"""
    # I1~I9와 동일한 방식으로 텍스트 추가
    texts = [
        (510, 578, '* PIPE SPECIFICATION'),
        (575, 562, 'LINE NO.'),
        (636, 568.8, 'DESIGN'),
        (670.7, 568.8, 'OPERATING'),
        (737.6, 568.8, 'PIPE'),
        (789.4, 568.8, 'INSULATION'),
        (627.2, 560, 'PRESS'),
        (648.8, 560, 'TEMP'),
        (667.2, 560, 'PRESS'),
        (688.8, 560, 'TEMP'),
        (627, 554.8, '(BARG)'),
        (651.4, 554.8, '(°C)'),
        (667, 554.8, '(BARG)'),
        (691.4, 554.8, '(°C)'),
        (710, 557.3, 'MATERIAL'),
        (745.2, 557.3, 'SIZE'),
        (765.2, 557.3, 'SCH'),
        (783.2, 557.3, 'THICK'),
        (803, 557.3, 'MATERIAL')
    ]
    
        # I1~I9와 동일한 속성으로 텍스트 생성
    for x, y, text in texts:
        msp.add_text(
            text,
            dxfattribs={
                'style': 'ARIAL',
                'height': 4.3,
                'color': 2,  # YELLOW
                'width': 0.85,  # 폭 비율
                'insert': (x, y, 0),
                'layer': 'default'
                # halign, valign 제거 (DDEDIT 문제 방지)
            }
        )
def add_grid_lines(msp):
    """격자선 추가"""
    # H 선들
    h_lines = [
        ('H1', 831, 576, 506, 576),
        ('H2', 831, 566, 626, 566),
        ('H3', 831, 553, 506, 553),
        ('H4', 801, 543, 536, 543)
    ]
    
    for layer, x1, y1, x2, y2 in h_lines:
        msp.add_line(
            (x1, y1),
            (x2, y2),
            dxfattribs={'layer': layer}
        )
    
    # V 선들
    v_lines = [
        ('V1', 506, 576, 506, 453),
        ('V2', 536, 553, 536, 453),
        ('V6', 646, 566, 646, 453)
    ]
    
    for layer, x1, y1, x2, y2 in v_lines:
        msp.add_line(
            (x1, y1),
            (x2, y2),
            dxfattribs={'layer': layer}
        )
    
    # V1 복사
    v1_copies = [
        ('V3', 40),
        ('V4', 120),
        ('V5', 160),
        ('V7', 200),
        ('V9', 275)
    ]
    
    for layer, offset in v1_copies:
        msp.add_line(
            (506 + offset, 576),
            (506 + offset, 453),
            dxfattribs={'layer': layer}
        )
    
    # V6 복사
    v6_copies = [
        ('V8', 40),
        ('V10', 95),
        ('V11', 115),
        ('V12', 155)  # 수정: V11이 두 번 나와서 V12로 변경
    ]
    
    for layer, offset in v6_copies:
        msp.add_line(
            (646 + offset, 566),
            (646 + offset, 453),
            dxfattribs={'layer': layer}
        )
    
    return h_lines, v_lines, v1_copies, v6_copies

def process_dxf_file(filepath):
    """DXF 파일 처리"""
    print(f"\n=== Processing DXF file: {filepath} ===")
    doc = ezdxf.readfile(filepath)
    msp = doc.modelspace()
    
    # ARIAL 스타일 확인 및 생성 (최대한 간단하게)
    print("Checking text styles...")
    try:
        # ARIAL 스타일 생성 시도
        if 'ARIAL' not in doc.styles:
            doc.styles.new('ARIAL')
            print("ARIAL style created")
        else:
            print("ARIAL style already exists")
    except Exception as e:
        print(f"Style handling error (will use default): {e}")
    
    # 모든 TEXT 엔티티 개수 확인
    text_count = len(list(msp.query('TEXT')))
    print(f"Total TEXT entities in file: {text_count}")
    
    # 1차 작업: TINFO 찾기
    tinfo_data = find_tinfo_texts(msp)
    print(f"\nTotal TINFO found: {len(tinfo_data)}")
    
    if not tinfo_data:
        print("WARNING: No TINFO texts found!")
        return
    
    # 2차 작업을 먼저 수행하여 SN 매칭 정보 얻기
    s1_polylines = []
    for entity in msp.query('POLYLINE LWPOLYLINE'):
        if entity.dxf.layer.lower() == 'spoolno':
            s1_polylines.append(entity)
    
    # SN이 매칭된 TNO들을 저장할 집합
    matched_tnos = set()
    s1_info = []
    entities_to_delete = []  # 삭제할 엔티티 목록
    used_ad3 = set()  # 사용된 AD3 추적
    
    if s1_polylines:
        # I1 값을 TNO에 매핑하는 딕셔너리 생성
        i1_to_tno = {}
        print("\n=== TNO-I1 Mapping ===")
        for data in tinfo_data:
            if data['i_values'][0]:  # I1 값이 있으면
                i1_to_tno[data['i_values'][0]] = data['tno']
                print(f"TNO {data['tno']}: I1 = {data['i_values'][0]}")
        print("===================\n")
        
        # 각 S1에 대한 정보 수집
        used_texts = set()
        
        for idx, s1 in enumerate(s1_polylines):
            info = {'s1': s1, 'p1': None, 'pt': None, 'm1': None, 'pa': None, 'p1_text': None, 'pp': None, 'pt_text': None, 'sn': None}
            
            # PIPE 텍스트 찾기
            pipe_text = find_nearest_text_from_points(msp, s1, 10, 'PIPE', used_texts)
            if pipe_text:
                info['pa'] = pipe_text
                used_texts.add(pipe_text)
                
                # PIPE 값을 제외한 나머지를 PT로 저장
                pipe_text_content = pipe_text.dxf.text.upper()
                pt_value = pipe_text_content.replace('PIPE', '').strip()
                
                # PT 값이 없으면 PA 아래에서 찾기
                if not pt_value:
                    pipe_pos = pipe_text.dxf.insert
                    pt_texts = find_text_in_region(msp, pipe_pos[0], pipe_pos[1] - 7, 3, 3)
                    if pt_texts:
                        pt_value = pt_texts[0].dxf.text.strip()
                        info['pt_text'] = pt_texts[0]
                
                info['pt'] = pt_value if pt_value else None
                
                # LINENO 찾기 - PT 값을 LINENO로 사용
                lineno = info['pt']
                print(f"S1 #{idx+1}: LINENO(PT) = {lineno}")
                if lineno and lineno in i1_to_tno:
                    info['sn'] = i1_to_tno[lineno]
                    matched_tnos.add(info['sn'])  # 매칭된 TNO 저장
                    print(f"  → Matched to TNO {info['sn']}")
                    
                    # SN이 있는 경우에만 색상 변경 및 삭제 목록에 추가
                    info['pa'].dxf.color = 4  # CYAN
                    s1.dxf.color = 4
                    entities_to_delete.append(s1)
                    entities_to_delete.append(info['pa'])
                    
                    if info.get('pt_text'):
                        info['pt_text'].dxf.color = 4  # CYAN
                        entities_to_delete.append(info['pt_text'])
                else:
                    print(f"  → No match found in I1 values")
                
                # PIPE 아래 영역에서 텍스트 찾기 (PP)
                pipe_pos = pipe_text.dxf.insert
                pp_texts = find_text_in_region(msp, pipe_pos[0], pipe_pos[1] - 7, 10, 3)
                
                if pp_texts:
                    matl_found = False
                    for pp_text in pp_texts:
                        if 'MATL' in pp_text.dxf.text.upper():
                            info['pp'] = pp_text
                            info['m1'] = pp_text
                            # SN이 있는 경우에만 색상 변경 및 삭제 목록에 추가
                            if info['sn']:
                                pp_text.dxf.color = 4  # CYAN
                                entities_to_delete.append(pp_text)
                            matl_found = True
                            break
                    
                    if not matl_found:
                        info['pp'] = info['pt']
                else:
                    info['pp'] = info['pt']
            
            s1_info.append(info)
    
    # PIPE SPECIFICATION 텍스트 추가
    add_pipe_specification_texts(msp)
    
    # 격자선 추가
    h_lines, v_lines, v1_copies, v6_copies = add_grid_lines(msp)
    
    # SN 매칭 여부에 따른 출력 결정
    # matched_tnos가 비어있으면 모든 TNO 출력, 아니면 매칭된 것만 출력
    output_all_tnos = len(matched_tnos) == 0
    
    if output_all_tnos:
        print("\nNo SN matches found - outputting all TNOs")
    else:
        print(f"\nSN matches found - outputting {len(matched_tnos)} TNOs with SN")
    
    output_tno_count = 0
    for data in tinfo_data:
        tno = data['tno']
        
        # SN 매칭이 없으면 모든 TNO 출력, 있으면 매칭된 것만 출력
        if not output_all_tnos and tno not in matched_tnos:
            continue
            
        output_tno_count += 1
        i_values = data['i_values']
        y_offset = (output_tno_count - 1) * 10  # 출력된 TNO 순서대로 Y 오프셋 계산
        
        # TNO 원과 텍스트
        circle = msp.add_circle(
            center=(541, 548 - y_offset),
            radius=4,  # 지름 8mm = 반지름 4mm
            dxfattribs={'color': 4}  # CYAN
        )
        
        # TNO 텍스트를 add_text_to_circle 함수를 사용하여 원 중심에 추가
        tno_text = add_text_to_circle(
            msp=msp,
            center=(541, 548 - y_offset),
            text_value=str(tno),
            height=4.3,
            color=2,  # YELLOW
            layer='default'
        )
        
        # I1~I9 출력 (위치 조정됨 - DDEDIT 안정성을 위해 기본 설정 사용)
        i_positions = [
            (553, 545.8),         # I1 (변경 없음)
            (631.5, 545.8),         # I2 (변경 없음)
            (650.5, 545.8),       # I3 (653 - 2.5)
            (670.5, 545.8),       # I4 (673 - 2.5)
            (690.5, 545.8),       # I5 (693 - 2.5)
            (713, 545.8),         # I6 (720 - 7)
            (746.5, 545.8),       # I7 (748 - 1.5)
            (765.5, 545.8),       # I8 (768 - 2.5)
            (785.5, 545.8)        # I9 (788 - 2.5)
        ]
        
        for i, (x, y) in enumerate(i_positions):
            if i < len(i_values) and i_values[i]:
                # 가장 단순한 텍스트 생성 방법 사용
                msp.add_text(
                    i_values[i],
                    dxfattribs={
                         'style': 'ARIAL',  # 추가
                         'height': 4.3,
                         'color': 2,  # YELLOW
                         'width': 0.85,  # 추가
                         'insert': (x, y - y_offset, 0),
                         'layer': 'default'
                    }
                )
    
    print(f"\nOutput TNO count: {output_tno_count}")
    
    # H4 복사 및 HF 처리 - output_tno_count가 1인 경우도 처리
    if output_tno_count >= 1:
        # output_tno_count가 1이면 H4 복사 없이 바로 HF 생성
        # output_tno_count가 2 이상이면 H4 복사 후 HF 생성
        
        if output_tno_count > 1:
            # H4를 output_tno_count-1개 만큼 -Y 10mm로 이동 복사
            for i in range(1, output_tno_count):
                layer_name = f'H4_{i}'
                msp.add_line(
                    (801, 543 - i * 10),
                    (536, 543 - i * 10),
                    dxfattribs={'layer': layer_name}
                )
        
        # HF 생성 (output_tno_count가 1이면 H4 위치에, 2 이상이면 마지막 H4 위치에)
        hf_y = 543 - (output_tno_count - 1) * 10
        msp.add_line(
            (831, hf_y),  # 801 -> 831로 확장
            (506, hf_y),  # 536 -> 506으로 확장
            dxfattribs={'layer': 'HF'}
        )
        
        # 모든 V선의 Y 453 값을 HF의 Y값으로 변경
        # 기존 V선 삭제하고 새로 그리기
        # V1~V12의 시작 X 좌표 계산
        v_lines_new = [
            ('V1', 506),
            ('V2', 536),
            ('V3', 546),
            ('V4', 626),
            ('V5', 666),
            ('V6', 646),
            ('V7', 706),
            ('V8', 686),
            ('V9', 781),
            ('V10', 741),
            ('V11', 761),
            ('V12', 801)
        ]
        
        for layer, x in v_lines_new:
            # 기존 선 찾아서 삭제
            for entity in list(msp.query('LINE')):
                if hasattr(entity.dxf, 'layer') and entity.dxf.layer == layer:
                    start = entity.dxf.start
                    end = entity.dxf.end
                    if abs(end[1] - 453) < 0.1:  # Y값이 453인 선
                        msp.delete_entity(entity)
                        # 새로운 선 추가
                        msp.add_line(
                            (start[0], start[1]),
                            (start[0], hf_y),
                            dxfattribs={'layer': layer}
                        )
                        break
    
    # 2차 작업: SN이 있는 S1에 대한 추가 처리
    if s1_polylines:
        print(f"\n=== Processing S1 with SN ===")
        processed_count = 0
        
        for info in s1_info:
            s1 = info['s1']
            sn = info.get('sn')
            
            # SN이 없거나 PA가 없으면 건너뛰기
            if not sn or not info['pa']:
                if not sn:
                    print(f"S1 skipped - No SN assigned (PT={info.get('pt')})")
                if not info['pa']:
                    print(f"S1 skipped - No PA found")
                continue
            
            processed_count += 1
            print(f"\nProcessing S1 with SN={sn}")
            
            # S1의 점들 가져오기
            s1_points = get_polyline_points(s1)
            if not s1_points:
                continue
            
            # AD3 찾기 (이하 기존 코드와 동일)
            ad3 = None
            s1_segments = get_polyline_segments(s1)
            
            # 먼저 1mm 이내에서 찾기
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
                                ad3.dxf.color = 1  # RED
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
            
            # 1mm 이내에서 못 찾았으면 10mm 이내에서 찾기
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
                    ad3.dxf.color = 1  # RED
                    used_ad3.add(ad3)
                    entities_to_delete.append(ad3)
            
            if not ad3:
                continue
            
            # AD3의 점들 중 AP1, AP2 찾기
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
                    ad2.dxf.color = 2  # YELLOW
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
                dxfattribs={'color': 4}  # CYAN
            )
            
            # SC 이동
            ad2_length = get_polyline_length(ad2)
            move_dist = 4.1 + ad2_length
            direction = (ap2 - ap3).normalize()
            new_center = ap3 + direction * move_dist
            sc.dxf.center = (new_center.x, new_center.y)
            
            # SN 번호 텍스트를 add_text_to_circle 함수를 사용하여 원 중심에 추가
            sn_text = add_text_to_circle(
                msp=msp,
                center=(new_center.x, new_center.y),
                text_value=str(sn),
                height=4.3,
                color=2,  # YELLOW
                layer='spoolno'
            )
        
        print(f"\nTotal S1 processed with SN: {processed_count}")
    else:
        print(f"No polylines found in 'spoolno' layer in {filepath}")
    
    # 파일 저장 전에 추가 작업 수행
    print("\n=== Additional Processing ===")
    
    # x 738 y 14 위치(공차 ±5mm)에서 '_'가 포함된 텍스트 찾기
    sat_text = None
    print("\n=== Searching for SAT text ===")
    print("Looking for text with '_' in range X=733-743, Y=9-19")
    
    # 범위 내의 모든 텍스트 확인
    found_count = 0
    for entity in msp.query('TEXT'):
        text_pos = entity.dxf.insert
        # 범위를 조금 더 넓게 설정 (±10)
        if (728 <= text_pos[0] <= 748 and  # 738 ± 10
            4 <= text_pos[1] <= 24):        # 14 ± 10
            found_count += 1
            distance = ((text_pos[0] - 738)**2 + (text_pos[1] - 14)**2)**0.5
            print(f"  Text near target: X={text_pos[0]:.1f}, Y={text_pos[1]:.1f}, Distance={distance:.1f}, Content: {entity.dxf.text[:30]}...")
            
            # 정확한 위치 확인
            if (733 <= text_pos[0] <= 743 and 9 <= text_pos[1] <= 19):
                if '_' in entity.dxf.text:
                    sat_text = entity
                    print(f"  *** EXACT MATCH - Selected as SAT!")
                    break
    
    if found_count == 0:
        print("  No text found in the specified range!")
    elif not sat_text:
        print("  Text found but none contains '_'")
    
    if sat_text:
        # 텍스트 내의 숫자 이후의 텍스트 찾기
        text_content = sat_text.dxf.text
        print(f"\nProcessing SAT text: {text_content}")
        
        # 숫자 이후의 텍스트 추출
        print(f"Original text: {text_content}")
        
        # 연속된 숫자들을 찾고 마지막 숫자 그룹 이후부터 추출
        import re
        # 숫자 그룹들을 찾기
        digit_pattern = r'\d+'
        matches = list(re.finditer(digit_pattern, text_content))
        
        if matches:
            # 마지막 숫자 그룹의 끝 위치
            last_match = matches[-1]
            last_digit_end = last_match.end()
            print(f"Last number found: '{last_match.group()}' at position {last_match.start()}-{last_match.end()}")
            
            if last_digit_end < len(text_content):
                # 마지막 숫자 그룹 다음부터
                text_after_number = text_content[last_digit_end:]
                print(f"After last number: '{text_after_number}'")
            else:
                # 숫자가 마지막에 있으면 빈 문자열
                text_after_number = ""
                print(f"Number is at the end, no text after")
        else:
            # 숫자가 없으면 전체 텍스트 사용
            text_after_number = text_content
            print(f"No number found, using full text")
        
        # 모든 '_'를 공백으로 변경
        cleaned_text = text_after_number.replace('_', ' ')
        print(f"After replacing '_' with space: '{cleaned_text}'")
        
        # 텍스트가 공백으로 시작하는지 확인
        starts_with_space = cleaned_text.startswith(' ')
        
        # 25mm 길이로 맞추기 
        # 높이 4.3mm, 폭 비율 0.85, 문자 간격 고려하여 약 10-12자
        max_chunk_length = 10  # 25mm에 맞는 대략적인 문자 수
        text_chunks = []
        
        # 단어별로 나누지 않고 전체 텍스트를 길이로만 자르기
        remaining_text = cleaned_text
        while remaining_text:
            # 현재 청크 추출
            if len(remaining_text) <= max_chunk_length:
                text_chunks.append(remaining_text)
                break
            else:
                # 공백 위치에서 자르기 시도
                chunk = remaining_text[:max_chunk_length]
                last_space = chunk.rfind(' ')
                
                # 공백이 있으면 거기서 자르기
                if last_space > 0:
                    text_chunks.append(remaining_text[:last_space])
                    remaining_text = remaining_text[last_space + 1:]  # 공백 다음부터
                else:
                    # 공백이 없으면 강제로 자르기
                    text_chunks.append(chunk)
                    remaining_text = remaining_text[max_chunk_length:]
        
        print(f"Text chunks: {text_chunks}")
        
        # 텍스트 출력
        for i, chunk in enumerate(text_chunks):
            text_entity = msp.add_text(
                chunk,
                dxfattribs={
                    'style': 'ARIAL',
                    'height': 4.3,
                    'color': 2,  # YELLOW
                    'width': 0.85,
                    'halign': 0,  # LEFT
                    'valign': 0,  # BASELINE
                    'insert': (508, 544 - i * 6, 0),  # -Y 6mm 간격
                    'layer': 'default'  # 레이어 추가
                }
            )
            print(f"Output chunk {i+1}: '{chunk}' at X=508, Y={544 - i * 6}")
        
        # SAT 텍스트 삭제
        try:
            msp.delete_entity(sat_text)
            print("SAT text deleted successfully")
        except Exception as e:
            print(f"Error deleting SAT text: {e}")
            # 삭제 실패 시 색상 변경으로 표시
            try:
                sat_text.dxf.color = 1  # RED
                print("SAT text marked in RED (deletion failed)")
            except:
                pass
    else:
        print("No SAT text found at specified location")
    
    # 추가 텍스트 출력
    print("\nAdding additional texts...")
    additional_texts = [
        (804, 546, 'MINERAL'),
        (808, 540, 'FIBER'),
        (804, 534, '(120kg/m)')
    ]
    
    for x, y, text in additional_texts:
        try:
            text_entity = msp.add_text(
                text,
                dxfattribs={
                    'style': 'ARIAL',
                    'height': 4.3,
                    'color': 2,  # YELLOW
                    'width': 0.85,
                    'halign': 0,  # LEFT
                    'valign': 0,  # BASELINE
                    'insert': (x, y, 0),
                    'layer': 'default'  # 레이어 추가
                }
            )
            print(f"Added text '{text}' at X={x}, Y={y}")
        except Exception as e:
            print(f"Error adding text '{text}': {e}")
    
    # 모든 TINFO 삭제
    print("\nDeleting all TINFO texts...")
    tinfo_delete_count = 0
    tinfo_delete_failed = 0
    for data in tinfo_data:
        try:
            msp.delete_entity(data['text_entity'])
            tinfo_delete_count += 1
        except Exception as e:
            print(f"Error deleting TINFO: {e}")
            tinfo_delete_failed += 1
            # 삭제 실패 시 색상 변경으로 표시
            try:
                data['text_entity'].dxf.color = 1  # RED
            except:
                pass
    
    print(f"TINFO deletion: {tinfo_delete_count} deleted, {tinfo_delete_failed} failed")
    
    # 엔티티 업데이트
    doc.entitydb.purge()  # 삭제된 엔티티 정리
    
    # I1~I9 텍스트 스타일 강제 변경 (파일 저장 전)
    print("\nForcing ARIAL style for I values...")
    
    # I1~I9 텍스트 찾아서 스타일 변경
    i_text_count = 0
    for entity in msp.query('TEXT'):
        if entity.dxf.color == 2:  # YELLOW 텍스트
            text_pos = entity.dxf.insert
            # I1~I9 위치 범위 확인
            if 540 <= text_pos[0] <= 800 and 450 <= text_pos[1] <= 560:
                try:
                    # I values 위치에 있는 텍스트인지 더 정확하게 확인
                    for x_pos in [553, 631.5, 650.5, 670.5, 690.5, 713, 746.5, 765.5, 785.5]:
                        if abs(text_pos[0] - x_pos) < 2:  # X 좌표가 거의 일치
                            # 스타일과 width 설정
                            try:
                                entity.dxf.style = 'ARIAL'
                            except:
                                pass
                            entity.dxf.width = 0.85
                            i_text_count += 1
                            print(f"  Updated text '{entity.dxf.text}' at X={text_pos[0]:.1f}")
                            break
                except Exception as e:
                    print(f"  Error updating text: {e}")
    
    print(f"Total I values texts updated: {i_text_count}")
    
    # 파일 저장
    base_name = os.path.splitext(os.path.basename(filepath))[0]
    output_path = os.path.join(os.path.dirname(filepath), f"{base_name}_SPNO.dxf")
    
    # 삭제할 엔티티들 제거 (entities_to_delete가 있는 경우에만)
    if entities_to_delete:
        print(f"\nPreparing to delete {len(entities_to_delete)} entities...")
        deleted_count = 0
        failed_count = 0
        
        for entity in entities_to_delete:
            try:
                # 엔티티가 유효한지 확인
                if entity.is_alive:
                    msp.delete_entity(entity)
                    deleted_count += 1
                else:
                    print(f"Entity already deleted or invalid")
                    failed_count += 1
            except Exception as e:
                print(f"Error deleting entity: {e}")
                failed_count += 1
        
        print(f"Deletion complete: {deleted_count} deleted, {failed_count} failed")
    else:
        print("No entities to delete (no SN matches found)")
    
    # 문서 업데이트
    try:
        doc.entitydb.purge()
    except:
        pass
    
    # DXF 버전 확인 및 설정
    print(f"\nDXF version: {doc.dxfversion}")
    
    # 파일 저장 (원본과 동일한 DXF 버전 유지)
    try:
        doc.saveas(output_path)
    except Exception as e:
        print(f"Error saving with original version, trying R2013: {e}")
        # R2013 버전으로 저장 시도 (더 나은 호환성)
        doc.saveas(output_path, dxfversion='AC1027')
    
    print(f"\nSaved: {output_path}")

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