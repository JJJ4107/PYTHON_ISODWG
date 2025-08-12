import ezdxf
import os
import math
from ezdxf.math import Vec2
from tkinter import Tk, filedialog


class TextBoxLineFinder:
    """TEXT를 BOX화하여 가장 가까운 LINE을 찾는 유틸리티 클래스"""
    
    def __init__(self):
        pass
    
    @staticmethod
    def get_text_position(text):
        """TEXT 엔티티의 위치를 Vec2로 반환"""
        try:
            if hasattr(text.dxf, "insert"):
                ins = text.dxf.insert
                if hasattr(ins, '__getitem__'):
                    return Vec2(float(ins[0]), float(ins[1]))
                elif hasattr(ins, 'x') and hasattr(ins, 'y'):
                    return Vec2(float(ins.x), float(ins.y))
                else:
                    return Vec2(float(ins), 0)
            
            if hasattr(text.dxf, "location"):
                loc = text.dxf.location
                if hasattr(loc, '__getitem__') and len(loc) >= 2:
                    return Vec2(float(loc[0]), float(loc[1]))
                elif hasattr(loc, 'x') and hasattr(loc, 'y'):
                    return Vec2(float(loc.x), float(loc.y))
                    
        except Exception as e:
            print(f"   [경고] TEXT 위치 가져오기 오류: {e}")
        
        return Vec2(0.0, 0.0)
    
    @staticmethod
    def get_text_bbox(text):
        """
        TEXT 엔티티의 경계 상자 계산
        BOX 높이 = TEXT 높이 + 0.3 (2.2 + 0.3 = 2.5mm)
        """
        pos = TextBoxLineFinder.get_text_position(text)
        # TEXT 높이 가져오기 (기본값 2.2mm)
        height = getattr(text.dxf, 'height', 2.2)
        # 텍스트 길이를 대략적으로 계산 (문자 수 * 높이 * 0.8)
        text_len = len(text.dxf.text) * height * 0.8
        
        # BOX 높이는 TEXT 높이 + 0.3
        box_height = height + 0.3
        
        # TEXT의 현재 회전 각도 가져오기
        rotation = getattr(text.dxf, 'rotation', 0)
        
        # 회전되지 않은 상태의 BOX (TEXT 원점 기준)
        return {
            'min_x': pos.x,
            'max_x': pos.x + text_len,
            'min_y': pos.y - 0.15,  # 아래로 0.15
            'max_y': pos.y + height + 0.15,  # 위로 height + 0.15
            'rotation': rotation,  # TEXT의 회전 각도 포함
            'pos': pos  # TEXT의 위치 (회전 중심점)
        }
    
    @staticmethod
    def get_text_reference_points(text, num_points=3):
        """TEXT BOX의 참조점들을 계산"""
        bbox = TextBoxLineFinder.get_text_bbox(text)
        pos = bbox['pos']
        
        # 회전을 고려한 참조점 계산
        rotation = bbox.get('rotation', 0)
        rotation_rad = math.radians(rotation)
        
        if num_points == 3:
            # 회전되지 않은 상태의 점들
            points = [
                Vec2(bbox['min_x'], pos.y),  # 좌측
                Vec2((bbox['min_x'] + bbox['max_x']) / 2, pos.y),  # 중앙
                Vec2(bbox['max_x'], pos.y)  # 우측
            ]
        else:
            points = []
            for i in range(num_points):
                ratio = i / (num_points - 1) if num_points > 1 else 0
                x = bbox['min_x'] + (bbox['max_x'] - bbox['min_x']) * ratio
                points.append(Vec2(x, pos.y))
        
        # 회전 적용
        if abs(rotation) > 0.01:
            rotated_points = []
            cos_r = math.cos(rotation_rad)
            sin_r = math.sin(rotation_rad)
            
            for pt in points:
                # pos를 중심으로 회전
                dx = pt.x - pos.x
                dy = pt.y - pos.y
                rx = dx * cos_r - dy * sin_r + pos.x
                ry = dx * sin_r + dy * cos_r + pos.y
                rotated_points.append(Vec2(rx, ry))
            
            return rotated_points
        else:
            return points
    
    @staticmethod
    def distance(p1, p2):
        """두 점 사이의 거리 계산"""
        return math.hypot(p2.x - p1.x, p2.y - p1.y)
    
    @staticmethod
    def get_line_length(line):
        """LINE의 길이 계산"""
        if line.dxftype() == "LINE":
            start = Vec2(line.dxf.start.x, line.dxf.start.y)
            end = Vec2(line.dxf.end.x, line.dxf.end.y)
            return TextBoxLineFinder.distance(start, end)
        return 0
    
    @staticmethod
    def find_closest_line_to_text(text, lines, exclude_entities=None, exclude_layers=None, 
                                  min_length=None, max_distance=None, debug=False):
        """TEXT BOX에서 가장 가까운 LINE 찾기"""
        if exclude_entities is None:
            exclude_entities = []
        if exclude_layers is None:
            exclude_layers = []
        
        exclude_layers_upper = [layer.upper() for layer in exclude_layers]
        
        # TEXT의 참조점들 계산
        ref_points = TextBoxLineFinder.get_text_reference_points(text)
        text_center = TextBoxLineFinder.get_text_position(text)
        
        if debug:
            print(f"\n   [TEXT BOX 분석] TEXT: '{text.dxf.text}'")
            print(f"   회전: {getattr(text.dxf, 'rotation', 0):.1f}°")
            for i, pt in enumerate(ref_points):
                print(f"   참조점{i+1}: ({pt.x:.2f}, {pt.y:.2f})")
        
        found_line = None
        closest_point = None
        farthest_point = None
        min_dist = float("inf")
        
        lines_checked = 0
        
        for line in lines:
            if line in exclude_entities:
                continue
                
            if line.dxftype() != 'LINE':
                continue
                
            if line.dxf.layer.upper() in exclude_layers_upper:
                continue
            
            # 최대 거리 제한
            if max_distance is not None:
                line_center = Vec2((line.dxf.start.x + line.dxf.end.x) / 2,
                                 (line.dxf.start.y + line.dxf.end.y) / 2)
                if TextBoxLineFinder.distance(text_center, line_center) > max_distance:
                    continue
            
            # 길이 확인
            if min_length is not None:
                line_len = TextBoxLineFinder.get_line_length(line)
                if line_len < min_length:
                    continue
            
            lines_checked += 1
            
            # LINE의 끝점들
            start = Vec2(line.dxf.start.x, line.dxf.start.y)
            end = Vec2(line.dxf.end.x, line.dxf.end.y)
            
            # 모든 참조점에서 LINE의 각 끝점까지 거리 계산
            distances = []
            for ref_point in ref_points:
                distances.append(TextBoxLineFinder.distance(start, ref_point))
                distances.append(TextBoxLineFinder.distance(end, ref_point))
            
            min_pt_dist = min(distances)
            
            if min_pt_dist < min_dist:
                min_dist = min_pt_dist
                found_line = line
                
                # 어느 점이 가장 가까운지 확인
                min_idx = distances.index(min_pt_dist)
                
                if min_idx % 2 == 0:  # start점이 더 가까움
                    closest_point = start
                    farthest_point = end
                else:  # end점이 더 가까움
                    closest_point = end
                    farthest_point = start
        
        if debug:
            print(f"   검사한 LINE 수: {lines_checked}개")
            if found_line:
                print(f"   가장 가까운 LINE: (거리: {min_dist:.2f}mm)")
                print(f"   가까운 점: ({closest_point.x:.2f}, {closest_point.y:.2f})")
                print(f"   먼 점: ({farthest_point.x:.2f}, {farthest_point.y:.2f})")
            else:
                print(f"   결과: 적합한 LINE을 찾을 수 없음")
        
        return found_line, closest_point, farthest_point


