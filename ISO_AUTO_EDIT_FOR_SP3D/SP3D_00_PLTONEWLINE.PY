import tkinter as tk
from tkinter import filedialog, messagebox
import ezdxf
import os
import math

def calculate_polyline_area(points):
    """폴리라인의 면적을 계산하는 함수 (Shoelace formula)"""
    if len(points) < 3:
        return 0
    
    area = 0
    n = len(points)
    for i in range(n):
        j = (i + 1) % n
        area += points[i][0] * points[j][1]
        area -= points[j][0] * points[i][1]
    
    return abs(area) / 2

def calculate_hatch_area(hatch):
    """HATCH의 면적을 계산하는 함수"""
    try:
        total_area = 0
        
        # HATCH의 모든 경계 경로를 순회
        for path in hatch.paths:
            if path.path_type_flags & 2:  # Polyline path
                # 폴리라인 경로의 점들을 가져옴
                points = [(v[0], v[1]) for v in path.vertices]
                if len(points) >= 3:
                    area = calculate_polyline_area(points)
                    total_area += area
            else:  # Edge path
                # Edge path의 경우 각 edge를 점으로 변환
                points = []
                for edge in path.edges:
                    if edge.EDGE_TYPE == "LineEdge":
                        points.append((edge.start[0], edge.start[1]))
                    elif edge.EDGE_TYPE == "ArcEdge":
                        # 호의 시작점 추가
                        center = edge.center
                        radius = edge.radius
                        start_angle = math.radians(edge.start_angle)
                        points.append((
                            center[0] + radius * math.cos(start_angle),
                            center[1] + radius * math.sin(start_angle)
                        ))
                    elif edge.EDGE_TYPE == "EllipseEdge":
                        # 타원의 시작점 추가 (간단히 처리)
                        points.append((edge.center[0], edge.center[1]))
                    elif edge.EDGE_TYPE == "SplineEdge":
                        # 스플라인의 제어점 추가
                        if hasattr(edge, 'control_points'):
                            points.extend([(p[0], p[1]) for p in edge.control_points])
                
                # 마지막 edge의 끝점 추가
                if path.edges and hasattr(path.edges[-1], 'end'):
                    last_edge = path.edges[-1]
                    if last_edge.EDGE_TYPE == "LineEdge":
                        points.append((last_edge.end[0], last_edge.end[1]))
                
                if len(points) >= 3:
                    area = calculate_polyline_area(points)
                    total_area += area
        
        return total_area
    except Exception as e:
        # 오류 발생 시 0 반환
        return 0

def calculate_line_length(line):
    """LINE 엔티티의 길이를 계산하는 함수"""
    start = line.dxf.start
    end = line.dxf.end
    
    # 3D 거리 계산
    dx = end.x - start.x
    dy = end.y - start.y
    dz = end.z - start.z
    
    return math.sqrt(dx*dx + dy*dy + dz*dz)

def get_arc_endpoints(arc):
    """호의 시작점과 끝점을 계산"""
    center = arc.dxf.center
    radius = arc.dxf.radius
    start_angle = math.radians(arc.dxf.start_angle)
    end_angle = math.radians(arc.dxf.end_angle)
    
    # 시작점
    start_point = (
        center.x + radius * math.cos(start_angle),
        center.y + radius * math.sin(start_angle),
        center.z
    )
    
    # 끝점
    end_point = (
        center.x + radius * math.cos(end_angle),
        center.y + radius * math.sin(end_angle),
        center.z
    )
    
    return start_point, end_point

def point_distance(p1, p2):
    """두 점 사이의 거리 계산"""
    return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2 + (p1[2] - p2[2])**2)

