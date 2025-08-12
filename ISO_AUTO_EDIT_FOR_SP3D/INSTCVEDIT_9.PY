import ezdxf
from ezdxf.math import Vec3
from ezdxf.entities import DXFEntity
import tkinter as tk
from tkinter import filedialog
import math
import numpy as np
from typing import List, Tuple, Optional, Union

class DXFProcessor:
    def __init__(self):
        self.doc = None
        self.msp = None
        self.used_entities = set()  # 이미 사용된 엔티티 추적
        self.instno_circles = []  # 찾은 INSTNO 원들 저장
        self.instno_data = {}  # 각 INSTNO에 대한 관련 데이터 저장
        
    def select_dxf_files(self) -> List[str]:
        """DXF 파일 선택 다이얼로그 열기"""
        root = tk.Tk()
        root.withdraw()
        
        file_paths = filedialog.askopenfilenames(
            title="DXF 파일 선택",
            filetypes=[("DXF files", "*.dxf"), ("All files", "*.*")]
        )
        
        return list(file_paths)
    
    def load_dxf(self, filepath: str):
        """DXF 파일 로드"""
        self.doc = ezdxf.readfile(filepath)
        self.msp = self.doc.modelspace()
    
    def get_entity_points(self, entity: DXFEntity) -> List[Vec3]:
        """엔티티에서 점들을 안전하게 추출"""
        try:
            if entity.dxftype() == "LWPOLYLINE":
                points = list(entity.get_points('xy'))
                return [Vec3(p[0], p[1], 0) for p in points]
            elif entity.dxftype() == "POLYLINE":
                points = []
                for vertex in entity.vertices:
                    points.append(Vec3(vertex.dxf.location))
                return points
            else:
                return []
        except Exception as e:
            print(f"Error getting points: {e}")
            return []
    
    def find_instno_circles(self) -> List[DXFEntity]:
        """INSTNO 레이어의 원(CIRCLE) 찾기"""
        instno_circles = []
        
        for entity in self.msp:
            if entity.dxf.layer == "INSTNO":
                if entity.dxftype() == "CIRCLE":
                    instno_circles.append(entity)
        
        return instno_circles
    
    def find_a2_polyline(self, center: Vec3, radius: float) -> Optional[DXFEntity]:
        """INSTNO 원과 관련된 2점 또는 3점 폴리라인 찾기 (A2) - 1개만 반환"""
        print(f"    - Looking for A2 polyline near circle: center={center}, radius={radius:.2f}")
        
        candidates = []
        
        for entity in self.msp:
            if entity in self.used_entities:
                continue
            
            if hasattr(entity.dxf, 'color') and entity.dxf.color == 4:  # CYAN = 4
                continue
                
            if entity.dxftype() in ["POLYLINE", "LWPOLYLINE"]:
                points = self.get_entity_points(entity)
                if len(points) == 2 or len(points) == 3:
                    p1 = points[0]
                    p2 = points[-1]
                    
                    dist1_to_center = (p1 - center).magnitude
                    dist2_to_center = (p2 - center).magnitude
                    dist1_to_circle = abs(dist1_to_center - radius)
                    dist2_to_circle = abs(dist2_to_center - radius)
                    
                    # 조건 1: 어느 한 점이 원둘레로부터 1mm 이내
                    if dist1_to_circle <= 1.0 or dist2_to_circle <= 1.0:
                        min_dist_to_circle = min(dist1_to_circle, dist2_to_circle)
                        candidates.append((entity, min_dist_to_circle, "circle_proximity"))
                        print(f"      - Found A2 candidate ({len(points)} points): distance to circle = {min_dist_to_circle:.3f}mm")
                    
                    # 조건 2: 어느 한 점이 INSTNO 중심에서 9mm 이내
                    elif dist1_to_center <= 9.0 or dist2_to_center <= 9.0:
                        min_dist_to_center = min(dist1_to_center, dist2_to_center)
                        candidates.append((entity, min_dist_to_center, "center_proximity"))
                        print(f"      - Found A2 candidate ({len(points)} points): distance to center = {min_dist_to_center:.3f}mm")
        
        if candidates:
            candidates.sort(key=lambda x: (0 if x[2] == "circle_proximity" else 1, x[1]))
            result = candidates[0][0]
            result.dxf.color = 4  # CYAN = 4
            self.used_entities.add(result)
            print(f"      - Selected A2, color changed to CYAN")
            return result
        
        print("      - No A2 candidate found")
        return None
    
    def get_circle_tangent_points(self, center: Vec3, radius: float) -> List[Vec3]:
        """원의 모든 접선점들을 계산 (36개 점, 10도 간격)"""
        points = []
        for angle in range(0, 360, 10):
            rad = math.radians(angle)
            x = center.x + radius * math.cos(rad)
            y = center.y + radius * math.sin(rad)
            points.append(Vec3(x, y, center.z))
        return points
    
    def find_tbox_near_tangent(self, center: Vec3, radius: float) -> Optional[DXFEntity]:
        """INSTNO 원의 접선에서 10mm 이내의 5점 폴리라인 찾기 (TBOX)"""
        print(f"    - Looking for TBOX near circle tangent")
        
        tangent_points = self.get_circle_tangent_points(center, radius)
        candidates = []
        
        for entity in self.msp:
            if entity in self.used_entities:
                continue
                
            if entity.dxftype() in ["POLYLINE", "LWPOLYLINE"]:
                points = self.get_entity_points(entity)
                if len(points) == 5:
                    # 각 점에서 가장 가까운 접선점까지의 거리 계산
                    min_dist_to_tangent = float('inf')
                    for point in points:
                        for tangent_point in tangent_points:
                            dist = (point - tangent_point).magnitude
                            min_dist_to_tangent = min(min_dist_to_tangent, dist)
                    
                    if min_dist_to_tangent <= 10.0:  # 10mm 이내
                        # 전체 길이 계산
                        total_length = 0
                        for i in range(len(points) - 1):
                            total_length += (points[i+1] - points[i]).magnitude
                        
                        candidates.append((entity, total_length, min_dist_to_tangent))
                        print(f"      - Found TBOX candidate: length={total_length:.2f}mm, distance from tangent={min_dist_to_tangent:.2f}mm")
        
        if candidates:
            # 길이가 14mm에 가장 가까운 것 선택
            candidates.sort(key=lambda x: abs(x[1] - 14.0))
            selected = candidates[0][0]
            self.used_entities.add(selected)
            print(f"      - Selected TBOX")
            return selected
        
        print("      - TBOX not found")
        return None
    
    def find_itag_near_tangent(self, center: Vec3, radius: float) -> Optional[DXFEntity]:
        """INSTNO 원의 접선에서 10mm 이내의 조건에 맞는 TEXT 찾기 (ITAG)"""
        print(f"    - Looking for ITAG near circle tangent")
        
        tangent_points = self.get_circle_tangent_points(center, radius)
        candidates = []
        
        for text_entity in self.msp.query('TEXT'):
            if text_entity in self.used_entities:
                continue
            
            try:
                text_value = text_entity.dxf.text.strip()
                value = float(text_value)
                
                if 3 <= value <= 50:
                    rotation = text_entity.dxf.rotation
                    if abs(rotation) < 0.1:  # 거의 0도
                        text_pos = Vec3(text_entity.dxf.insert)
                        
                        # 가장 가까운 접선점까지의 거리
                        min_dist_to_tangent = float('inf')
                        for tangent_point in tangent_points:
                            dist = (text_pos - tangent_point).magnitude
                            min_dist_to_tangent = min(min_dist_to_tangent, dist)
                        
                        if min_dist_to_tangent <= 10.0:  # 10mm 이내
                            candidates.append((text_entity, value, min_dist_to_tangent))
                            print(f"      - Found ITAG candidate: '{text_value}', distance={min_dist_to_tangent:.2f}mm")
                            
            except ValueError:
                continue
        
        if candidates:
            candidates.sort(key=lambda x: x[2])  # 거리로 정렬
            selected = candidates[0][0]
            self.used_entities.add(selected)
            print(f"      - Selected ITAG: '{selected.dxf.text}'")
            return selected
        
        print("      - ITAG not found")
        return None
    
    def find_ftp(self, center: Vec3, radius: float) -> Vec3:
        """INSTNO 원 접선 중 Y값이 가장 작은 점 (FTP)"""
        tangent_points = self.get_circle_tangent_points(center, radius)
        ftp = min(tangent_points, key=lambda p: p.y)
        print(f"    - FTP (lowest Y tangent point): {ftp}")
        return ftp
    
    def find_tpos(self, tbox: DXFEntity, ftp: Vec3) -> Vec3:
        """TBOX의 점들 중 FTP와 가장 가까운 점 (TPOS)"""
        if not tbox:
            return None
            
        points = self.get_entity_points(tbox)
        if not points:
            return None
        
        min_dist = float('inf')
        tpos = None
        
        for point in points:
            dist = (point - ftp).magnitude
            if dist < min_dist:
                min_dist = dist
                tpos = point
        
        print(f"    - TPOS (closest TBOX point to FTP): {tpos}, distance={min_dist:.2f}mm")
        return tpos
    
    def move_tbox_and_itag_to_ftp(self, tbox: DXFEntity, itag: DXFEntity, tpos: Vec3, ftp: Vec3):
        """TBOX와 ITAG를 TPOS에서 FTP로 이동"""
        if not tpos or not ftp:
            return
        
        offset = ftp - tpos
        
        if tbox:
            tbox.translate(offset.x, offset.y, offset.z)
            tbox.dxf.color = 2  # YELLOW = 2
            print(f"    - TBOX moved by {offset}, color changed to YELLOW")
        
        if itag:
            current_pos = Vec3(itag.dxf.insert)
            itag.dxf.insert = current_pos + offset
            itag.dxf.color = 4  # CYAN = 4
            print(f"    - ITAG moved by {offset}, color changed to CYAN")
    
    def find_insttag_texts(self, instno_circle: DXFEntity) -> List[DXFEntity]:
        """INSTNO 원 둘레에서 2.5mm 이내에 있는 조건에 맞는 TEXT 찾기"""
        insttag_texts = []
        
        center = Vec3(instno_circle.dxf.center)
        radius = instno_circle.dxf.radius
        
        for text_entity in self.msp.query('TEXT'):
            if text_entity.dxf.layer == "WDNO":
                continue
                
            rotation = text_entity.dxf.rotation
            if abs(rotation) > 0.1:
                continue
            
            text_content = text_entity.dxf.text.strip()
            
            if '<' in text_content or '>' in text_content or 'x' in text_content.lower():
                continue
            
            text_pos = Vec3(text_entity.dxf.insert)
            dist_to_center = (text_pos - center).magnitude
            dist_to_circle = abs(dist_to_center - radius)
            
            if dist_to_circle <= 2.5:
                insttag_texts.append(text_entity)
                print(f"        - Found INSTTAG: '{text_entity.dxf.text}' at distance {dist_to_circle:.2f}mm from circle")
        
        return insttag_texts
    
    def get_inst_bounding_box(self, instno: DXFEntity, insttag_texts: List[DXFEntity], 
                             tbox: DXFEntity, itag: DXFEntity) -> Tuple[Vec3, Vec3]:
        """INST 그룹의 바운딩 박스 계산"""
        all_points = []
        
        # INSTNO 원의 바운딩 박스
        center = Vec3(instno.dxf.center)
        radius = instno.dxf.radius
        all_points.extend([
            Vec3(center.x - radius, center.y - radius, center.z),
            Vec3(center.x + radius, center.y + radius, center.z)
        ])
        
        # INSTTAG 텍스트들
        for text in insttag_texts:
            all_points.append(Vec3(text.dxf.insert))
        
        # TBOX 점들
        if tbox:
            all_points.extend(self.get_entity_points(tbox))
        
        # ITAG 위치
        if itag:
            all_points.append(Vec3(itag.dxf.insert))
        
        # 최소/최대 좌표 계산
        min_x = min(p.x for p in all_points)
        min_y = min(p.y for p in all_points)
        max_x = max(p.x for p in all_points)
        max_y = max(p.y for p in all_points)
        
        return Vec3(min_x, min_y, 0), Vec3(max_x, max_y, 0)
    
    def check_interference(self, bbox_min: Vec3, bbox_max: Vec3, 
                          exclude_entities: set) -> bool:
        """바운딩 박스 내에 다른 엔티티와의 간섭 체크"""
        for entity in self.msp:
            if entity in exclude_entities:
                continue
            
            # 점 형태의 엔티티 체크
            if entity.dxftype() == "CIRCLE":
                center = Vec3(entity.dxf.center)
                if (bbox_min.x <= center.x <= bbox_max.x and 
                    bbox_min.y <= center.y <= bbox_max.y):
                    return True
            
            elif entity.dxftype() in ["POLYLINE", "LWPOLYLINE"]:
                points = self.get_entity_points(entity)
                for point in points:
                    if (bbox_min.x <= point.x <= bbox_max.x and 
                        bbox_min.y <= point.y <= bbox_max.y):
                        return True
            
            elif entity.dxftype() == "TEXT":
                pos = Vec3(entity.dxf.insert)
                if (bbox_min.x <= pos.x <= bbox_max.x and 
                    bbox_min.y <= pos.y <= bbox_max.y):
                    return True
        
        return False
    
    def move_inst_group(self, entities: List[DXFEntity], offset: Vec3):
        """INST 그룹 전체를 이동"""
        for entity in entities:
            if entity.dxftype() == "CIRCLE":
                center = Vec3(entity.dxf.center)
                entity.dxf.center = center + offset
            elif entity.dxftype() == "TEXT":
                pos = Vec3(entity.dxf.insert)
                entity.dxf.insert = pos + offset
            elif entity.dxftype() in ["POLYLINE", "LWPOLYLINE"]:
                entity.translate(offset.x, offset.y, offset.z)
    
    def create_line_and_trim(self, a2_far_point: Vec3, instno_center: Vec3, instno_radius: float):
        """A2 먼점과 INSTNO 중심 사이에 흰색 선을 그리고 원 안쪽 부분 TRIM"""
        # A2 먼점에서 INSTNO 중심까지의 거리
        total_distance = (instno_center - a2_far_point).magnitude
        
        if total_distance <= instno_radius:
            print("    - Warning: A2 far point is inside the circle")
            return
        
        # 원 둘레까지의 비율 계산
        ratio = (total_distance - instno_radius) / total_distance
        
        # 교점 계산 (A2 먼점에서 중심 방향으로 ratio만큼 이동)
        intersection = a2_far_point + (instno_center - a2_far_point) * ratio
        
        # 트림된 선 생성
        trimmed_line = self.msp.add_line(a2_far_point, intersection)
        trimmed_line.dxf.layer = "INSTG"
        trimmed_line.dxf.color = 7  # WHITE
        
        # 디버그 정보
        distance_check = (intersection - instno_center).magnitude
        print(f"    - Created trimmed white line, layer='INSTG'")
        print(f"    - Line length: {(intersection - a2_far_point).magnitude:.2f}mm")
        print(f"    - Distance from intersection to center: {distance_check:.3f}mm (radius: {instno_radius:.3f}mm)")
    
    def process_dxf_file(self, filepath: str):
        """DXF 파일 처리 메인 함수"""
        print(f"Processing: {filepath}")
        self.load_dxf(filepath)
        
        # 사용된 엔티티 초기화
        self.used_entities = set()
        self.instno_data = {}
        
        # 1. INSTNO 레이어의 원(CIRCLE) 찾기
        self.instno_circles = self.find_instno_circles()
        print(f"Found {len(self.instno_circles)} INSTNO circles")
        
        # A2 엔티티들을 저장할 리스트
        a2_entities_to_delete = []
        
        for idx, instno in enumerate(self.instno_circles):
            print(f"\nProcessing INSTNO {idx + 1}/{len(self.instno_circles)}")
            
            self.used_entities.add(instno)
            
            center = Vec3(instno.dxf.center)
            radius = instno.dxf.radius
            
            print(f"  - Circle center: {center}, radius: {radius:.2f}")
            
            # 2. A2 찾기 (1개만)
            a2 = self.find_a2_polyline(center, radius)
            if not a2:
                print("  - No A2 found")
                continue
            
            a2_entities_to_delete.append(a2)  # 나중에 삭제할 A2 저장
            
            # A2의 먼점 찾기
            a2_points = self.get_entity_points(a2)
            dist1 = (a2_points[0] - center).magnitude
            dist2 = (a2_points[-1] - center).magnitude
            a2_far_point = a2_points[0] if dist1 > dist2 else a2_points[-1]
            a2_near_point = a2_points[-1] if dist1 > dist2 else a2_points[0]
            
            print(f"  - A2 far point distance: {max(dist1, dist2):.2f}mm")
            print(f"  - A2 near point distance: {min(dist1, dist2):.2f}mm")
            
            # 3. TBOX 찾기
            tbox = self.find_tbox_near_tangent(center, radius)
            
            # 4. ITAG 찾기
            itag = self.find_itag_near_tangent(center, radius)
            
            if not tbox or not itag:
                print("  - TBOX or ITAG not found, skipping")
                continue
            
            # 5. FTP 찾기 (Y값이 가장 작은 접선점)
            ftp = self.find_ftp(center, radius)
            
            # 6. TPOS 찾기 (TBOX 점 중 FTP와 가장 가까운 점)
            tpos = self.find_tpos(tbox, ftp)
            
            # 7. TBOX와 ITAG를 FTP로 이동
            self.move_tbox_and_itag_to_ftp(tbox, itag, tpos, ftp)
            
            # 8. INSTTAG 텍스트들 찾기
            insttag_texts = self.find_insttag_texts(instno)
            print(f"  - Found {len(insttag_texts)} INSTTAG texts")
            
            # 9. INST 그룹 생성
            inst_entities = [instno] + insttag_texts
            if tbox:
                inst_entities.append(tbox)
            if itag:
                inst_entities.append(itag)
            
            # 10. INSTNO 중심과 A2 먼점 사이의 벡터
            center_to_far = a2_far_point - center
            current_distance = center_to_far.magnitude
            move_direction = center_to_far.normalize()
            
            # 11. 목표 위치 계산 (INSTNO 중심에서 A2 먼점 방향으로 15mm 지점)
            target_position = a2_far_point - move_direction * 15.0
            target_offset = target_position - center
            
            print(f"  - Current distance (center to A2 far): {current_distance:.2f}mm")
            print(f"  - Target distance: 15.0mm")
            print(f"  - Move offset: {target_offset}")
            
            # 원래 위치 저장
            original_positions = []
            for entity in inst_entities:
                if entity.dxftype() == "CIRCLE":
                    original_positions.append(("CIRCLE", Vec3(entity.dxf.center)))
                elif entity.dxftype() == "TEXT":
                    original_positions.append(("TEXT", Vec3(entity.dxf.insert)))
                elif entity.dxftype() in ["POLYLINE", "LWPOLYLINE"]:
                    original_positions.append(("POLYLINE", self.get_entity_points(entity).copy()))
            
            # 12. INST를 목표 위치로 이동
            self.move_inst_group(inst_entities, target_offset)
            
            # 13. 간섭 체크
            bbox_min, bbox_max = self.get_inst_bounding_box(instno, insttag_texts, tbox, itag)
            exclude_set = set(inst_entities + [a2])  # INST 그룹과 A2는 제외
            
            position_found = False
            total_offset = target_offset
            
            if not self.check_interference(bbox_min, bbox_max, exclude_set):
                position_found = True
                print(f"  - No interference at target position (15mm)")
            else:
                print(f"  - Interference detected at target position")
                
                # 3mm씩 후진하며 체크 (최대 5번 = 15mm)
                for step in range(1, 6):  # 3mm, 6mm, 9mm, 12mm, 15mm 후진
                    # 원래 위치 방향으로 3mm 후진
                    step_offset = -move_direction * 3.0
                    self.move_inst_group(inst_entities, step_offset)
                    total_offset = total_offset + step_offset
                    
                    bbox_min, bbox_max = self.get_inst_bounding_box(instno, insttag_texts, tbox, itag)
                    
                    if not self.check_interference(bbox_min, bbox_max, exclude_set):
                        position_found = True
                        print(f"  - No interference after {step * 3}mm retreat")
                        break
                    else:
                        print(f"  - Still interference after {step * 3}mm retreat")
                
                # 모든 위치에서 간섭 발생시 원래 위치로
                if not position_found:
                    print(f"  - Interference at all positions, returning to original")
                    # 원래 위치로 복원
                    current_offset = -total_offset
                    self.move_inst_group(inst_entities, current_offset)
                    total_offset = Vec3(0, 0, 0)  # 원래 위치로 돌아갔으므로 총 오프셋은 0
            
            # 14. 최종 위치 확정 후, 이동된 INSTNO 중심 계산
            final_center = center + total_offset
            print(f"  - Final INSTNO center: {final_center}")
            
            # 15. 위치 확정 후 선 그리기 및 TRIM (이동된 중심 사용)
            self.create_line_and_trim(a2_far_point, final_center, radius)
            
            # 레이어 변경
            for text in insttag_texts:
                text.dxf.layer = "INSTNOG"
            if tbox:
                tbox.dxf.layer = "INSTBOX"
            if itag:
                itag.dxf.layer = "INSTITEMNO"
            
            print(f"  - INSTNO group {idx + 1} processing completed")
        
        # 16. 모든 A2 삭제
        for a2 in a2_entities_to_delete:
            try:
                a2.destroy()
                print(f"Deleted A2 entity")
            except Exception as e:
                print(f"Failed to delete A2 entity: {e}")
        
        print(f"\nTotal A2 entities deleted: {len(a2_entities_to_delete)}")
        
        # 파일 저장
        output_path = filepath.replace('.dxf', '_INST.DXF').replace('.DXF', '_INST.DXF')
        self.doc.saveas(output_path)
        print(f"\nSaved to: {output_path}")

def main():
    processor = DXFProcessor()
    
    # DXF 파일 선택
    files = processor.select_dxf_files()
    
    if not files:
        print("No files selected")
        return
    
    # 각 파일 처리
    for filepath in files:
        try:
            processor.process_dxf_file(filepath)
        except Exception as e:
            print(f"Error processing {filepath}: {str(e)}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()