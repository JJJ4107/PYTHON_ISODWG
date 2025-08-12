import math
from ezdxf.math import Vec3

class A1LineFinder:
    """A1 및 연속된 A1-1 라인을 찾는 클래스"""
    
    def __init__(self):
        self.used_lines = set()  # 이미 사용된 라인 추적
    
    def get_distance(self, p1, p2):
        """두 점 사이의 거리 계산"""
        return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)
    
    def get_line_angle(self, start, end):
        """라인의 각도를 계산 (0~360도)"""
        dx = end.x - start.x
        dy = end.y - start.y
        
        # 라디안을 도로 변환
        angle = math.atan2(dy, dx) * 180 / math.pi
        
        # 0~360도로 정규화
        if angle < 0:
            angle += 360
            
        return angle
    
    def find_a1_from_reference_points(self, msp, reference_points, max_distance=7.0, 
                                     search_layers=["DIMLINES", "ISOTEXT"],
                                     exclude_layers=["PIPE", "FITTINGS", "WELDS"],
                                     min_length=2.2):
        """
        기준점들(예: DBOX 중심점들)에서 가장 가까운 A1 라인 찾기
        
        Parameters:
        - msp: 모델 스페이스
        - reference_points: 기준점 리스트 (예: DBOX 각 선분의 중심점)
        - max_distance: 최대 검색 거리
        - search_layers: 검색할 레이어 리스트
        - exclude_layers: 제외할 레이어 리스트
        - min_length: 최소 라인 길이
        
        Returns:
        - (a1_lines, a1_info) 튜플
        """
        
        # A1 후보들 수집
        candidates = []
        
        # 지정된 레이어에서 검색
        for layer in search_layers:
            for entity in msp.query(f'LINE[layer=="{layer}"]'):
                # 제외 레이어 확인
                if entity.dxf.layer in exclude_layers:
                    continue
                
                # 이미 사용된 라인 제외
                if entity in self.used_lines:
                    continue
                    
                start = Vec3(entity.dxf.start)
                end = Vec3(entity.dxf.end)
                
                # 최소 길이 확인
                length = (end - start).magnitude
                if length < min_length:
                    continue
                
                # 각 기준점에 대해 거리 계산
                for ref_point in reference_points:
                    # 라인의 시작점 또는 끝점과 기준점 사이의 거리
                    dist_start = self.get_distance(start, ref_point)
                    dist_end = self.get_distance(end, ref_point)
                    
                    if dist_start <= max_distance:
                        candidates.append({
                            'line': entity,
                            'distance': dist_start,
                            'reference_point': ref_point,
                            'closest_point': "start"
                        })
                    
                    if dist_end <= max_distance:
                        candidates.append({
                            'line': entity,
                            'distance': dist_end,
                            'reference_point': ref_point,
                            'closest_point': "end"
                        })
        
        if not candidates:
            return None, None
        
        # 거리순으로 정렬하여 가장 가까운 것 선택
        candidates.sort(key=lambda x: x['distance'])
        best_candidate = candidates[0]
        
        # 선택된 A1 라인
        a1_line = best_candidate['line']
        self.used_lines.add(a1_line)
        
        # A1 라인 리스트 (첫 번째는 A1, 나머지는 A1-1)
        a1_lines = [a1_line]
        
        # 연속된 라인들 찾기
        continuous_lines = self.find_continuous_lines(
            msp, a1_line, 
            max_distance=8.0,  # 연결 거리
            angle_tolerance=1.0,  # 각도 허용 오차
            search_layers=search_layers,
            exclude_layers=exclude_layers,
            min_length=min_length
        )
        
        # 연속된 라인들을 A1-1로 추가
        for line in continuous_lines:
            if line not in a1_lines:
                a1_lines.append(line)
                self.used_lines.add(line)
        
        # 정보 반환
        a1_info = {
            'first_a1': a1_line,
            'reference_point': best_candidate['reference_point'],
            'closest_point': best_candidate['closest_point'],
            'distance': best_candidate['distance'],
            'total_count': len(a1_lines),
            'a1_count': 1,
            'a1_1_count': len(a1_lines) - 1
        }
        
        return a1_lines, a1_info
    
    def find_continuous_lines(self, msp, base_line, max_distance=8.0, angle_tolerance=1.0,
                            search_layers=["DIMLINES", "ISOTEXT"],
                            exclude_layers=["PIPE", "FITTINGS", "WELDS"],
                            min_length=2.2):
        """기준 라인과 연속된 라인들을 찾기"""
        continuous_lines = []
        
        # 기준 라인의 각도 계산
        base_start = Vec3(base_line.dxf.start)
        base_end = Vec3(base_line.dxf.end)
        base_angle = self.get_line_angle(base_start, base_end)
        
        # 방문한 라인 추적
        visited = set([base_line])
        
        # 재귀적으로 연속된 라인 찾기
        self._find_continuous_from_endpoints(
            msp, base_line, base_angle, max_distance, 
            angle_tolerance, continuous_lines, visited,
            search_layers, exclude_layers, min_length
        )
        
        return continuous_lines
    
    def _find_continuous_from_endpoints(self, msp, current_line, base_angle, max_distance, 
                                      angle_tolerance, continuous_lines, visited,
                                      search_layers, exclude_layers, min_length):
        """현재 라인의 양 끝점에서 연속된 라인 찾기 (재귀)"""
        current_start = Vec3(current_line.dxf.start)
        current_end = Vec3(current_line.dxf.end)
        
        # 지정된 레이어에서 검색
        for layer in search_layers:
            for entity in msp.query(f'LINE[layer=="{layer}"]'):
                # 이미 방문했거나 사용된 라인은 제외
                if entity in visited or entity in self.used_lines:
                    continue
                
                # 제외 레이어 확인
                if entity.dxf.layer in exclude_layers:
                    continue
                
                line_start = Vec3(entity.dxf.start)
                line_end = Vec3(entity.dxf.end)
                
                # 최소 길이 확인
                length = (line_end - line_start).magnitude
                if length < min_length:
                    continue
                
                # 현재 라인의 끝점과 다음 라인의 시작점/끝점 사이 거리 확인
                connections = [
                    (current_end, line_start),
                    (current_end, line_end),
                    (current_start, line_start),
                    (current_start, line_end)
                ]
                
                for point1, point2 in connections:
                    dist = self.get_distance(point1, point2)
                    if dist <= max_distance:
                        # 1. 다음 라인 자체의 각도 확인
                        line_angle = self.get_line_angle(line_start, line_end)
                        
                        # 각도 차이 계산 (0-180도 사이로 정규화)
                        angle_diff = abs(line_angle - base_angle)
                        if angle_diff > 180:
                            angle_diff = 360 - angle_diff
                        
                        # 반대 방향(180도 차이)도 같은 기울기로 간주
                        if angle_diff > 90:
                            angle_diff = 180 - angle_diff
                        
                        if angle_diff <= angle_tolerance:
                            # 2. 연결점 사이의 가상선 각도 확인 (일직선상에 있는지)
                            if dist > 0.001:  # 거의 같은 점이 아닌 경우
                                connection_angle = self.get_line_angle(point1, point2)
                                
                                # 연결선 각도와 base_angle 차이 계산
                                connection_angle_diff = abs(connection_angle - base_angle)
                                if connection_angle_diff > 180:
                                    connection_angle_diff = 360 - connection_angle_diff
                                
                                # 반대 방향도 같은 기울기로 간주
                                if connection_angle_diff > 90:
                                    connection_angle_diff = 180 - connection_angle_diff
                                
                                # 연결선도 같은 기울기여야 함 (일직선상)
                                if connection_angle_diff > angle_tolerance:
                                    continue
                            
                            # 모든 조건을 만족하면 연속된 라인으로 추가
                            continuous_lines.append(entity)
                            visited.add(entity)
                            
                            # 재귀적으로 이 라인에서 또 연속된 라인 찾기
                            self._find_continuous_from_endpoints(
                                msp, entity, base_angle, max_distance, 
                                angle_tolerance, continuous_lines, visited,
                                search_layers, exclude_layers, min_length
                            )
                            break