def select_files():
    """파일 선택 대화상자"""
    Tk().withdraw()
    return filedialog.askopenfilenames(
        title="DXF 파일 선택 (여러 개 가능)",
        filetypes=[("DXF files", "*.dxf")])


def distance(p1, p2):
    """두 점 사이의 거리 계산"""
    return math.hypot(p2.x - p1.x, p2.y - p1.y)


def get_text_position(text):
    """TEXT 엔티티의 위치를 Vec2로 반환"""
    return TextBoxLineFinder.get_text_position(text)


def get_line_length(line):
    """LINE의 길이 계산"""
    return TextBoxLineFinder.get_line_length(line)


def find_connected_lines(start_line, msp, exclude_layers, used_lines, tolerance=0.1, max_lines=10):
    """시작 LINE에서 연결된 LINE들을 찾아 연속된 경로 구성"""
    connected_lines = [start_line]
    used_lines_set = set(used_lines)
    used_lines_set.add(start_line)
    
    exclude_layers_upper = [layer.upper() for layer in exclude_layers]
    
    # 양쪽 방향으로 확장
    for direction in ['forward', 'backward']:
        current_line = start_line
        
        while len(connected_lines) < max_lines:
            # 현재 LINE의 끝점 찾기
            if direction == 'forward':
                search_point = Vec2(current_line.dxf.end.x, current_line.dxf.end.y)
            else:
                search_point = Vec2(current_line.dxf.start.x, current_line.dxf.start.y)
            
            # 연결된 LINE 찾기
            found_next = None
            for line in msp.query('LINE'):
                if line in used_lines_set:
                    continue
                    
                if line.dxf.layer.upper() in exclude_layers_upper:
                    continue
                
                start = Vec2(line.dxf.start.x, line.dxf.start.y)
                end = Vec2(line.dxf.end.x, line.dxf.end.y)
                
                # 연결점 확인 (tolerance 이내)
                if distance(start, search_point) <= tolerance:
                    found_next = line
                    if direction == 'forward':
                        connected_lines.append(line)
                    else:
                        connected_lines.insert(0, line)
                    break
                elif distance(end, search_point) <= tolerance:
                    found_next = line
                    if direction == 'forward':
                        connected_lines.append(line)
                    else:
                        connected_lines.insert(0, line)
                    break
            
            if found_next:
                used_lines_set.add(found_next)
                current_line = found_next
            else:
                break  # 더 이상 연결된 LINE이 없음
    
    return connected_lines


