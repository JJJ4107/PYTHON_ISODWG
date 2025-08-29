import ezdxf
import os
import math
import re
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
    """TEXT 엔티티의 위치를 Vec2로 반환"""
    try:
        # insert 속성 확인
        if hasattr(text.dxf, "insert"):
            ins = text.dxf.insert
            # Vec3 또는 3D 좌표인 경우
            if hasattr(ins, '__getitem__'):
                return Vec2(float(ins[0]), float(ins[1]))
            # x, y 속성이 있는 경우
            elif hasattr(ins, 'x') and hasattr(ins, 'y'):
                return Vec2(float(ins.x), float(ins.y))
            # 단일 값인 경우 (거의 없겠지만)
            else:
                return Vec2(float(ins), 0)
        
        # location 속성 확인 (구버전 호환)
        if hasattr(text.dxf, "location"):
            loc = text.dxf.location
            if hasattr(loc, '__getitem__') and len(loc) >= 2:
                return Vec2(float(loc[0]), float(loc[1]))
            elif hasattr(loc, 'x') and hasattr(loc, 'y'):
                return Vec2(float(loc.x), float(loc.y))
                
    except Exception as e:
        print(f"   [경고] TEXT 위치 가져오기 오류: {e}")
        if hasattr(text, 'dxf') and hasattr(text.dxf, 'text'):
            print(f"   [경고] TEXT 내용: '{text.dxf.text}'")
    
    # 기본값 반환
    return Vec2(0.0, 0.0)

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
            
            # 회전 각도 설정
            orig_angle = getattr(entity.dxf, 'rotation', 0)
            new_angle = (orig_angle + angle_deg) % 360
            entity.dxf.rotation = new_angle
            
            # 디버깅: 회전 결과 확인
            actual_rotation = getattr(entity.dxf, 'rotation', -999)
            print(f"     [회전 적용] TEXT '{entity.dxf.text}': {orig_angle:.1f}° → {new_angle:.1f}° (실제: {actual_rotation:.1f}°)")
            
        elif t == "LINE":
            a = Vec2(entity.dxf.start.x, entity.dxf.start.y)
            b = Vec2(entity.dxf.end.x, entity.dxf.end.y)
            ra = rotate_point(a, center, angle_deg)
            rb = rotate_point(b, center, angle_deg)
            entity.dxf.start = (ra.x, ra.y, 0)
            entity.dxf.end = (rb.x, rb.y, 0)
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
    return Vec2(x_sum/n, y_sum/n) if n else Vec2(0,0)

def get_line_center(line):
    """LINE 엔티티의 중심점 계산"""
    if line.dxftype() == "LINE":
        start = Vec2(line.dxf.start.x, line.dxf.start.y)
        end = Vec2(line.dxf.end.x, line.dxf.end.y)
        return Vec2((start.x + end.x) / 2, (start.y + end.y) / 2)
    return None

def get_line_angle(line):
    """LINE의 기울기(각도) 계산"""
    if line.dxftype() == "LINE":
        start = Vec2(line.dxf.start.x, line.dxf.start.y)
        end = Vec2(line.dxf.end.x, line.dxf.end.y)
        return calc_angle_deg(start, end)
    return 0

def check_line_passes_near_point(line, point, threshold=2.0):
    """LINE이 점 근처를 지나는지 확인"""
    if line.dxftype() == "LINE":
        start = Vec2(line.dxf.start.x, line.dxf.start.y)
        end = Vec2(line.dxf.end.x, line.dxf.end.y)
        # 점에서 선분까지의 최단거리 계산
        line_vec = Vec2(end.x - start.x, end.y - start.y)
        line_len = math.sqrt(line_vec.x**2 + line_vec.y**2)
        if line_len == 0:
            return distance(point, start) <= threshold
        
        t = max(0, min(1, ((point.x - start.x) * line_vec.x + (point.y - start.y) * line_vec.y) / (line_len**2)))
        closest_point = Vec2(start.x + t * line_vec.x, start.y + t * line_vec.y)
        return distance(point, closest_point) <= threshold
    return False

def get_line_length(line):
    """LINE의 길이 계산"""
    if line.dxftype() == "LINE":
        start = Vec2(line.dxf.start.x, line.dxf.start.y)
        end = Vec2(line.dxf.end.x, line.dxf.end.y)
        return distance(start, end)
    return 0

def set_mirrtext_zero(doc):
    try:
        doc.header['$MIRRTEXT'] = 0
        print("   [MIRRTEXT=0] 설정 완료")
    except Exception as e:
        print(f"▶ MIRRTEXT=0 설정 오류: {e}")

def get_text_bbox(text):
    """TEXT 엔티티의 경계 상자 계산 (BOX 높이 = TEXT 높이 + 0.3mm) - 회전 정보 포함"""
    pos = get_text_position(text)
    # TEXT 높이 가져오기 (기본값 2.2mm)
    height = getattr(text.dxf, 'height', 2.2)
    # 텍스트 길이를 대략적으로 계산 (문자 수 * 높이 * 0.8)
    text_len = len(text.dxf.text) * height * 0.8
    
    # BOX 높이는 항상 TEXT 높이 + 0.3mm
    box_height = height + 0.3
    
    # TEXT의 현재 회전 각도 가져오기
    rotation = getattr(text.dxf, 'rotation', 0)
    
    # 회전되지 않은 상태의 BOX (TEXT 원점 기준)
    return {
        'min_x': pos.x,
        'max_x': pos.x + text_len,
        'min_y': pos.y - 0.15,  # 아래로 0.15mm
        'max_y': pos.y + box_height - 0.15,  # pos.y + height + 0.15
        'rotation': rotation,  # TEXT의 회전 각도 포함
        'pos': pos  # TEXT의 위치 (회전 중심점)
    }