def point_to_line_distance(point, line_start, line_end):
    """점과 선분 사이의 최단 거리와 선분 위의 가장 가까운 점 반환"""
    x0, y0, z0 = point
    x1, y1, z1 = line_start
    x2, y2, z2 = line_end
    
    # 선분의 벡터
    dx = x2 - x1
    dy = y2 - y1
    dz = z2 - z1
    
    # 선분의 길이 제곱
    line_length_sq = dx*dx + dy*dy + dz*dz
    
    if line_length_sq == 0:
        # 선분이 점인 경우
        return point_distance(point, line_start), line_start
    
    # 매개변수 t 계산
    t = ((x0 - x1) * dx + (y0 - y1) * dy + (z0 - z1) * dz) / line_length_sq
    
    # t를 0과 1 사이로 제한 (선분의 범위)
    t = max(0, min(1, t))
    
    # 선분 위의 가장 가까운 점
    closest_point = (
        x1 + t * dx,
        y1 + t * dy,
        z1 + t * dz
    )
    
    distance = point_distance(point, closest_point)
    
    return distance, closest_point

def find_closest_pipe_point(ap1, pipe_lines):
    """AP1에서 가장 가까운 PIPE 선의 점(AP2)을 찾기"""
    min_distance = float('inf')
    closest_point = None
    
    for line in pipe_lines:
        start = (line.dxf.start.x, line.dxf.start.y, line.dxf.start.z)
        end = (line.dxf.end.x, line.dxf.end.y, line.dxf.end.z)
        
        distance, point = point_to_line_distance(ap1, start, end)
        
        if distance < min_distance:
            min_distance = distance
            closest_point = point
    
    return closest_point

