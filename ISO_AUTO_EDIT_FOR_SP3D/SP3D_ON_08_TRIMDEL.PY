import ezdxf
import os
import sys
import glob
import math
from ezdxf.math import Vec2


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
        except Exception:
            pass
        return Vec2(0.0, 0.0)

    @staticmethod
    def get_text_bbox(text):
        """
        TEXT 엔티티의 경계 상자 계산
        BOX 높이 = TEXT 높이 + 0.3 (2.2 + 0.3 = 2.5mm)
        """
        pos = TextBoxLineFinder.get_text_position(text)
        height = getattr(text.dxf, 'height', 2.2)
        text_len = len(text.dxf.text) * height * 0.8
        rotation = getattr(text.dxf, 'rotation', 0)
        return {
            'min_x': pos.x,
            'max_x': pos.x + text_len,
            'min_y': pos.y - 0.15,
            'max_y': pos.y + height + 0.15,
            'rotation': rotation,
            'pos': pos
        }

    @staticmethod
    def get_text_reference_points(text, num_points=3):
        """TEXT BOX의 참조점들을 계산"""
        bbox = TextBoxLineFinder.get_text_bbox(text)
        pos = bbox['pos']
        rotation = bbox.get('rotation', 0)
        rotation_rad = math.radians(rotation)

        if num_points == 3:
            points = [
                Vec2(bbox['min_x'], pos.y),
                Vec2((bbox['min_x'] + bbox['max_x']) / 2, pos.y),
                Vec2(bbox['max_x'], pos.y)
            ]
        else:
            points = []
            for i in range(num_points):
                ratio = i / (num_points - 1) if num_points > 1 else 0
                x = bbox['min_x'] + (bbox['max_x'] - bbox['min_x']) * ratio
                points.append(Vec2(x, pos.y))

        if abs(rotation) > 0.01:
            rotated_points = []
            cos_r = math.cos(rotation_rad)
            sin_r = math.sin(rotation_rad)
            for pt in points:
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
        return math.hypot(p2.x - p1.x, p2.y - p1.y)

    @staticmethod
    def get_line_length(line):
        if line.dxftype() == "LINE":
            start = Vec2(line.dxf.start.x, line.dxf.start.y)
            end = Vec2(line.dxf.end.x, line.dxf.end.y)
            return TextBoxLineFinder.distance(start, end)
        return 0

    @staticmethod
    def find_closest_line_to_text(
        text,
        lines,
        exclude_entities=None,
        exclude_layers=None,
        min_length=None,
        max_distance=None,
        debug=False
    ):
        """TEXT BOX에서 가장 가까운 LINE 찾기"""
        if exclude_entities is None:
            exclude_entities = []
        if exclude_layers is None:
            exclude_layers = []

        exclude_layers_upper = [layer.upper() for layer in exclude_layers]
        ref_points = TextBoxLineFinder.get_text_reference_points(text)
        text_center = TextBoxLineFinder.get_text_position(text)

        found_line = None
        closest_point = None
        farthest_point = None
        min_dist = float("inf")

        for line in lines:
            if line in exclude_entities:
                continue
            if line.dxftype() != 'LINE':
                continue
            if line.dxf.layer.upper() in exclude_layers_upper:
                continue
            if max_distance is not None:
                line_center = Vec2(
                    (line.dxf.start.x + line.dxf.end.x) / 2,
                    (line.dxf.start.y + line.dxf.end.y) / 2
                )
                if TextBoxLineFinder.distance(text_center, line_center) > max_distance:
                    continue
            if min_length is not None:
                line_len = TextBoxLineFinder.get_line_length(line)
                if line_len < min_length:
                    continue

            start = Vec2(line.dxf.start.x, line.dxf.start.y)
            end = Vec2(line.dxf.end.x, line.dxf.end.y)

            distances = []
            for ref_point in ref_points:
                distances.append(TextBoxLineFinder.distance(start, ref_point))
                distances.append(TextBoxLineFinder.distance(end, ref_point))

            min_pt_dist = min(distances)
            if min_pt_dist < min_dist:
                min_dist = min_pt_dist
                found_line = line
                min_idx = distances.index(min_pt_dist)
                if min_idx % 2 == 0:
                    closest_point = start
                    farthest_point = end
                else:
                    closest_point = end
                    farthest_point = start

        return found_line, closest_point, farthest_point