# 사용 예시
def example_usage():
    """A1 찾기 사용 예시"""
    
    # DXF 파일 로드 (ezdxf 라이브러리 사용)
    import ezdxf
    doc = ezdxf.readfile("example.dxf")
    msp = doc.modelspace()
    
    # A1 찾기 객체 생성
    a1_finder = A1LineFinder()
    
    # 기준점들 설정 (예: DBOX 중심점들)
    # 실제로는 DBOX 라인들의 중심점을 계산해야 함
    reference_points = [
        Vec3(100, 100, 0),
        Vec3(150, 100, 0),
        Vec3(100, 150, 0),
        Vec3(150, 150, 0)
    ]
    
    # A1 찾기
    a1_lines, a1_info = a1_finder.find_a1_from_reference_points(
        msp, 
        reference_points,
        max_distance=7.0,  # 기준점에서 최대 7mm
        search_layers=["DIMLINES", "ISOTEXT"],
        exclude_layers=["PIPE", "FITTINGS", "WELDS"],
        min_length=2.2
    )
    
    if a1_lines:
        print(f"A1 찾기 완료:")
        print(f"  - 총 {a1_info['total_count']}개 라인")
        print(f"  - A1: {a1_info['a1_count']}개")
        print(f"  - A1-1: {a1_info['a1_1_count']}개")
        print(f"  - 기준점에서 거리: {a1_info['distance']:.2f}mm")
        
        # 찾은 라인들에 대한 처리 (예: 레이어 변경)
        for i, line in enumerate(a1_lines):
            if i == 0:
                line.dxf.layer = "A1"
                line.dxf.color = 4  # CYAN
            else:
                line.dxf.layer = "A1-1"
                line.dxf.color = 4  # CYAN
    else:
        print("A1을 찾을 수 없습니다.")