def get_rotated_bbox_bounds(bbox):
    """회전된 BOX의 실제 경계 좌표 계산"""
    # bbox가 dictionary인지 확인
    if not isinstance(bbox, dict):
        print(f"   [경고] bbox가 dictionary가 아닙니다: {type(bbox)}")
        return {'min_x': 0, 'max_x': 0, 'min_y': 0, 'max_y': 0}
    
    # 필수 키 확인
    if 'min_x' not in bbox or 'max_x' not in bbox or 'min_y' not in bbox or 'max_y' not in bbox:
        print(f"   [경고] bbox에 필수 키가 없습니다: {bbox.keys()}")
        return {'min_x': 0, 'max_x': 0, 'min_y': 0, 'max_y': 0}
    
    # TEXT의 insert point (회전 중심점)
    pos = bbox.get('pos')
    if not pos:
        # pos가 없으면 bbox의 좌하단을 기준점으로 사용
        pos = Vec2(bbox['min_x'], bbox['min_y'])
    
    # 회전되지 않은 상태의 4개 모서리 (insert point 기준 상대 좌표)
    corners = [
        (bbox['min_x'] - pos.x, bbox['min_y'] - pos.y),
        (bbox['max_x'] - pos.x, bbox['min_y'] - pos.y),
        (bbox['max_x'] - pos.x, bbox['max_y'] - pos.y),
        (bbox['min_x'] - pos.x, bbox['max_y'] - pos.y)
    ]
    
    # 회전 적용
    rotation = bbox.get('rotation', 0)
    if abs(rotation) > 0.01:  # 0도가 아닌 경우만 회전
        rotation_rad = math.radians(rotation)
        cos_r = math.cos(rotation_rad)
        sin_r = math.sin(rotation_rad)
        
        rotated_corners = []
        for dx, dy in corners:
            # 회전 변환
            rx = dx * cos_r - dy * sin_r
            ry = dx * sin_r + dy * cos_r
            # 원래 위치로 이동
            rotated_corners.append((rx + pos.x, ry + pos.y))
    else:
        # 회전이 없으면 원래 좌표 사용
        rotated_corners = [(x + pos.x, y + pos.y) for x, y in corners]
    
    # 회전된 BOX의 실제 min/max 좌표
    x_coords = [c[0] for c in rotated_corners]
    y_coords = [c[1] for c in rotated_corners]
    
    return {
        'min_x': min(x_coords),
        'max_x': max(x_coords),
        'min_y': min(y_coords),
        'max_y': max(y_coords)
    }

def draw_bbox(msp, bbox, layer_name, color):
    """BOX를 도면에 그리기 (회전된 BOX를 4개의 LINE으로 구성)"""
    try:
        # TEXT의 insert point (회전 중심점)
        pos = bbox.get('pos')
        if not pos:
            pos = Vec2(bbox['min_x'], bbox['min_y'])
        
        # 회전되지 않은 상태의 4개 모서리
        corners = [
            Vec2(bbox['min_x'], bbox['min_y']),
            Vec2(bbox['max_x'], bbox['min_y']),
            Vec2(bbox['max_x'], bbox['max_y']),
            Vec2(bbox['min_x'], bbox['max_y'])
        ]
        
        # 회전 적용
        rotation = bbox.get('rotation', 0)
        if abs(rotation) > 0.01:  # 0도가 아닌 경우만 회전
            rotated_corners = []
            for corner in corners:
                rotated = rotate_point(corner, pos, rotation)
                rotated_corners.append(rotated)
            corners = rotated_corners
        
        # 4개의 LINE 그리기
        line_count = 0
        for i in range(4):
            start = corners[i]
            end = corners[(i + 1) % 4]
            line = msp.add_line((start.x, start.y, 0), (end.x, end.y, 0))
            line.dxf.layer = layer_name
            line.dxf.color = color
            line_count += 1
        
        print(f"   [BOX 그리기 완료] {line_count}개 LINE 생성 (레이어: {layer_name}, 색상: {color})")
        return True
    except Exception as e:
        print(f"   [BOX 그리기 오류] {e}")
        return False

def point_to_line_distance(point, line_start, line_end):
    """점에서 선분까지의 최단 거리 계산"""
    line_vec = Vec2(line_end.x - line_start.x, line_end.y - line_start.y)
    line_len = math.sqrt(line_vec.x**2 + line_vec.y**2)
    
    if line_len == 0:
        return distance(point, line_start)
    
    # 점을 선분에 투영
    t = max(0, min(1, ((point.x - line_start.x) * line_vec.x + (point.y - line_start.y) * line_vec.y) / (line_len**2)))
    
    # 선분 위의 가장 가까운 점
    closest_point = Vec2(
        line_start.x + t * line_vec.x,
        line_start.y + t * line_vec.y
    )
    
    return distance(point, closest_point)

def check_fl_el_text(text):
    """TEXT가 FL+, FL-, EL+, EL- 중 하나를 포함하는지 확인"""
    text_upper = text.upper()
    
    # FL 또는 EL 다음에 공백(선택) 그리고 + 또는 - 패턴 확인
    # FL 또는 EL 다음에 0개 이상의 공백, 그리고 + 또는 -
    pattern = r'(FL|EL)\s*[+\-]'
    
    found = bool(re.search(pattern, text_upper))
    
    # 디버깅 정보
    if "FL" in text_upper or "EL" in text_upper:
        if not found:
            print(f"   [FL/EL 감지 실패] '{text}' - 패턴 불일치")
            # 문자 단위로 출력
            print(f"   [문자 분석] ", end="")
            for i, c in enumerate(text):
                if c == ' ':
                    print(f"[{i}:공백]", end="")
                else:
                    print(f"[{i}:{c}]", end="")
            print()
    
    return found