class TrimProcessor:
    """TRIM 텍스트 처리 클래스"""
    
    def __init__(self):
        self.entities_to_delete = []
        self.used_a1_lines = []
        self.trim_count = 0
        
    def distance(self, p1, p2):
        return math.hypot(p2.x - p1.x, p2.y - p1.y)

    def get_text_position(self, text):
        return TextBoxLineFinder.get_text_position(text)

    def get_line_length(self, line):
        return TextBoxLineFinder.get_line_length(line)

    def find_connected_lines(self, start_line, msp, exclude_layers, used_lines, tolerance=0.1, max_lines=10):
        """시작 LINE에서 연결된 LINE들을 찾아 연속된 경로 구성"""
        connected_lines = [start_line]
        used_lines_set = set(used_lines)
        used_lines_set.add(start_line)

        exclude_layers_upper = [layer.upper() for layer in exclude_layers]

        for direction in ['forward', 'backward']:
            current_line = start_line
            while len(connected_lines) < max_lines:
                if direction == 'forward':
                    search_point = Vec2(current_line.dxf.end.x, current_line.dxf.end.y)
                else:
                    search_point = Vec2(current_line.dxf.start.x, current_line.dxf.start.y)

                found_next = None
                for line in msp.query('LINE'):
                    if line in used_lines_set:
                        continue
                    if line.dxf.layer.upper() in exclude_layers_upper:
                        continue

                    start = Vec2(line.dxf.start.x, line.dxf.start.y)
                    end = Vec2(line.dxf.end.x, line.dxf.end.y)

                    if self.distance(start, search_point) <= tolerance:
                        found_next = line
                        if direction == 'forward':
                            connected_lines.append(line)
                        else:
                            connected_lines.insert(0, line)
                        break
                    elif self.distance(end, search_point) <= tolerance:
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
                    break

        return connected_lines

    def get_connected_line_endpoints(self, connected_lines, ref_center):
        """연결된 LINE들에서 기준점에 가장 가까운 점(AP1)과 가장 먼 점(AP2) 찾기"""
        all_points = []
        for line in connected_lines:
            start = Vec2(line.dxf.start.x, line.dxf.start.y)
            end = Vec2(line.dxf.end.x, line.dxf.end.y)
            all_points.append(start)
            all_points.append(end)

        if not all_points:
            return None, None

        unique_points = []
        for pt in all_points:
            is_duplicate = False
            for upt in unique_points:
                if self.distance(pt, upt) < 0.1:
                    is_duplicate = True
                    break
            if not is_duplicate:
                unique_points.append(pt)

        min_dist = float('inf')
        max_dist = 0
        closest_point = None
        farthest_point = None

        for pt in unique_points:
            dist = self.distance(ref_center, pt)
            if dist < min_dist:
                min_dist = dist
                closest_point = pt
            if dist > max_dist:
                max_dist = dist
                farthest_point = pt

        return closest_point, farthest_point

    def process(self, doc):
        """
        In-memory DXF document 처리 (런너 연동용)
        
        Args:
            doc: ezdxf.document.Drawing 객체
            
        Returns:
            tuple: (success: bool, message: str, stats: dict)
        """
        try:
            # 초기화
            self.entities_to_delete = []
            self.used_a1_lines = []
            self.trim_count = 0
            
            msp = doc.modelspace()
            
            # TRIM 텍스트 처리
            for tr_text in msp.query('TEXT'):
                if 'TRIM' not in tr_text.dxf.text.upper():
                    continue

                tr_pos = self.get_text_position(tr_text)
                self.trim_count += 1

                self.entities_to_delete.append(tr_text)

                exclude_layers_for_a1 = ['FRAME', 'DL', 'AD1', 'DIM', 'ITNO', 'ITEMPOS']
                exclude_entities_for_a1 = self.used_a1_lines

                found_A1, AP1, AP2 = TextBoxLineFinder.find_closest_line_to_text(
                    text=tr_text,
                    lines=msp.query('LINE'),
                    exclude_entities=exclude_entities_for_a1,
                    exclude_layers=exclude_layers_for_a1,
                    min_length=None,
                    max_distance=35.0,
                    debug=False
                )

                if not found_A1:
                    continue

                connected_lines = self.find_connected_lines(
                    start_line=found_A1,
                    msp=msp,
                    exclude_layers=exclude_layers_for_a1,
                    used_lines=self.used_a1_lines,
                    tolerance=0.1,
                    max_lines=10
                )

                all_a1_lines = connected_lines

                new_AP1, new_AP2 = self.get_connected_line_endpoints(all_a1_lines, tr_pos)
                if new_AP1 and new_AP2:
                    AP1 = new_AP1
                    AP2 = new_AP2

                for line in all_a1_lines:
                    self.entities_to_delete.append(line)
                    if line not in self.used_a1_lines:
                        self.used_a1_lines.append(line)

                del1_lines = []
                all_endpoints = []
                for line in all_a1_lines:
                    start = Vec2(line.dxf.start.x, line.dxf.start.y)
                    end = Vec2(line.dxf.end.x, line.dxf.end.y)
                    all_endpoints.append(start)
                    all_endpoints.append(end)

                unique_endpoints = []
                for pt in all_endpoints:
                    is_duplicate = False
                    for upt in unique_endpoints:
                        if self.distance(pt, upt) < 0.1:
                            is_duplicate = True
                            break
                    if not is_duplicate:
                        unique_endpoints.append(pt)

                for line in msp.query('LINE'):
                    if line in all_a1_lines:
                        continue
                    if line.dxf.layer.upper() in ["FRAME", "ITNO", "ITEMPOS"]:
                        continue

                    line_len = self.get_line_length(line)
                    if line_len > 2.0:
                        continue

                    start = Vec2(line.dxf.start.x, line.dxf.start.y)
                    end = Vec2(line.dxf.end.x, line.dxf.end.y)

                    for endpoint in unique_endpoints:
                        if self.distance(start, endpoint) <= 2.0 or self.distance(end, endpoint) <= 2.0:
                            del1_lines.append(line)
                            break

                    if len(del1_lines) >= 3:
                        break

                for line in del1_lines:
                    self.entities_to_delete.append(line)

            # 엔티티 삭제
            deleted_count = 0
            if self.entities_to_delete:
                for entity in self.entities_to_delete:
                    try:
                        msp.delete_entity(entity)
                        deleted_count += 1
                    except Exception:
                        pass
            
            # 통계 정보
            stats = {
                'trim_count': self.trim_count,
                'deleted_entities': deleted_count,
                'a1_lines': len(self.used_a1_lines),
                'total_entities_marked': len(self.entities_to_delete)
            }
            
            message = f"처리 완료: {self.trim_count}개 TRIM 텍스트 발견, {deleted_count}개 엔티티 삭제"
            
            return True, message, stats
            
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            return False, f"처리 중 오류 발생: {str(e)}", {'error': error_detail}

    def process_file(self, file_path):
        """파일 기반 처리 (기존 방식)"""
        try:
            doc = ezdxf.readfile(file_path)
        except Exception as e:
            return False, f"파일 읽기 실패: {str(e)}"

        # In-memory 처리 실행
        success, message, stats = self.process(doc)
        
        if success:
            # 파일 저장
            save_path = os.path.splitext(file_path)[0] + "_TRIMD.dxf"
            try:
                doc.saveas(save_path)
                return True, f"파일 저장 완료: {save_path}"
            except Exception as e:
                return False, f"파일 저장 실패: {str(e)}"
        else:
            return success, message


