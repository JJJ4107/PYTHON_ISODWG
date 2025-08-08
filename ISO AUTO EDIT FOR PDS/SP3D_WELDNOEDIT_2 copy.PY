import ezdxf
import tkinter as tk
from tkinter import filedialog, messagebox
import os
import math
import numpy as np
from ezdxf.math import Vec3, intersection_line_line_2d
from ezdxf.entities import Circle, Text, Line, Arc, LWPolyline, Polyline

class DXFProcessor:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        
    def open_files(self):
        """DXF 파일 선택 대화상자 열기"""
        file_paths = filedialog.askopenfilenames(
            title="DXF 파일 선택",
            filetypes=[("DXF files", "*.dxf"), ("All files", "*.*")]
        )
        return file_paths
    
    def distance_2d(self, p1, p2):
        """2D 거리 계산"""
        return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)
    
    def point_to_line_distance(self, point, line_start, line_end):
        """점과 선분 사이의 최단 거리 계산"""
        A = np.array([line_start[0], line_start[1]])
        B = np.array([line_end[0], line_end[1]])
        P = np.array([point[0], point[1]])
        
        AB = B - A
        AP = P - A
        
        if np.dot(AB, AB) == 0:
            return np.linalg.norm(AP)
        
        t = max(0, min(1, np.dot(AP, AB) / np.dot(AB, AB)))
        projection = A + t * AB
        
        return np.linalg.norm(P - projection), projection
    
    def get_circle_line_intersection(self, center, radius, line_start, line_end):
        """원과 선의 교점 찾기"""
        # 선을 매개변수 형태로 표현
        dx = line_end[0] - line_start[0]
        dy = line_end[1] - line_start[1]
        
        # 원의 중심을 원점으로 이동
        fx = line_start[0] - center[0]
        fy = line_start[1] - center[1]
        
        a = dx * dx + dy * dy
        b = 2 * (fx * dx + fy * dy)
        c = fx * fx + fy * fy - radius * radius
        
        discriminant = b * b - 4 * a * c
        
        if discriminant < 0:
            return None
            
        discriminant = math.sqrt(discriminant)
        
        t1 = (-b - discriminant) / (2 * a)
        t2 = (-b + discriminant) / (2 * a)
        
        # 선분 내의 교점만 찾기
        intersections = []
        if 0 <= t1 <= 1:
            intersections.append((line_start[0] + t1 * dx, line_start[1] + t1 * dy))
        if 0 <= t2 <= 1:
            intersections.append((line_start[0] + t2 * dx, line_start[1] + t2 * dy))
            
        return intersections
    
    def create_text_box(self, text_entity):
        """텍스트를 박스화하여 경계 상자와 중심 반환"""
        if not text_entity:
            return None, None
            
        text_height = text_entity.dxf.height
        text_content = text_entity.dxf.text
        text_width = len(text_content) * text_height * 0.7  # 대략적인 너비
        
        insert_point = text_entity.dxf.insert
        rotation = math.radians(text_entity.dxf.rotation)
        
        # 텍스트 박스의 네 모서리 계산 (원점 기준)
        corners = [
            (0, -text_height * 0.2),
            (text_width, -text_height * 0.2),
            (text_width, text_height),
            (0, text_height)
        ]
        
        # 박스 중심 계산 (원점 기준)
        box_center_local = (text_width / 2, text_height * 0.4)
        
        # 회전 적용
        rotated_corners = []
        for x, y in corners:
            rx = x * math.cos(rotation) - y * math.sin(rotation) + insert_point[0]
            ry = x * math.sin(rotation) + y * math.cos(rotation) + insert_point[1]
            rotated_corners.append((rx, ry))
        
        # 박스 중심의 실제 위치 계산
        box_center = (
            box_center_local[0] * math.cos(rotation) - box_center_local[1] * math.sin(rotation) + insert_point[0],
            box_center_local[1] * math.cos(rotation) + box_center_local[0] * math.sin(rotation) + insert_point[1]
        )
            
        return rotated_corners, box_center
    
    def move_text_box_by_center(self, text_entity, new_center):
        """텍스트 박스의 중심을 새로운 위치로 이동"""
        if text_entity:
            # 현재 박스의 중심 위치 계산
            _, current_center = self.create_text_box(text_entity)
            
            # 중심 이동에 필요한 오프셋 계산
            offset_x = new_center[0] - current_center[0]
            offset_y = new_center[1] - current_center[1]
            
            # 텍스트 엔티티 이동
            current_insert = text_entity.dxf.insert
            text_entity.dxf.insert = (
                current_insert[0] + offset_x,
                current_insert[1] + offset_y,
                current_insert[2]
            )
    
    def check_wd_interference(self, msp, wdc_center, wdc_radius, wdt_text, exclude_entities):
        """WD(WDC+WDT) 전체의 간섭 체크"""
        check_radius = wdc_radius + 0.1  # WCHK (변경: 1.0 -> 0.1)
        
        # WDT 박스 corners 계산
        text_box_corners = None
        if wdt_text:
            text_box_corners, _ = self.create_text_box(wdt_text)
        
        for entity in msp:
            # 제외 대상 확인
            if entity in exclude_entities:
                continue
            if entity.dxf.layer in ['WDC', 'WDT', 'A1', 'WEDLS']:
                continue
                
            # WDC 원과의 간섭 체크
            if entity.dxftype() == 'CIRCLE':
                center = entity.dxf.center
                radius = entity.dxf.radius
                distance = self.distance_2d(wdc_center, center)
                if distance < check_radius + radius:
                    return True
                    
            elif entity.dxftype() == 'LINE':
                start = entity.dxf.start
                end = entity.dxf.end
                dist, _ = self.point_to_line_distance(wdc_center, start, end)
                if dist < check_radius:
                    return True
                    
            # WDT 텍스트 박스와의 간섭 체크
            if text_box_corners:
                for corner in text_box_corners:
                    if entity.dxftype() == 'CIRCLE':
                        if self.distance_2d(corner, entity.dxf.center) < entity.dxf.radius:
                            return True
                    elif entity.dxftype() == 'LINE':
                        dist, _ = self.point_to_line_distance(corner, entity.dxf.start, entity.dxf.end)
                        if dist < 0.5:  # 작은 여유 공간
                            return True
                    
        return False
    
    def find_wdc_circles(self, msp):
        """반지름 1.5~3.4mm인 ISOTEXT 레이어 원 찾기"""
        wdc_circles = []
        for entity in msp:
            if entity.dxftype() == 'CIRCLE' and entity.dxf.layer == 'ISOTEXT':
                radius = entity.dxf.radius
                if 1.5 <= radius <= 3.4:
                    # WDC 레이어로 변경하고 색상을 CYAN으로 설정
                    entity.dxf.layer = 'WDC'
                    entity.dxf.color = 4  # CYAN
                    wdc_circles.append(entity)
        return wdc_circles
    
    def find_wdt_text(self, msp, wdc_circle):
        """WDC에서 4mm 범위 내의 수평 ISOTEXT 텍스트 찾기"""
        center = wdc_circle.dxf.center
        for entity in msp:
            if entity.dxftype() == 'TEXT' and entity.dxf.layer == 'ISOTEXT':
                text_pos = entity.dxf.insert
                distance = self.distance_2d(center, text_pos)
                rotation = entity.dxf.rotation
                
                # 기울기가 0 (수평)이고 4mm 이내
                if distance <= 4.0 and abs(rotation) < 0.1:
                    entity.dxf.layer = 'WDT'
                    return entity
        return None
    
    def find_a1_line(self, msp, wdc_circle):
        """WDC에서 3mm 내에 가장 가까운 ISOTEXT 선 찾기"""
        center = wdc_circle.dxf.center
        min_distance = float('inf')
        closest_line = None
        ap1 = None
        ap2 = None
        
        for entity in msp:
            if entity.dxftype() == 'LINE' and entity.dxf.layer == 'ISOTEXT':
                start = entity.dxf.start
                end = entity.dxf.end
                
                dist_start = self.distance_2d(center, start)
                dist_end = self.distance_2d(center, end)
                
                # 더 가까운 점 찾기
                if dist_start < dist_end:
                    if dist_start <= 3.0 and dist_start < min_distance:
                        min_distance = dist_start
                        closest_line = entity
                        ap1 = start
                        ap2 = end
                else:
                    if dist_end <= 3.0 and dist_end < min_distance:
                        min_distance = dist_end
                        closest_line = entity
                        ap1 = end
                        ap2 = start
        
        if closest_line:
            closest_line.dxf.layer = 'A1'
            return closest_line, ap1, ap2
        
        return None, None, None
    
    def find_pipe_lines(self, msp, ap2):
        """AP2에서 3mm 내의 PIPE 레이어 선 찾기 (최대 2개)"""
        pipe_lines = []
        for entity in msp:
            if entity.dxftype() == 'LINE' and entity.dxf.layer == 'PIPE':
                start = entity.dxf.start
                end = entity.dxf.end
                
                if self.distance_2d(ap2, start) <= 3.0 or self.distance_2d(ap2, end) <= 3.0:
                    pipe_lines.append(entity)
                    if len(pipe_lines) >= 2:
                        break
        
        # PIPE1, PIPE2로 이름 지정
        for i, pipe in enumerate(pipe_lines):
            pipe.pipe_name = f'PIPE{i+1}'
        
        return pipe_lines
    
    def find_elbo_arc(self, msp, ap2):
        """AP2에서 10mm 내의 ELBO 레이어 호 찾기"""
        for entity in msp:
            if entity.dxftype() == 'ARC' and entity.dxf.layer == 'ELBO':
                center = entity.dxf.center
                radius = entity.dxf.radius
                
                # 호 위의 점들 확인
                dist_to_center = self.distance_2d(ap2, center)
                if dist_to_center - radius <= 10.0:
                    entity.elbo_name = 'ELBO1'
                    return entity
        return None
    
    def process_dxf_file(self, file_path):
        """DXF 파일 처리"""
        try:
            # DXF 파일 열기
            doc = ezdxf.readfile(file_path)
            msp = doc.modelspace()
            
            # 1. WDC 원 찾기
            wdc_circles = self.find_wdc_circles(msp)
            
            for wdc in wdc_circles:
                wdc_center = wdc.dxf.center
                wdc_radius = wdc.dxf.radius
                
                # 2. WDT 텍스트 찾기
                wdt_text = self.find_wdt_text(msp, wdc)
                
                # 3. A1 선 찾기
                a1_line, ap1, ap2 = self.find_a1_line(msp, wdc)
                
                if not a1_line or not ap2:
                    continue
                
                # 4. PIPE 선 찾기
                pipe_lines = self.find_pipe_lines(msp, ap2)
                
                # 5. ELBO 호 찾기
                elbo_arc = self.find_elbo_arc(msp, ap2)
                
                # 6. WDT 텍스트 박스화 및 BOX 중심을 WDC 중심으로 이동
                st_position = wdc_center  # ST 위치 저장
                
                if wdt_text:
                    # 텍스트 박스의 중심을 WDC 중심으로 이동
                    self.move_text_box_by_center(wdt_text, wdc_center)
                
                # 7. WD 이동 위치 계산
                # WCHK = WD 원범위 + 0.1mm (간섭 체크 범위)
                # 이동 조건: WDC 중심과 AP2의 거리가 'WDC 반지름 + 2.9mm'가 되는 지점으로 이동
                # 즉, AP2에서 (WDC 반지름 + 2.9mm) 떨어진 위치가 새로운 WDC 중심
                direction = np.array([wdc_center[0] - ap2[0], wdc_center[1] - ap2[1], 0])
                direction_length = np.linalg.norm(direction[:2])
                
                if direction_length == 0:
                    # WDC 중심과 AP2가 같은 위치인 경우
                    continue
                    
                direction_norm = direction[:2] / direction_length
                
                # 목표 거리: WDC 반지름 + 2.9mm
                target_distance = wdc_radius + 2.9
                
                # MO 위치 계산 (AP2에서 target_distance만큼 떨어진 위치)
                mo_position = (
                    ap2[0] + direction_norm[0] * target_distance,
                    ap2[1] + direction_norm[1] * target_distance,
                    ap2[2]
                )
                
                # 간섭 체크를 위한 제외 엔티티 리스트
                exclude_entities = [wdc]
                if wdt_text:
                    exclude_entities.append(wdt_text)
                if a1_line:
                    exclude_entities.append(a1_line)
                
                # 8. WDC와 WDT를 MO 위치로 함께 이동
                wdc.dxf.center = mo_position
                if wdt_text:
                    self.move_text_box_by_center(wdt_text, mo_position)
                
                # 9. 간섭 체크
                interference = self.check_wd_interference(msp, mo_position, wdc_radius, wdt_text, exclude_entities)
                
                final_position = mo_position
                
                if interference:
                    # 간섭이 있으면 1mm씩 ST 위치(원래 WDC 중심) 방향으로 이동
                    # 이동 방향: MO에서 ST로
                    back_direction = np.array([st_position[0] - mo_position[0], st_position[1] - mo_position[1]])
                    back_distance = np.linalg.norm(back_direction)
                    
                    if back_distance == 0:
                        # ST와 MO가 같은 위치인 경우 (이동할 곳이 없음)
                        print(f"Warning: Cannot move WD - ST and MO positions are the same")
                        continue
                        
                    back_direction_norm = back_direction / back_distance
                    
                    step = 1.0
                    max_distance = np.linalg.norm(back_direction)
                    max_steps = int(max_distance / step)
                    
                    found_position = False
                    
                    for i in range(1, max_steps + 1):
                        # 이동할 위치 계산 (MO에서 ST 방향으로)
                        test_position = (
                            mo_position[0] + back_direction_norm[0] * (step * i),
                            mo_position[1] + back_direction_norm[1] * (step * i),
                            mo_position[2]
                        )
                        
                        # WDC와 WDT를 함께 테스트 위치로 이동
                        wdc.dxf.center = test_position
                        if wdt_text:
                            self.move_text_box_by_center(wdt_text, test_position)
                        
                        # 간섭 체크
                        if not self.check_wd_interference(msp, test_position, wdc_radius, wdt_text, exclude_entities):
                            final_position = test_position
                            found_position = True
                            break
                    
                    # 간섭 없는 위치를 찾지 못한 경우 ST 위치로
                    if not found_position:
                        final_position = st_position
                        wdc.dxf.center = final_position
                        if wdt_text:
                            self.move_text_box_by_center(wdt_text, final_position)
                
                # 10. WL 선 생성 및 WDC 원 안 부분 TRIM
                # WL: WDC 중심에서 AP2로 연결하되, WDC 원 안의 부분은 제거
                
                # 원과 선의 교점 찾기
                intersections = self.get_circle_line_intersection(final_position, wdc_radius, final_position, ap2)
                
                if intersections and len(intersections) > 0:
                    # 교점들 중 AP2에 가장 가까운 점 선택 (원을 나가는 점)
                    exit_point = min(intersections, key=lambda p: self.distance_2d(p, ap2))
                    
                    # WDC 원 경계에서 AP2까지의 선만 생성 (원 안 부분은 TRIM)
                    wl_line = msp.add_line(exit_point, ap2)
                    wl_line.dxf.layer = 'WL'
                    wl_line.dxf.color = 7  # 흰색
                else:
                    # 교점이 없는 경우 (AP2가 원 안에 있거나 선이 원과 만나지 않는 경우)
                    dist_to_ap2 = self.distance_2d(final_position, ap2)
                    
                    if dist_to_ap2 > wdc_radius:
                        # AP2가 원 밖에 있지만 교점을 못 찾은 경우
                        print(f"Warning: Could not find intersection point for WL trim")
                        # 전체 선 생성
                        wl_line = msp.add_line(final_position, ap2)
                        wl_line.dxf.layer = 'WL'
                        wl_line.dxf.color = 7
                    else:
                        # AP2가 원 안에 있는 경우 - WL 생성하지 않음
                        print(f"Note: AP2 is inside WDC circle - no WL line created")
                
                # 11. A1 삭제
                if a1_line:
                    msp.delete_entity(a1_line)
            
            # 12. 파일 저장
            base_name = os.path.splitext(os.path.basename(file_path))[0]
            output_path = os.path.join(
                os.path.dirname(file_path),
                f"{base_name}_WDNO.DXF"
            )
            doc.saveas(output_path)
            
            return True, output_path
            
        except Exception as e:
            return False, str(e)
    
    def run(self):
        """메인 실행 함수"""
        file_paths = self.open_files()
        
        if not file_paths:
            messagebox.showinfo("알림", "선택된 파일이 없습니다.")
            return
        
        success_count = 0
        error_files = []
        
        for file_path in file_paths:
            success, result = self.process_dxf_file(file_path)
            
            if success:
                success_count += 1
                print(f"처리 완료: {result}")
            else:
                error_files.append((file_path, result))
                print(f"처리 실패: {file_path} - {result}")
        
        # 결과 메시지
        message = f"총 {len(file_paths)}개 파일 중 {success_count}개 처리 완료"
        if error_files:
            message += f"\n\n실패한 파일:\n"
            for file, error in error_files:
                message += f"{os.path.basename(file)}: {error}\n"
        
        messagebox.showinfo("처리 결과", message)

if __name__ == "__main__":
    processor = DXFProcessor()
    processor.run()