def process_dxf(file_path):
    try:
        doc = ezdxf.readfile(file_path)
    except Exception as e:
        print(f"파일 열기 실패: {file_path} / {e}")
        return

    msp = doc.modelspace()
    modified = False
    processed_count = 0

    # FL/EL 텍스트 검색
    all_texts = list(msp.query('TEXT'))
    print(f"\n[TEXT 검색] 전체 TEXT 수: {len(all_texts)}개")
    
    fl_el_texts = []
    for text in all_texts:
        if check_fl_el_text(text.dxf.text):
            rotation = getattr(text.dxf, 'rotation', 0)
            fl_el_texts.append((text, rotation))
            print(f"   - '{text.dxf.text}' (rotation: {rotation:.1f}°)")
    
    print(f"[FL/EL TEXT] 총 {len(fl_el_texts)}개 발견")

    for st1 in msp.query('TEXT'):
        # FL+, FL-, EL+, EL- 포함 확인
        if not check_fl_el_text(st1.dxf.text):
            continue
        
        # 원래 회전 각도 확인 - rotation이 0인 것만 처리
        st1_original_rotation = getattr(st1.dxf, 'rotation', 0)
        if st1_original_rotation != 0:
            print(f"\n[제외-회전] '{st1.dxf.text}' - rotation: {st1_original_rotation:.1f}° (0°만 처리)")
            continue  # 회전된 TEXT는 건너뛰기
            
        st1_pos = get_text_position(st1)
        
        print(f"\n[ELEDIT 처리 시작] '{st1.dxf.text}' (rotation: 0°)")
        
        # FL을 찾았을 때 바로 CYAN 색상으로 BOX화 (주석 처리 - 삭제 예정)
        initial_fl_bbox = get_text_bbox(st1)
        # draw_bbox(msp, initial_fl_bbox, "FLBOX", 4)  # CYAN = 4 - 삭제 요청으로 주석 처리
        
        initial_box_width = initial_fl_bbox['max_x'] - initial_fl_bbox['min_x']
        initial_box_height = initial_fl_bbox['max_y'] - initial_fl_bbox['min_y']
        print(f"   [FLBOX 정보] FL '{st1.dxf.text}' BOX 크기: 가로 {initial_box_width:.2f}mm × 세로 {initial_box_height:.2f}mm")
        print(f"   [FLBOX 정보] 회전: {initial_fl_bbox.get('rotation', 0):.1f}°")
        
        # FL 텍스트 위에서 N-, N+, S-, S+ 포함 텍스트 확인
        # 수정된 범위: Y방향 0~4mm, X방향 ±0.5mm 이내
        skip_this_fl = False
        for text in msp.query('TEXT'):
            if text is st1:
                continue
            text_pos = get_text_position(text)
            
            # Y 방향 0~4mm 범위 확인 (같은 높이 포함)
            dy = text_pos.y - st1_pos.y
            dx = abs(text_pos.x - st1_pos.x)
            
            if 0 <= dy <= 4 and dx <= 0.5:  # 수정된 조건
                text_upper = text.dxf.text.upper()
                # N 또는 S 다음에 공백(선택) 그리고 + 또는 - 패턴 확인
                pattern = r'[NS]\s*[+\-]'
                if re.search(pattern, text_upper):
                    print(f"   [제외] FL '{st1.dxf.text}' 위쪽에 '{text.dxf.text}' 발견 (Y: +{dy:.2f}mm, X: ±{dx:.2f}mm)")
                    skip_this_fl = True
                    break
        
        if skip_this_fl:
            print(f"\n[제외-N/S] '{st1.dxf.text}' - 위쪽에 N-, N+, S-, S+ 패턴 포함 텍스트 있음")
            continue

        # ELEDIT 그룹 확정 (색상, 레이어)
        st1.dxf.layer = "ELEDIT"
        set_entity_color(st1, 4)  # CYAN
        
        modified = True
        print(f"\n[ELEDIT 처리] FL/EL TEXT: {st1.dxf.text}")
        
        # 처리 전 회전 상태 확인
        st1_rot_before = getattr(st1.dxf, 'rotation', -999)
        print(f"   [처리 전 회전] ST1: {st1_rot_before:.1f}°")

        # ELEDITDN (DN 또는 " 포함) TEXT
        eledit_dn_text = None
        for e in msp.query('TEXT'):
            if e is st1:
                continue
            pos = get_text_position(e)
            dx = abs(pos.x - st1_pos.x)
            dy = st1_pos.y - pos.y
            if dx <= 2.0 and 0 < dy <= 4.0:
                text_upper = e.dxf.text.upper()
                if "DN" in text_upper or '"' in e.dxf.text:
                    eledit_dn_text = e
                    break
        if eledit_dn_text:
            eledit_dn_text.dxf.layer = "ELEDITDN"
            set_entity_color(eledit_dn_text, 4)  # CYAN
            print(f"   [ELEDITDN 추가] DN 또는 \" 포함 TEXT: '{eledit_dn_text.dxf.text}' 포함")

        # 변수 초기화
        found_DIMLINE = None
        
        # 1. 가장 가까운 LINE (A1) 찾기 - FL 텍스트의 좌측, 중앙, 우측 고려
        # FL 텍스트의 좌측, 중앙, 우측 점 계산
        fl_bbox = get_text_bbox(st1)
        fl_left_point = st1_pos  # 왼쪽 기준점 (insert point)
        fl_center_point = Vec2((fl_bbox['min_x'] + fl_bbox['max_x']) / 2, st1_pos.y)  # 중앙점
        fl_right_point = Vec2(fl_bbox['max_x'], st1_pos.y)  # 오른쪽 끝점
        
        print(f"   [FL 범위] 좌측: ({fl_left_point.x:.2f}, {fl_left_point.y:.2f}), 중앙: ({fl_center_point.x:.2f}, {fl_center_point.y:.2f}), 우측: ({fl_right_point.x:.2f}, {fl_right_point.y:.2f})")
        
        found_A1 = None
        AP1, AP2 = None, None
        min_dist = float("inf")
        
        for line in msp.query('LINE'):
            # FRAME 레이어 제외
            if line.dxf.layer.upper() == "FRAME":
                continue
            
            # FLBOX, FL_BOX 레이어 제외 (FL 텍스트의 박스이므로 A1이 되면 안됨)
            if line.dxf.layer.upper() in ["FLBOX", "FL_BOX"]:
                continue
            
            # DEL1 레이어 제외
            if line.dxf.layer.upper() == "DEL1":
                continue
            
            # 2mm 이하 LINE 제외
            line_len = get_line_length(line)
            if line_len <= 2.0:
                continue
                
            start = Vec2(line.dxf.start.x, line.dxf.start.y)
            end = Vec2(line.dxf.end.x, line.dxf.end.y)
            
            # FL의 3개 참조점에서 LINE의 각 점까지 거리 계산
            distances = []
            for fl_point in [fl_left_point, fl_center_point, fl_right_point]:
                distances.append(distance(start, fl_point))
                distances.append(distance(end, fl_point))
            
            min_pt_dist = min(distances)
            
            if min_pt_dist < min_dist:
                min_dist = min_pt_dist
                found_A1 = line
                
                # 어느 점이 가장 가까운지 확인
                min_idx = distances.index(min_pt_dist)
                
                # 최소 거리가 LINE의 start점인지 end점인지 확인
                if min_idx % 2 == 0:  # start점이 더 가까움
                    AP1 = start
                    AP2 = end
                else:  # end점이 더 가까움
                    AP1 = end
                    AP2 = start
                
        if not found_A1:
            print(f"   [A1 없음] ELEDIT에서 가장 가까운 LINE을 찾을 수 없습니다 (FRAME 레이어 제외)")
            continue
        found_A1.dxf.layer = "A1"
        set_entity_color(found_A1, 4)  # CYAN = 4
        print(f"   [A1] FL/EL에서 가장 가까운 LINE {found_A1.dxf.handle} (CYAN 색상, FRAME 제외)")
        print(f"   [A1] AP1: ({AP1.x:.2f}, {AP1.y:.2f}), AP2: ({AP2.x:.2f}, {AP2.y:.2f})")

        # 추가 A1 LINE들을 저장할 리스트 초기화
        additional_a1_lines = []
        
        # DEL1: A1 끝에서 2mm 접하는 2mm 이하 LINE 3개 찾기
        del1_lines = []
        
        # DEL1 찾기 시도 (최대 10번 반복)
        for attempt in range(10):
            del1_lines = []
            
            if found_A1:
                # 현재 A1과 추가 LINE들의 끝점 수집
                all_endpoints = []
                
                # 원래 A1의 끝점들
                a1_start = Vec2(found_A1.dxf.start.x, found_A1.dxf.start.y)
                a1_end = Vec2(found_A1.dxf.end.x, found_A1.dxf.end.y)
                all_endpoints.extend([a1_start, a1_end])
                
                # 추가 LINE들의 끝점들
                for add_line in additional_a1_lines:
                    add_start = Vec2(add_line.dxf.start.x, add_line.dxf.start.y)
                    add_end = Vec2(add_line.dxf.end.x, add_line.dxf.end.y)
                    all_endpoints.extend([add_start, add_end])
                
                # 모든 끝점에서 DEL1 찾기
                for line in msp.query('LINE'):
                    if line is found_A1:
                        continue
                    if line in additional_a1_lines:
                        continue
                    if line in del1_lines:  # 이미 DEL1에 포함된 경우 제외
                        continue
                        
                    # FRAME 레이어 제외
                    if line.dxf.layer.upper() == "FRAME":
                        continue
                    
                    # FLBOX 레이어 제외
                    if line.dxf.layer.upper() == "FLBOX":
                        continue
                        
                    line_len = get_line_length(line)
                    if line_len > 2.0:
                        continue
                    
                    start = Vec2(line.dxf.start.x, line.dxf.start.y)
                    end = Vec2(line.dxf.end.x, line.dxf.end.y)
                    
                    # 모든 A1 끝점들과의 거리 확인
                    for endpoint in all_endpoints:
                        if (distance(start, endpoint) <= 2.0 or distance(end, endpoint) <= 2.0):
                            del1_lines.append(line)
                            break
                    
                    if len(del1_lines) >= 3:
                        break
                
                # DEL1을 찾았으면 종료
                if del1_lines:
                    print(f"   [DEL1 찾기] {attempt+1}차 시도에서 {len(del1_lines)}개 발견")
                    break
                
                # DEL1을 못 찾았으면 A1 끝점에서 0.2mm 범위 내 LINE 찾기
                print(f"   [DEL1 없음] {attempt+1}차 시도 - A1 끝점 0.2mm 범위 내 LINE 검색")
                
                # 디버깅: 검색 대상 끝점들 출력
                print(f"   [검색 끝점] 총 {len(all_endpoints)}개 끝점에서 검색:")
                for i, ep in enumerate(all_endpoints):
                    print(f"     끝점{i+1}: ({ep.x:.3f}, {ep.y:.3f})")
                
                found_additional = False
                candidates_checked = 0
                
                for line in msp.query('LINE'):
                    if line is found_A1:
                        continue
                    if line in additional_a1_lines:
                        continue
                    # FRAME 레이어 제외
                    if line.dxf.layer.upper() == "FRAME":
                        continue
                    
                    # FLBOX 레이어 제외
                    if line.dxf.layer.upper() == "FLBOX":
                        continue
                    
                    # DEL1 레이어 제외
                    if line.dxf.layer.upper() == "DEL1":
                        continue
                    
                    # 2mm 이하 LINE 제외
                    line_len = get_line_length(line)
                    if line_len <= 2.0:
                        continue
                    
                    candidates_checked += 1
                    start = Vec2(line.dxf.start.x, line.dxf.start.y)
                    end = Vec2(line.dxf.end.x, line.dxf.end.y)
                    
                    # 모든 A1 끝점에서 0.3mm 범위 내 점 확인 (여유 증가)
                    for endpoint in all_endpoints:
                        dist_to_start = distance(start, endpoint)
                        dist_to_end = distance(end, endpoint)
                        
                        if dist_to_start <= 0.3:  # 0.2 -> 0.3으로 증가
                            additional_a1_lines.append(line)
                            # 새로운 AP2 설정 (연결되지 않은 끝점)
                            AP2 = end
                            print(f"   [A1 확장] LINE {line.dxf.handle} 추가 (시작점 거리: {dist_to_start:.3f}mm)")
                            print(f"   [A1 확장] 새 AP2: ({AP2.x:.2f}, {AP2.y:.2f})")
                            found_additional = True
                            break
                        elif dist_to_end <= 0.3:  # 0.2 -> 0.3으로 증가
                            additional_a1_lines.append(line)
                            # 새로운 AP2 설정 (연결되지 않은 끝점)
                            AP2 = start
                            print(f"   [A1 확장] LINE {line.dxf.handle} 추가 (끝점 거리: {dist_to_end:.3f}mm)")
                            print(f"   [A1 확장] 새 AP2: ({AP2.x:.2f}, {AP2.y:.2f})")
                            found_additional = True
                            break
                    
                    if found_additional:
                        break
                
                print(f"   [A1 검색 결과] {candidates_checked}개 LINE 검사")
                
                if not found_additional:
                    print(f"   [DEL1 검색 종료] 더 이상 연결된 LINE을 찾을 수 없습니다.")
                    break
        
        # DEL1 검색 결과 최종 확인
        if not del1_lines:
            print(f"   [DEL1 없음] DEL1을 찾지 못했습니다.")
            
            # ==== 수정된 부분: DEL1을 찾지 못한 경우에만 추가 ISOTEXT 레이어 LINE 검색 ====
            print(f"   [ISOTEXT 추가 검색] DEL1을 찾지 못하여 추가 ISOTEXT 레이어 LINE을 검색합니다.")
            
            # A1에 추가: AP2 끝에서 가장 가까운 2mm 이상의 ISOTEXT 레이어 LINE 1개
            isotext_line = None
            min_isotext_dist = float("inf")
            
            for line in msp.query('LINE'):
                if line is found_A1:
                    continue
                
                # ISOTEXT 레이어만 대상
                if line.dxf.layer.upper() != "ISOTEXT":
                    continue
                
                # DEL1 레이어는 이미 ISOTEXT가 아니므로 제외됨
                
                # 길이가 2mm 이상인 LINE만
                line_len = get_line_length(line)
                if line_len < 2.0:
                    continue
                
                # AP2에서 각 끝점까지의 거리 계산
                start = Vec2(line.dxf.start.x, line.dxf.start.y)
                end = Vec2(line.dxf.end.x, line.dxf.end.y)
                dist_to_start = distance(AP2, start)
                dist_to_end = distance(AP2, end)
                min_dist_to_ap2 = min(dist_to_start, dist_to_end)
                
                if min_dist_to_ap2 < min_isotext_dist:
                    min_isotext_dist = min_dist_to_ap2
                    isotext_line = line
            
            # ISOTEXT LINE을 찾았으면 A1 그룹에 추가
            if isotext_line:
                isotext_line.dxf.layer = "A1"
                set_entity_color(isotext_line, 4)  # CYAN = 4
                additional_a1_lines.append(isotext_line)
                
                # 새로운 AP2 설정 (ISOTEXT LINE의 AP2에서 먼 끝점)
                start = Vec2(isotext_line.dxf.start.x, isotext_line.dxf.start.y)
                end = Vec2(isotext_line.dxf.end.x, isotext_line.dxf.end.y)
                if distance(AP2, start) < distance(AP2, end):
                    AP2 = end  # end가 더 멀면 end를 새 AP2로
                else:
                    AP2 = start  # start가 더 멀면 start를 새 AP2로
                
                line_len = get_line_length(isotext_line)
                print(f"   [A1 추가] ISOTEXT LINE {isotext_line.dxf.handle} 추가 (길이={line_len:.2f}mm, AP2에서 거리={min_isotext_dist:.2f}mm)")
                print(f"   [A1 추가] 새로운 AP2: ({AP2.x:.2f}, {AP2.y:.2f})")
                
                # ISOTEXT를 추가한 후 DEL1 재검색
                print(f"   [DEL1 재검색] ISOTEXT 추가 후 DEL1을 다시 검색합니다.")
                
                # 모든 A1 끝점 재수집
                all_endpoints = []
                all_endpoints.extend([Vec2(found_A1.dxf.start.x, found_A1.dxf.start.y), 
                                    Vec2(found_A1.dxf.end.x, found_A1.dxf.end.y)])
                
                for add_line in additional_a1_lines:
                    all_endpoints.extend([Vec2(add_line.dxf.start.x, add_line.dxf.start.y),
                                        Vec2(add_line.dxf.end.x, add_line.dxf.end.y)])
                
                # DEL1 재검색
                for line in msp.query('LINE'):
                    if line is found_A1:
                        continue
                    if line in additional_a1_lines:
                        continue
                    if line in del1_lines:
                        continue
                        
                    # FLBOX 레이어 제외
                    if line.dxf.layer.upper() == "FLBOX":
                        continue
                        
                    if line.dxf.layer.upper() != "ISOTEXT":
                        continue
                        
                    line_len = get_line_length(line)
                    if line_len > 2.0:
                        continue
                    
                    start = Vec2(line.dxf.start.x, line.dxf.start.y)
                    end = Vec2(line.dxf.end.x, line.dxf.end.y)
                    
                    for endpoint in all_endpoints:
                        if (distance(start, endpoint) <= 2.0 or distance(end, endpoint) <= 2.0):
                            del1_lines.append(line)
                            break
                    
                    if len(del1_lines) >= 3:
                        break
                
                if del1_lines:
                    print(f"   [DEL1 재검색 성공] {len(del1_lines)}개 DEL1 발견")
                else:
                    print(f"   [DEL1 재검색 실패] 여전히 DEL1을 찾지 못했습니다.")
            else:
                print(f"   [ISOTEXT 없음] AP2에서 가장 가까운 2mm 이상의 ISOTEXT 레이어를 찾을 수 없습니다.")
            
            print(f"   [작업 계속 진행] DEL1 없이 작업을 계속 진행합니다.")
        
        # AP2가 변경되었을 수 있으므로 DIMLINE 재검색이 필요한 경우

        # 2. DIMLINE 찾기 (AP2에서 2mm 이내를 지나는 DIMLINES 레이어)
        found_DIMLINE = None
        min_dimline_dist = float("inf")
        
        for line in msp.query('LINE'):
            if line is found_A1:
                continue
            
            # FLBOX 레이어 제외
            if line.dxf.layer.upper() == "FLBOX":
                continue
            
            # DIMLINES 레이어 확인
            if line.dxf.layer.upper() != "DIMLINES":
                continue
            
            # 길이가 1.8mm 이하인 LINE 제외
            if get_line_length(line) <= 1.8:
                continue
            
            # 수직 LINE 제외 (각도가 85~95도 또는 -95~-85도인 경우)
            line_angle = get_line_angle(line)
            if (85 <= abs(line_angle) <= 95):
                print(f"   [DIMLINE 제외] 수직 LINE 제외: {line.dxf.handle} (각도={line_angle:.1f}°)")
                continue
                
            # AP2에서 2mm 이내를 지나는지 확인
            if check_line_passes_near_point(line, AP2, 2.0):
                # 중심점과 AP2의 거리로 우선순위 결정
                center = get_line_center(line)
                if center:
                    dist = distance(center, AP2)
                    if dist < min_dimline_dist:
                        min_dimline_dist = dist
                        found_DIMLINE = line

        if not found_DIMLINE:
            print(f"   [DIMLINE 없음] AP2에서 2mm 이내를 지나는 DIMLINES 레이어(1.8mm 초과)를 찾을 수 없습니다.")
            continue
        else:
            line_len = get_line_length(found_DIMLINE)
            print(f"   [DIMLINE] DIMLINES 레이어 발견: {found_DIMLINE.dxf.handle} (길이={line_len:.2f}mm)")
            
            # DIMLINE을 DIM 레이어로 변경하고 CYAN 색상 설정
            found_DIMLINE.dxf.layer = "DIM"
            set_entity_color(found_DIMLINE, 4)  # CYAN
            print(f"   [DIMLINE] DIM 레이어로 변경, CYAN 색상 적용")
            
            # DIMLINE 길이가 10mm 이하면 SKIP
            if line_len <= 10.0:
                print(f"   [SKIP] DIMLINE 길이가 10mm 이하({line_len:.2f}mm)이므로 작업을 건너뜁니다.")
                continue

        # DPOS 계산 (DIMLINE 중심점)
        dpos = get_line_center(found_DIMLINE)
        if not dpos:
            print(f"   [DPOS 오류] DIMLINE 중심점 계산 실패. 처리 건너뜁니다.")
            continue
        print(f"   [DPOS] DIMLINE 중심점: ({dpos.x:.2f}, {dpos.y:.2f})")
        
        # DIMLINE 기울기 계산
        dimline_angle = get_line_angle(found_DIMLINE)
        print(f"   [DIMLINE 기울기] {dimline_angle:.2f}° (수평=0°, 수직위=90°, 수직아래=-90°)")

        # 3. AD1 찾기 (AP2에서 가장 가까운 짧은 LINE, 길이 1.5mm 이하)
        found_AD1 = None
        min_ad1_dist = float("inf")
        
        for line in msp.query('LINE'):
            if line is found_A1 or line is found_DIMLINE:
                continue
            
            # FLBOX 레이어 제외
            if line.dxf.layer.upper() == "FLBOX":
                continue
            
            # 길이 계산
            line_len = get_line_length(line)
            if line_len > 1.5:  # 5mm에서 1.5mm로 변경
                continue
                
            # AP2에서 가장 가까운 점까지의 거리
            start = Vec2(line.dxf.start.x, line.dxf.start.y)
            end = Vec2(line.dxf.end.x, line.dxf.end.y)
            min_dist_to_ap2 = min(distance(start, AP2), distance(end, AP2))
            
            if min_dist_to_ap2 < min_ad1_dist:
                min_ad1_dist = min_dist_to_ap2
                found_AD1 = line
        
        if found_AD1:
            found_AD1.dxf.layer = "AD1"
            set_entity_color(found_AD1, 3)  # GREEN = 3
            line_len = get_line_length(found_AD1)
            print(f"   [AD1] 짧은 LINE 발견: {found_AD1.dxf.handle}, 길이={line_len:.2f}mm (≤1.5mm), AP2에서 거리={min_ad1_dist:.2f}mm)")
        else:
            print(f"   [AD1 없음] 조건에 맞는 짧은 LINE을 찾을 수 없습니다 (1.5mm 이하).")

        # 추가된 A1 LINE들도 A1 레이어로 설정
        for add_line in additional_a1_lines:
            add_line.dxf.layer = "A1"
            set_entity_color(add_line, 4)  # CYAN = 4
            print(f"   [A1 추가] 확장된 LINE {add_line.dxf.handle} (CYAN 색상)")
            
        # DEL1 레이어 설정
        for i, line in enumerate(del1_lines):
            line.dxf.layer = "DEL1"
            set_entity_color(line, 4)  # CYAN
            print(f"   [DEL1-{i+1}] A1 근처 2mm 이하 LINE: {line.dxf.handle} (FRAME 제외)")

        # 4. ELEDIT 그룹 이동 및 회전
        # ELEDIT 그룹 구성
        eledit_entities = [st1]
        if eledit_dn_text:
            eledit_entities.append(eledit_dn_text)

        print("\n   ========== ELEDIT 변환 상세 정보 ==========")
        
        # FL TEXT의 현재 기준점
        fl_insert_point = get_text_position(st1)
        print(f"   [FL 기준점] 현재 위치: ({fl_insert_point.x:.2f}, {fl_insert_point.y:.2f})")
        
        # 1. FL 기준점을 DIM 선상에 투영
        dim_start = Vec2(found_DIMLINE.dxf.start.x, found_DIMLINE.dxf.start.y)
        dim_end = Vec2(found_DIMLINE.dxf.end.x, found_DIMLINE.dxf.end.y)
        dim_vector = Vec2(dim_end.x - dim_start.x, dim_end.y - dim_start.y)
        dim_length = math.sqrt(dim_vector.x**2 + dim_vector.y**2)
        
        if dim_length > 0:
            dim_unit_vector = Vec2(dim_vector.x / dim_length, dim_vector.y / dim_length)
        else:
            dim_unit_vector = Vec2(1, 0)
        
        # FL 기준점을 DIM 선상에 투영하여 가장 가까운 점 찾기
        fl_to_start = Vec2(fl_insert_point.x - dim_start.x, fl_insert_point.y - dim_start.y)
        projection_length = (fl_to_start.x * dim_unit_vector.x + fl_to_start.y * dim_unit_vector.y)
        
        # 투영 길이를 DIM 범위 내로 제한
        projection_length = max(0, min(dim_length, projection_length))
        
        # DIM 선상의 투영점
        projection_point = Vec2(
            dim_start.x + dim_unit_vector.x * projection_length,
            dim_start.y + dim_unit_vector.y * projection_length
        )
        print(f"   [DIM 투영점] ({projection_point.x:.2f}, {projection_point.y:.2f})")
        
        # 2. 투영점에서 수직으로 0.8mm 위쪽 계산
        perp_offset = get_perpendicular_offset(dimline_angle, 0.8)
        if perp_offset.y < 0:  # 항상 위쪽으로
            perp_offset = Vec2(-perp_offset.x, -perp_offset.y)
        
        # FL의 목표 위치 (DIM 투영점 + 수직 0.8mm)
        target_fl_pos = Vec2(
            projection_point.x + perp_offset.x,
            projection_point.y + perp_offset.y
        )
        
        # 이동 벡터 계산
        move_to_target = Vec2(
            target_fl_pos.x - fl_insert_point.x,
            target_fl_pos.y - fl_insert_point.y
        )
        
        print(f"   [이동1] FL 기준점 → DIM 위 0.8mm 위치")
        print(f"   [이동1] 이동 벡터: ({move_to_target.x:.2f}, {move_to_target.y:.2f})")
        print(f"   [이동1] 이동 거리: {math.sqrt(move_to_target.x**2 + move_to_target.y**2):.2f}mm")
        
        # 모든 엔티티 이동
        for ent in eledit_entities:
            move_entity(ent, move_to_target)
        print(f"   [이동1 실행] FL 기준점을 DIM 위 0.8mm 위치로 이동 완료")
        
        # 2. DIM 기울기만큼 회전 (FL 기준점 중심)
        current_fl_pos = get_text_position(st1)
        for ent in eledit_entities:
            rotate_entity_around(ent, current_fl_pos, dimline_angle)
        print(f"   [회전 실행] FL 기준점 중심으로 {dimline_angle:.2f}° 회전 완료")
        
        # 회전 후 상태 확인
        if st1.dxftype() == "TEXT":
            st1_rot_after = getattr(st1.dxf, 'rotation', -999)
            print(f"   [회전 후 확인] ST1: {st1_rot_after:.1f}°")
        
        # 3. 회전 후 FL 기준점을 다시 DIM 위 0.8mm로 조정
        # 회전으로 인해 위치가 변했을 수 있으므로 재조정
        rotated_fl_pos = get_text_position(st1)
        
        # FL 기준점을 DIM 선상에 재투영
        fl_to_start = Vec2(rotated_fl_pos.x - dim_start.x, rotated_fl_pos.y - dim_start.y)
        projection_length = (fl_to_start.x * dim_unit_vector.x + fl_to_start.y * dim_unit_vector.y)
        projection_length = max(0, min(dim_length, projection_length))
        
        # DIM 선상의 투영점
        projection_point = Vec2(
            dim_start.x + dim_unit_vector.x * projection_length,
            dim_start.y + dim_unit_vector.y * projection_length
        )
        
        # 투영점에서 수직으로 0.8mm 위쪽 재계산
        perp_offset = get_perpendicular_offset(dimline_angle, 0.8)
        if perp_offset.y < 0:  # 항상 위쪽으로
            perp_offset = Vec2(-perp_offset.x, -perp_offset.y)
        
        # FL의 최종 목표 위치
        final_fl_pos = Vec2(
            projection_point.x + perp_offset.x,
            projection_point.y + perp_offset.y
        )
        
        # 최종 조정 이동
        final_adjustment = Vec2(
            final_fl_pos.x - rotated_fl_pos.x,
            final_fl_pos.y - rotated_fl_pos.y
        )
        
        if abs(final_adjustment.x) > 0.01 or abs(final_adjustment.y) > 0.01:
            for ent in eledit_entities:
                move_entity(ent, final_adjustment)
            print(f"   [최종 조정] FL 기준점을 DIM 위 0.8mm로 재조정")
            print(f"   [최종 조정] 조정 벡터: ({final_adjustment.x:.2f}, {final_adjustment.y:.2f})")
        
        # 최종 위치 확인
        final_fl_insert = get_text_position(st1)
        print(f"   [최종 위치] FL 기준점: ({final_fl_insert.x:.2f}, {final_fl_insert.y:.2f})")
        
        # DIM으로부터의 실제 거리 확인
        final_fl_to_start = Vec2(final_fl_insert.x - dim_start.x, final_fl_insert.y - dim_start.y)
        final_projection = (final_fl_to_start.x * dim_unit_vector.x + final_fl_to_start.y * dim_unit_vector.y)
        final_proj_point = Vec2(
            dim_start.x + dim_unit_vector.x * final_projection,
            dim_start.y + dim_unit_vector.y * final_projection
        )
        actual_distance = distance(final_fl_insert, final_proj_point)
        print(f"   [거리 확인] DIM으로부터의 실제 거리: {actual_distance:.3f}mm")
        print("   ==========================================\n")

        # 4. 각도 보정
        # 4-1. DIMLINE 각도가 90도 이상이거나 -90도 이하일 때 180도 회전
        if dimline_angle > 90 or dimline_angle <= -90:
            set_mirrtext_zero(doc)
            print(f"\n   [각도 보정] DIMLINE 각도가 {dimline_angle:.2f}° (>90° 또는 ≤-90°)이므로 180도 추가 회전")
            
            # FL 기준점 중심으로 180도 회전
            fl_pos_for_rotation = get_text_position(st1)
            for ent in eledit_entities:
                rotate_entity_around(ent, fl_pos_for_rotation, 180)
            print("   [각도 보정] FL 기준점 중심으로 180도 회전 완료, MIRRTEXT=0 설정")
            
            # 회전 후 다시 DIM 위 0.8mm로 조정
            rotated_fl_pos = get_text_position(st1)
            
            # FL 기준점을 DIM 선상에 재투영
            fl_to_start = Vec2(rotated_fl_pos.x - dim_start.x, rotated_fl_pos.y - dim_start.y)
            projection_length = (fl_to_start.x * dim_unit_vector.x + fl_to_start.y * dim_unit_vector.y)
            projection_length = max(0, min(dim_length, projection_length))
            
            # DIM 선상의 투영점
            projection_point = Vec2(
                dim_start.x + dim_unit_vector.x * projection_length,
                dim_start.y + dim_unit_vector.y * projection_length
            )
            
            # 투영점에서 수직으로 0.8mm 위쪽 재계산
            perp_offset = get_perpendicular_offset(dimline_angle, 0.8)
            if perp_offset.y < 0:  # 항상 위쪽으로
                perp_offset = Vec2(-perp_offset.x, -perp_offset.y)
            
            # FL의 최종 목표 위치
            final_fl_pos = Vec2(
                projection_point.x + perp_offset.x,
                projection_point.y + perp_offset.y
            )
            
            # 최종 조정 이동
            final_adjustment = Vec2(
                final_fl_pos.x - rotated_fl_pos.x,
                final_fl_pos.y - rotated_fl_pos.y
            )
            
            if abs(final_adjustment.x) > 0.01 or abs(final_adjustment.y) > 0.01:
                for ent in eledit_entities:
                    move_entity(ent, final_adjustment)
                print(f"   [각도 보정 후 조정] FL 기준점을 DIM 위 0.8mm로 재조정")
                print(f"   [각도 보정 후 조정] 조정 벡터: ({final_adjustment.x:.2f}, {final_adjustment.y:.2f})")

        # 5. DIM 연장 체크 (필요시)
        # 현재 FL BOX 계산 (이동/회전 후)
        current_fl_bbox = get_text_bbox(st1)
        fl_bounds = get_rotated_bbox_bounds(current_fl_bbox)
        
        # DIM 방향에 따른 FL BOX의 범위 계산
        # DIM 선상에 FL BOX의 최소/최대 투영점 찾기
        fl_corners = [
            Vec2(fl_bounds['min_x'], fl_bounds['min_y']),
            Vec2(fl_bounds['max_x'], fl_bounds['min_y']),
            Vec2(fl_bounds['max_x'], fl_bounds['max_y']),
            Vec2(fl_bounds['min_x'], fl_bounds['max_y'])
        ]
        
        # DIM 방향 벡터 재계산
        dim_start = Vec2(found_DIMLINE.dxf.start.x, found_DIMLINE.dxf.start.y)
        dim_end = Vec2(found_DIMLINE.dxf.end.x, found_DIMLINE.dxf.end.y)
        dim_vector = Vec2(dim_end.x - dim_start.x, dim_end.y - dim_start.y)
        dim_length = math.sqrt(dim_vector.x**2 + dim_vector.y**2)
        
        if dim_length > 0:
            dim_unit_vector = Vec2(dim_vector.x / dim_length, dim_vector.y / dim_length)
        else:
            dim_unit_vector = Vec2(1, 0)
        
        # 각 모서리를 DIM 선상에 투영
        min_projection = float('inf')
        max_projection = float('-inf')
        
        for corner in fl_corners:
            corner_to_start = Vec2(corner.x - dim_start.x, corner.y - dim_start.y)
            projection = (corner_to_start.x * dim_unit_vector.x + corner_to_start.y * dim_unit_vector.y)
            min_projection = min(min_projection, projection)
            max_projection = max(max_projection, projection)
        
        # DIM 연장 필요 여부 체크
        # FL 텍스트 길이 계산 (연장 제한 기준)
        fl_text_length = current_fl_bbox['max_x'] - current_fl_bbox['min_x']
        max_extend = fl_text_length * 0.5  # 최대 FL 길이의 1/2
        min_extend = fl_text_length * 0.25  # 최소 FL 길이의 1/4
        
        # FL 위치 조정이 필요한지 확인하기 위한 변수
        fl_position_adjustment_needed = False
        fl_adjustment_offset = Vec2(0, 0)
        
        if min_projection < 0:
            # DIM start 쪽으로 연장 필요
            original_extend = abs(min_projection)
            extend_length = original_extend
            
            # 최대/최소 제한 적용
            if extend_length > max_extend:
                extend_length = max_extend
                # FL을 오른쪽으로 이동해야 함
                adjustment_distance = original_extend - extend_length
                fl_adjustment_offset = Vec2(
                    dim_unit_vector.x * adjustment_distance,
                    dim_unit_vector.y * adjustment_distance
                )
                fl_position_adjustment_needed = True
                print(f"   [DIM 연장 제한] 최대 연장 길이 {max_extend:.2f}mm로 제한")
                print(f"   [FL 위치 조정 필요] {adjustment_distance:.2f}mm 이동 필요")
            elif extend_length < min_extend:
                extend_length = min_extend
                print(f"   [DIM 연장 보정] 최소 연장 길이 {min_extend:.2f}mm로 보정")
                
            new_start = Vec2(
                dim_start.x - dim_unit_vector.x * extend_length,
                dim_start.y - dim_unit_vector.y * extend_length
            )
            found_DIMLINE.dxf.start = (new_start.x, new_start.y, 0)
            print(f"   [DIM 연장] 시작점 쪽으로 {extend_length:.2f}mm 연장 (FL 길이 {fl_text_length:.2f}mm의 {extend_length/fl_text_length*100:.0f}%)")
            
        if max_projection > dim_length:
            # DIM end 쪽으로 연장 필요
            original_extend = max_projection - dim_length
            extend_length = original_extend
            
            # 최대/최소 제한 적용
            if extend_length > max_extend:
                extend_length = max_extend
                # FL을 왼쪽으로 이동해야 함
                adjustment_distance = original_extend - extend_length
                fl_adjustment_offset = Vec2(
                    -dim_unit_vector.x * adjustment_distance,
                    -dim_unit_vector.y * adjustment_distance
                )
                fl_position_adjustment_needed = True
                print(f"   [DIM 연장 제한] 최대 연장 길이 {max_extend:.2f}mm로 제한")
                print(f"   [FL 위치 조정 필요] {adjustment_distance:.2f}mm 이동 필요")
            elif extend_length < min_extend:
                extend_length = min_extend
                print(f"   [DIM 연장 보정] 최소 연장 길이 {min_extend:.2f}mm로 보정")
                
            new_end = Vec2(
                dim_end.x + dim_unit_vector.x * extend_length,
                dim_end.y + dim_unit_vector.y * extend_length
            )
            found_DIMLINE.dxf.end = (new_end.x, new_end.y, 0)
            print(f"   [DIM 연장] 끝점 쪽으로 {extend_length:.2f}mm 연장 (FL 길이 {fl_text_length:.2f}mm의 {extend_length/fl_text_length*100:.0f}%)")
        
        # FL 위치 조정이 필요한 경우
        if fl_position_adjustment_needed:
            print(f"\n   [FL 위치 재조정] DIM 연장 제한으로 인한 FL 위치 조정")
            print(f"   [조정 벡터] ({fl_adjustment_offset.x:.2f}, {fl_adjustment_offset.y:.2f})")
            
            # ELEDIT 그룹 전체 이동
            for ent in eledit_entities:
                move_entity(ent, fl_adjustment_offset)
            
            # 이동 후 최종 위치 확인
            final_fl_pos_after_adjust = get_text_position(st1)
            print(f"   [조정 후 FL 위치] ({final_fl_pos_after_adjust.x:.2f}, {final_fl_pos_after_adjust.y:.2f})")

        # 5-1. 최종 위치에서 FL BOX 그리기 (주석 처리 - 삭제 예정)
        print(f"\n   ========== FL BOX 정보 ==========")
        final_fl_bbox = get_text_bbox(st1)  # 최종 위치에서 BOX 재계산
        # draw_bbox(msp, final_fl_bbox, "FL_BOX", 6)  # MAGENTA = 6 - 삭제 요청으로 주석 처리
        
        box_width = final_fl_bbox['max_x'] - final_fl_bbox['min_x']
        box_height = final_fl_bbox['max_y'] - final_fl_bbox['min_y']
        print(f"   [FL BOX 정보] FL '{st1.dxf.text}' 최종 BOX 크기: 가로 {box_width:.2f}mm × 세로 {box_height:.2f}mm")
        print(f"   [FL BOX 정보] 회전: {final_fl_bbox.get('rotation', 0):.1f}°")
        
        # 최종 BOX의 4개 모서리 출력
        final_bounds = get_rotated_bbox_bounds(final_fl_bbox)
        final_corners = [
            Vec2(final_bounds['min_x'], final_bounds['min_y']),
            Vec2(final_bounds['max_x'], final_bounds['min_y']),
            Vec2(final_bounds['max_x'], final_bounds['max_y']),
            Vec2(final_bounds['min_x'], final_bounds['max_y'])
        ]
        print(f"   [FL BOX 정보] 최종 4개 모서리:")
        for i, corner in enumerate(final_corners):
            print(f"   - 모서리{i+1}: ({corner.x:.2f}, {corner.y:.2f})")
        
        processed_count += 1

        # 6. A1, AD1, DEL1 삭제
        to_remove = []
        removed_entities = set()  # 중복 삭제 방지
        
        if found_A1:
            to_remove.append((found_A1, f"A1: {getattr(found_A1.dxf, 'handle', 'unknown')}"))
            removed_entities.add(found_A1)
        
        # 추가된 A1 LINE들도 삭제 목록에 추가
        for i, add_line in enumerate(additional_a1_lines):
            if add_line not in removed_entities:
                to_remove.append((add_line, f"A1-추가{i+1}: {getattr(add_line.dxf, 'handle', 'unknown')}"))
                removed_entities.add(add_line)
            
        if found_AD1 and found_AD1 not in removed_entities:
            to_remove.append((found_AD1, f"AD1: {getattr(found_AD1.dxf, 'handle', 'unknown')}"))
            removed_entities.add(found_AD1)
        
        # DEL1 LINE들 삭제 목록에 추가
        for i, line in enumerate(del1_lines):
            if line not in removed_entities:
                to_remove.append((line, f"DEL1-{i+1}: {getattr(line.dxf, 'handle', 'unknown')}"))
                removed_entities.add(line)
            
        # 7. AD1의 어느 한점과 접하는 1mm 이하의 ARROW 레이어 LINE 삭제
        if found_AD1:
            ad1_start = Vec2(found_AD1.dxf.start.x, found_AD1.dxf.start.y)
            ad1_end = Vec2(found_AD1.dxf.end.x, found_AD1.dxf.end.y)
            ad1_points = [ad1_start, ad1_end]
            
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

    # 8. FLBOX와 FL_BOX 레이어 삭제
    print(f"\n   ========== FLBOX 및 FL_BOX 삭제 ==========")
    
    flbox_count = 0
    fl_box_count = 0
    
    # 삭제할 엔티티 수집 (iterator 문제 방지)
    entities_to_delete = []
    
    for entity in msp:
        if entity.dxftype() == 'LINE':
            if entity.dxf.layer == "FLBOX":
                entities_to_delete.append(entity)
                flbox_count += 1
            elif entity.dxf.layer == "FL_BOX":
                entities_to_delete.append(entity)
                fl_box_count += 1
    
    # 엔티티 삭제
    for entity in entities_to_delete:
        try:
            msp.delete_entity(entity)
        except Exception as e:
            print(f"   [삭제 오류] {e}")
    
    print(f"   [FLBOX 삭제] 총 {flbox_count}개 FLBOX LINE 삭제 (CYAN 색상)")
    print(f"   [FL_BOX 삭제] 총 {fl_box_count}개 FL_BOX LINE 삭제 (MAGENTA 색상)")
    
    print(f"\n   ========== 처리 결과 ==========")
    print(f"   [처리 완료] 총 {processed_count}개 FL/EL TEXT 처리됨")

    save_path = os.path.splitext(file_path)[0] + "_ELEDIT.dxf"
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