def get_connected_line_endpoints(connected_lines, ref_center):
    """연결된 LINE들에서 기준점에 가장 가까운 점(AP1)과 가장 먼 점(AP2) 찾기"""
    all_points = []
    
    # 모든 LINE의 끝점 수집
    for line in connected_lines:
        start = Vec2(line.dxf.start.x, line.dxf.start.y)
        end = Vec2(line.dxf.end.x, line.dxf.end.y)
        all_points.append(start)
        all_points.append(end)
    
    if not all_points:
        return None, None
    
    # 중복 제거 (매우 가까운 점들은 같은 점으로 처리)
    unique_points = []
    for pt in all_points:
        is_duplicate = False
        for upt in unique_points:
            if distance(pt, upt) < 0.1:
                is_duplicate = True
                break
        if not is_duplicate:
            unique_points.append(pt)
    
    # 기준점에서 가장 가까운 점과 가장 먼 점 찾기
    min_dist = float('inf')
    max_dist = 0
    closest_point = None
    farthest_point = None
    
    for pt in unique_points:
        dist = distance(ref_center, pt)
        if dist < min_dist:
            min_dist = dist
            closest_point = pt
        if dist > max_dist:
            max_dist = dist
            farthest_point = pt
    
    return closest_point, farthest_point


def process_dxf(file_path):
    """DXF 파일 처리 메인 함수"""
    try:
        doc = ezdxf.readfile(file_path)
    except Exception as e:
        print(f"파일 열기 실패: {file_path} / {e}")
        return

    msp = doc.modelspace()
    
    # 삭제할 엔티티들을 저장할 리스트
    entities_to_delete = []
    
    # 이미 사용된 A1 LINE들을 추적
    used_a1_lines = []
    
    # 처리된 TRIM TEXT 개수
    trim_count = 0

    # 모든 TEXT에서 'TRIM'이 포함된 것 찾기
    for tr_text in msp.query('TEXT'):
        # TRIM이 포함되지 않으면 제외
        if 'TRIM' not in tr_text.dxf.text.upper():
            continue
            
        tr_pos = get_text_position(tr_text)
        print(f"\n[TRIM TEXT 발견] '{tr_text.dxf.text}' 위치: ({tr_pos.x:.2f}, {tr_pos.y:.2f})")
        trim_count += 1
        
        # TR TEXT를 삭제 목록에 추가
        entities_to_delete.append(tr_text)

        # A1 찾기 - TR TEXT BOX 기준
        print(f"   [A1 찾기] TRIM TEXT BOX에서 가장 가까운 LINE 검색 (35mm 이내)")
        
        # A1이 될 수 없는 레이어들
        exclude_layers_for_a1 = ['FRAME', 'DL', 'AD1', 'DIM', 'ITNO', 'ITEMPOS']
        
        # 제외할 엔티티 목록 (이미 선택된 A1들)
        exclude_entities_for_a1 = used_a1_lines
        
        found_A1, AP1, AP2 = TextBoxLineFinder.find_closest_line_to_text(
            text=tr_text,
            lines=msp.query('LINE'),
            exclude_entities=exclude_entities_for_a1,
            exclude_layers=exclude_layers_for_a1,
            min_length=None,
            max_distance=35.0,
            debug=True
        )
        
        if not found_A1:
            print(f"   [A1 없음] TRIM TEXT BOX에서 가장 가까운 LINE을 찾을 수 없습니다")
            continue
        
        # 연속라인 찾기
        print(f"   [연속라인 찾기] A1에서 연결된 LINE 검색")
        connected_lines = find_connected_lines(
            start_line=found_A1,
            msp=msp,
            exclude_layers=exclude_layers_for_a1,
            used_lines=used_a1_lines,
            tolerance=0.1,
            max_lines=10
        )
        
        print(f"   - 연결된 LINE 수: {len(connected_lines)}개")
        
        # 연결된 모든 LINE을 A1 그룹으로 처리
        all_a1_lines = connected_lines
        
        # 연속된 LINE들에서 AP1, AP2 재계산
        new_AP1, new_AP2 = get_connected_line_endpoints(all_a1_lines, tr_pos)
        if new_AP1 and new_AP2:
            AP1 = new_AP1
            AP2 = new_AP2
            print(f"   - 연속라인 전체 길이 기준 AP1: ({AP1.x:.2f}, {AP1.y:.2f})")
            print(f"   - 연속라인 전체 길이 기준 AP2: ({AP2.x:.2f}, {AP2.y:.2f})")
        
        # 모든 연결된 LINE을 삭제 목록에 추가하고 사용된 목록에 추가
        for line in all_a1_lines:
            entities_to_delete.append(line)
            if line not in used_a1_lines:
                used_a1_lines.append(line)
        
        # 주 A1 LINE 정보 출력
        line_len = get_line_length(found_A1)
        total_a1_length = distance(AP1, AP2)
        print(f"   [A1] 주 LINE (길이: {line_len:.2f}mm)")
        print(f"   - 연속라인 전체 길이: {total_a1_length:.2f}mm (AP1~AP2)")
        print(f"   - A1 LINE {len(all_a1_lines)}개를 삭제 목록에 추가")

        # DEL1 찾기: 연속된 A1의 모든 끝점에서 2mm 이내 접하는 2mm 이하 LINE 3개
        del1_lines = []
        
        # 연속된 A1의 모든 끝점 수집
        all_endpoints = []
        for line in all_a1_lines:
            start = Vec2(line.dxf.start.x, line.dxf.start.y)
            end = Vec2(line.dxf.end.x, line.dxf.end.y)
            all_endpoints.append(start)
            all_endpoints.append(end)
        
        # 중복 제거
        unique_endpoints = []
        for pt in all_endpoints:
            is_duplicate = False
            for upt in unique_endpoints:
                if distance(pt, upt) < 0.1:
                    is_duplicate = True
                    break
            if not is_duplicate:
                unique_endpoints.append(pt)
        
        print(f"   [DEL1 찾기] A1 끝점 {len(unique_endpoints)}개에서 2mm 이내 LINE 검색")
        
        for line in msp.query('LINE'):
            if line in all_a1_lines:
                continue
            if line.dxf.layer.upper() in ["FRAME", "ITNO", "ITEMPOS"]:
                continue
                
            line_len = get_line_length(line)
            if line_len > 2.0:
                continue
            
            start = Vec2(line.dxf.start.x, line.dxf.start.y)
            end = Vec2(line.dxf.end.x, line.dxf.end.y)
            
            for endpoint in unique_endpoints:
                if distance(start, endpoint) <= 2.0 or distance(end, endpoint) <= 2.0:
                    del1_lines.append(line)
                    break
            
            if len(del1_lines) >= 3:
                break
        
        # DEL1을 삭제 목록에 추가
        for i, line in enumerate(del1_lines):
            entities_to_delete.append(line)
            print(f"   [DEL1-{i+1}] LINE 삭제 목록에 추가")
        
        print(f"   [DEL1] {len(del1_lines)}개 LINE을 삭제 목록에 추가")

    # 모든 엔티티 삭제 실행
    if entities_to_delete:
        print(f"\n========== 삭제 실행 ==========")
        print(f"총 {len(entities_to_delete)}개 엔티티 삭제 중...")
        
        for entity in entities_to_delete:
            try:
                msp.delete_entity(entity)
            except Exception as e:
                print(f"삭제 오류: {e}")
        
        print(f"삭제 완료!")
    else:
        print(f"\n삭제할 엔티티가 없습니다.")

    # 파일 저장
    save_path = os.path.splitext(file_path)[0] + "TRIMDEL.dxf"
    try:
        doc.saveas(save_path)
        print(f"\n[✔] 저장 완료: {os.path.basename(save_path)}")
        print(f"[✔] 처리된 TRIM TEXT 수: {trim_count}개")
    except Exception as e:
        print(f"[!] 저장 오류: {e}")


if __name__ == "__main__":
    files = select_files()
    if not files:
        print("❗ DXF 파일을 선택하지 않았습니다.")
    else:
        for f in files:
            print(f"\n{'='*60}")
            print(f"파일 처리: {os.path.basename(f)}")
            print(f"{'='*60}")
            process_dxf(f)
        print("\n▶ 모든 파일 처리 완료.")