# 전역 함수들 (기존 코드 호환성 유지)
def distance(p1, p2):
    return math.hypot(p2.x - p1.x, p2.y - p1.y)

def get_text_position(text):
    return TextBoxLineFinder.get_text_position(text)

def get_line_length(line):
    return TextBoxLineFinder.get_line_length(line)

def process_dxf(file_path):
    """DXF 파일 처리 메인 함수 (기존 호환성 유지)"""
    processor = TrimProcessor()
    processor.process_file(file_path)

def _expand_cli_paths(argv):
    """쉘 와일드카드와 중복/비존재 파일을 정리"""
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


# 스텝 시스템을 위한 전역 processor 인스턴스
_global_processor = None

def get_processor():
    """전역 processor 인스턴스 반환 (싱글톤 패턴)"""
    global _global_processor
    if _global_processor is None:
        _global_processor = TrimProcessor()
    return _global_processor


# 스텝 파일 시스템용 엔트리 포인트
def step_entry(doc):
    """
    스텝 파일 시스템 엔트리 포인트
    
    Args:
        doc: ezdxf.document.Drawing 객체
        
    Returns:
        tuple: (success: bool, message: str, stats: dict)
    """
    processor = get_processor()
    return processor.process(doc)

# 대체 엔트리 포인트 이름들
def step_process(doc):
    """스텝 프로세스 엔트리 포인트"""
    return step_entry(doc)

def step_run(doc):
    """스텝 런 엔트리 포인트"""
    return step_entry(doc)

def step():
    """인자 없는 스텝 엔트리 포인트"""
    if 'doc' in globals():
        return step_entry(globals()['doc'])
    else:
        return False, "No document provided", {}

def process(doc):
    """전역 process 함수"""
    return step_entry(doc)

def run(doc):
    """전역 run 함수"""
    return step_entry(doc)


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        sys.exit(0)
    files = _expand_cli_paths(args)
    for f in files:
        process_dxf(f)