def process_dxf_file(filepath):
    """DXF 파일을 처리하는 함수"""
    try:
        # DXF 파일 열기
        doc = ezdxf.readfile(filepath)
        msp = doc.modelspace()
        
        # 삭제할 엔티티를 저장할 리스트
        entities_to_delete = []
        
        # PIPE 레이어의 LINE들을 저장할 리스트
        pipe_lines = []
        
        # 카운터
        counters = {
            'pipe_line_color': 0,
            'pipe_line_yellow': 0,  # 길이 0.2~1.1mm인 PIPE 라인 카운터 추가
            'pipe_arc': 0,
            'dimlines_line': 0,
            'fittings_line': 0,
            'isotext_line': 0,
            'dimlines_polyline': 0,
            'isotext_polyline': 0,
            'elbo_arc_moved': 0,
            'hatch_deleted': 0  # HATCH 삭제 카운터 추가
        }
        
        # 모든 엔티티 순회
        for entity in msp:
            try:
                # HATCH 처리 (모든 레이어에서 면적 0.9 이하인 HATCH 삭제)
                if entity.dxftype() == 'HATCH':
                    area = calculate_hatch_area(entity)
                    if area <= 0.9:
                        entities_to_delete.append(entity)
                        counters['hatch_deleted'] += 1
                        continue
                
                layer = entity.dxf.layer.upper()  # 대소문자 구분 없이 처리
                
                # PIPE 레이어의 LINE 저장
                if entity.dxftype() == 'LINE' and layer == 'PIPE':
                    pipe_lines.append(entity)
                
                # 1. 도면층이 PIPE이고 LINE인 경우 길이에 따라 색상 변경
                if entity.dxftype() == 'LINE' and layer == 'PIPE':
                    length = calculate_line_length(entity)
                    
                    # 길이가 0.2~1.1mm인 경우 YELLOW로 변경
                    if 0.2 <= length <= 1.1:
                        entity.dxf.color = 2  # YELLOW
                        counters['pipe_line_yellow'] += 1
                    # 그 외 흰색(7)인 LINE을 GREEN(3)으로 변경
                    elif hasattr(entity.dxf, 'color') and entity.dxf.color == 7:  # 흰색
                        entity.dxf.color = 3  # GREEN
                        counters['pipe_line_color'] += 1
                
                # 2. 도면층이 PIPE인 ARC를 찾아서 색상을 GREEN으로 변경하고 도면층을 ELBO로 변경
                elif entity.dxftype() == 'ARC' and layer == 'PIPE':
                    entity.dxf.color = 3  # GREEN
                    entity.dxf.layer = 'ELBO'
                    counters['pipe_arc'] += 1
                
                # 3. 도면층이 DIMLINES인 모든 LINE을 흰색으로 변경
                elif entity.dxftype() == 'LINE' and layer == 'DIMLINES':
                    entity.dxf.color = 7  # 흰색
                    counters['dimlines_line'] += 1
                
                # 4. 도면층이 FITTINGS인 LINE을 찾아서 색상을 YELLOW로 변경
                elif entity.dxftype() == 'LINE' and layer == 'FITTINGS':
                    entity.dxf.color = 2  # YELLOW
                    counters['fittings_line'] += 1
                
                # 5. 도면층이 ISOTEXT인 모든 LINE을 흰색으로 변경
                elif entity.dxftype() == 'LINE' and layer == 'ISOTEXT':
                    entity.dxf.color = 7  # 흰색
                    counters['isotext_line'] += 1
                
                # 6. 도면층이 DIMLINES이고 폴리라인이며 면적이 0.1 ~ 0.9인 것은 삭제
                elif entity.dxftype() in ['LWPOLYLINE', 'POLYLINE'] and layer == 'DIMLINES':
                    # 폴리라인의 점들을 가져옴
                    points = []
                    if entity.dxftype() == 'LWPOLYLINE':
                        points = list(entity.get_points())
                    elif entity.dxftype() == 'POLYLINE':
                        points = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
                    
                    # 면적 계산
                    if points and entity.is_closed:
                        area = calculate_polyline_area(points)
                        if 0.1 <= area <= 0.9:
                            entities_to_delete.append(entity)
                            counters['dimlines_polyline'] += 1
                
                # 7. 도면층이 ISOTEXT이고 폴리라인이며 면적이 0.1 ~ 0.9인 것은 삭제
                elif entity.dxftype() in ['LWPOLYLINE', 'POLYLINE'] and layer == 'ISOTEXT':
                    # 폴리라인의 점들을 가져옴
                    points = []
                    if entity.dxftype() == 'LWPOLYLINE':
                        points = list(entity.get_points())
                    elif entity.dxftype() == 'POLYLINE':
                        points = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
                    
                    # 면적 계산
                    if points and entity.is_closed:
                        area = calculate_polyline_area(points)
                        if 0.1 <= area <= 0.9:
                            entities_to_delete.append(entity)
                            counters['isotext_polyline'] += 1
                            
            except AttributeError:
                # 일부 엔티티에 특정 속성이 없을 수 있음
                continue
            except Exception as e:
                continue
        
        # 삭제할 엔티티들 삭제
        for entity in entities_to_delete:
            msp.delete_entity(entity)
        
        # ELBO 레이어의 ARC를 찾아서 PIPE 선에 맞춰 이동
        if pipe_lines:  # PIPE 선이 있을 때만 처리
            for entity in msp:
                try:
                    if entity.dxftype() == 'ARC' and entity.dxf.layer.upper() == 'ELBO':
                        # ARC의 끝점들 구하기
                        start_point, end_point = get_arc_endpoints(entity)
                        
                        # 시작점을 AP1으로 사용 (끝점을 사용하려면 end_point로 변경)
                        ap1 = start_point
                        
                        # AP1에서 가장 가까운 PIPE 선의 점(AP2) 찾기
                        ap2 = find_closest_pipe_point(ap1, pipe_lines)
                        
                        if ap2:
                            # 이동 벡터 계산
                            dx = ap2[0] - ap1[0]
                            dy = ap2[1] - ap1[1]
                            dz = ap2[2] - ap1[2]
                            
                            # ARC의 중심점 이동
                            old_center = entity.dxf.center
                            entity.dxf.center = (
                                old_center.x + dx,
                                old_center.y + dy,
                                old_center.z + dz
                            )
                            counters['elbo_arc_moved'] += 1
                            
                except Exception as e:
                    continue
        
        # 새 파일명 생성 (원본파일명_PL.DXF)
        base_name = os.path.splitext(os.path.basename(filepath))[0]
        dir_name = os.path.dirname(filepath)
        new_filepath = os.path.join(dir_name, f"{base_name}_PL.DXF")
        
        # 파일 저장
        doc.saveas(new_filepath)
        
        # 처리 결과 정보
        result_info = f"\n처리 통계:\n"
        result_info += f"  - PIPE 라인 (0.2~1.1mm) → YELLOW: {counters['pipe_line_yellow']}개\n"
        result_info += f"  - PIPE 흰색 LINE → GREEN: {counters['pipe_line_color']}개\n"
        result_info += f"  - PIPE ARC → GREEN/ELBO: {counters['pipe_arc']}개\n"
        result_info += f"  - DIMLINES LINE → 흰색: {counters['dimlines_line']}개\n"
        result_info += f"  - FITTINGS LINE → YELLOW: {counters['fittings_line']}개\n"
        result_info += f"  - ISOTEXT LINE → 흰색: {counters['isotext_line']}개\n"
        result_info += f"  - DIMLINES 폴리라인 삭제: {counters['dimlines_polyline']}개\n"
        result_info += f"  - ISOTEXT 폴리라인 삭제: {counters['isotext_polyline']}개\n"
        result_info += f"  - HATCH 삭제 (면적 ≤ 0.9): {counters['hatch_deleted']}개\n"
        result_info += f"  - ELBO ARC 이동: {counters['elbo_arc_moved']}개"
        
        return True, new_filepath + result_info
        
    except IOError as e:
        return False, f"파일 읽기/쓰기 오류: {e}"
    except ezdxf.DXFStructureError as e:
        return False, f"DXF 구조 오류: {e}"
    except Exception as e:
        return False, f"처리 중 오류 발생: {e}"

def select_and_process_files():
    """파일 선택 대화상자를 열고 선택된 파일들을 처리"""
    root = tk.Tk()
    root.withdraw()  # 메인 윈도우 숨기기
    
    # 파일 선택 대화상자
    file_paths = filedialog.askopenfilenames(
        title="DXF 파일 선택",
        filetypes=[("DXF files", "*.dxf"), ("All files", "*.*")],
        multiple=True
    )
    
    if not file_paths:
        messagebox.showinfo("알림", "선택된 파일이 없습니다.")
        return
    
    # 처리 결과 저장
    success_count = 0
    error_files = []
    detailed_results = []
    
    # 선택된 파일들 처리
    for filepath in file_paths:
        print(f"\n처리 중: {os.path.basename(filepath)}")
        success, result = process_dxf_file(filepath)
        if success:
            success_count += 1
            detailed_results.append((os.path.basename(filepath), result))
            print(f"처리 완료: {filepath}")
        else:
            error_files.append((filepath, result))
            print(f"처리 실패: {filepath} - {result}")
    
    # 결과 메시지 표시
    message = f"처리 완료!\n\n성공: {success_count}개 파일"
    
    if error_files:
        message += f"\n\n실패: {len(error_files)}개 파일\n실패 파일 목록:"
        for file, error in error_files:
            message += f"\n- {os.path.basename(file)}: {error}"
    
    # messagebox.showinfo("처리 결과", message)
    root.destroy()

if __name__ == "__main__":
    # ezdxf 라이브러리 설치 확인
    try:
        import ezdxf
        print(f"ezdxf 버전: {ezdxf.__version__}")
    except ImportError:
        print("ezdxf 라이브러리가 설치되어 있지 않습니다.")
        print("다음 명령으로 설치해주세요: pip install ezdxf")
        exit(1)
    
    print("DXF 파일 일괄 처리 프로그램")
    print("파일 선택 대화상자가 열립니다...")
    
    select_and_process_files()