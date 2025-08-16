import ezdxf
import tkinter as tk
from tkinter import filedialog
import math
import os
from typing import List, Tuple, Set, Optional
import numpy as np

# AutoCAD 색상 인덱스
# 1 = Red, 2 = Yellow, 3 = Green, 4 = Cyan, 5 = Blue, 6 = Magenta, 7 = White

class DXFTeeEditor:
    def __init__(self):
        self.doc = None
        self.modelspace = None
        
    def select_dxf_files(self) -> List[str]:
        """DXF 파일 선택 다이얼로그"""
        root = tk.Tk()
        root.withdraw()
        files = filedialog.askopenfilenames(
            title="DXF 파일 선택",
            filetypes=[("DXF files", "*.dxf"), ("All files", "*.*")]
        )
        root.destroy()
        return list(files)
    
    def distance(self, p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
        """두 점 사이의 거리 계산"""
        return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)
    
    def get_slope(self, p1: Tuple[float, float], p2: Tuple[float, float]) -> Optional[float]:
        """두 점 사이의 기울기 계산"""
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        if abs(dx) < 0.001:  # 수직선
            return float('inf')
        return dy / dx
    
    def slopes_are_equal(self, slope1: float, slope2: float, tolerance: float = 0.1) -> bool:
        """두 기울기가 같은지 비교 (수직선 포함)"""
        # 둘 다 수직선인 경우
        if slope1 == float('inf') and slope2 == float('inf'):
            return True
        # 하나만 수직선인 경우
        if slope1 == float('inf') or slope2 == float('inf'):
            return False
        # 일반적인 경우
        return abs(slope1 - slope2) < tolerance
    
    def get_polyline_points(self, entity) -> List[Tuple[float, float]]:
        """폴리라인의 점들을 추출"""
        points = []
        if entity.dxftype() == 'LWPOLYLINE':
            points = [(p[0], p[1]) for p in entity.get_points()]
        elif entity.dxftype() == 'POLYLINE':
            points = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
        return points
    
    def find_tee_polylines(self) -> List:
        """TEE를 포함하는 레이어의 폴리라인 찾기"""
        tee_entities = []
        for entity in self.modelspace:
            if entity.dxftype() in ['LWPOLYLINE', 'POLYLINE']:
                if 'TEE' in entity.dxf.layer.upper():
                    tee_entities.append(entity)
        return tee_entities
    
    def find_all_connected_tee_pipe(self, start_entities: List, tolerance: float = 0.2) -> List:
        """TEE/PIPE를 재귀적으로 모두 찾기"""
        totee = []
        processed = set()
        to_process = list(start_entities)
        
        while to_process:
            current_entity = to_process.pop(0)
            
            if current_entity in processed:
                continue
                
            processed.add(current_entity)
            totee.append(current_entity)
            
            # 현재 엔티티의 끝점들 가져오기
            points = self.get_polyline_points(current_entity)
            if len(points) >= 2:
                endpoints = [points[0], points[-1]]
                slope = self.get_slope(points[0], points[-1])
                
                if slope is not None:
                    # 각 끝점에서 연결된 엔티티 찾기
                    for endpoint in endpoints:
                        # 모든 엔티티 검사
                        for entity in self.modelspace:
                            if entity in processed:
                                continue
                                
                            if entity.dxftype() in ['LWPOLYLINE', 'POLYLINE']:
                                layer_name = entity.dxf.layer.upper()
                                if 'TEE' in layer_name or 'PIPE' in layer_name:
                                    entity_points = self.get_polyline_points(entity)
                                    if len(entity_points) >= 2:
                                        # 양 끝점 확인
                                        for ep in [entity_points[0], entity_points[-1]]:
                                            if self.distance(endpoint, ep) <= tolerance:
                                                # 기울기 확인
                                                entity_slope = self.get_slope(entity_points[0], entity_points[-1])
                                                if entity_slope is not None and self.slopes_are_equal(entity_slope, slope):
                                                    to_process.append(entity)
                                                    break
        
        return totee
    
    def find_gt1_polylines(self, point: Tuple[float, float], tolerance: float = 0.3) -> List:
        """GT_1 레이어의 3점 폴리라인 찾기"""
        gt1_entities = []
        for entity in self.modelspace:
            if entity.dxftype() in ['LWPOLYLINE', 'POLYLINE']:
                if entity.dxf.layer == 'GT_1':
                    points = self.get_polyline_points(entity)
                    if len(points) == 3:
                        # 길이 계산
                        length = sum(self.distance(points[i], points[i+1]) 
                                   for i in range(len(points)-1))
                        if length <= 5:
                            # 점 근처에 있는지 확인
                            for p in points:
                                if self.distance(point, p) <= tolerance:
                                    gt1_entities.append(entity)
                                    break
        return gt1_entities
    
    def find_arrow_lines(self, point: Tuple[float, float], tolerance: float = 0.1) -> List:
        """ARROW 레이어의 LINE 찾기"""
        arrow_lines = []
        for entity in self.modelspace:
            if entity.dxftype() == 'LINE' and entity.dxf.layer == 'ARROW':
                start = (entity.dxf.start.x, entity.dxf.start.y)
                end = (entity.dxf.end.x, entity.dxf.end.y)
                length = self.distance(start, end)
                if length <= 1.0:
                    if self.distance(point, start) <= tolerance or \
                       self.distance(point, end) <= tolerance:
                        arrow_lines.append(entity)
        return arrow_lines
    
    def find_pl2_polylines(self, point: Tuple[float, float], tolerance: float = 0.1) -> List:
        """PL2 레이어의 폴리라인 찾기"""
        pl2_entities = []
        for entity in self.modelspace:
            if entity.dxftype() in ['LWPOLYLINE', 'POLYLINE']:
                if entity.dxf.layer == 'PL2':
                    points = self.get_polyline_points(entity)
                    for p in points:
                        if self.distance(point, p) <= tolerance:
                            pl2_entities.append(entity)
                            break
        return pl2_entities
    
    def find_text_in_range(self, point: Tuple[float, float], 
                          x_min: float, x_max: float, y_range: float) -> List:
        """특정 범위 내의 텍스트 찾기"""
        texts = []
        for entity in self.modelspace:
            if entity.dxftype() in ['TEXT', 'MTEXT']:
                # 텍스트 위치 가져오기
                if entity.dxftype() == 'TEXT':
                    text_pos = (entity.dxf.insert.x, entity.dxf.insert.y)
                    text_content = entity.dxf.text
                else:  # MTEXT
                    text_pos = (entity.dxf.insert.x, entity.dxf.insert.y)
                    text_content = entity.text
                
                if (point[0] + x_min <= text_pos[0] <= point[0] + x_max and
                    abs(text_pos[1] - point[1]) <= y_range):
                    if 'DN' in text_content and 'x' in text_content:
                        # 기울기가 0인지 확인 (수평 텍스트)
                        if entity.dxftype() == 'TEXT':
                            rotation = entity.dxf.rotation if hasattr(entity.dxf, 'rotation') else 0
                            if abs(rotation) < 0.1:
                                texts.append(entity)
                        else:
                            texts.append(entity)
        return texts
    
    def find_el_fl_text(self, t1_entity, y_offset: float = 7.0) -> Optional:
        """EL 또는 FL을 포함하는 텍스트 찾기"""
        t1_pos = (t1_entity.dxf.insert.x, t1_entity.dxf.insert.y)
        search_pos = (t1_pos[0], t1_pos[1] - y_offset)
        
        for entity in self.modelspace:
            if entity.dxftype() in ['TEXT', 'MTEXT']:
                text_pos = (entity.dxf.insert.x, entity.dxf.insert.y)
                if self.distance(search_pos, text_pos) <= 0.5:
                    if entity.dxftype() == 'TEXT':
                        text_content = entity.dxf.text
                    else:  # MTEXT
                        text_content = entity.text
                    
                    if 'EL' in text_content or 'FL' in text_content:
                        return entity
        return None
    
    def create_typ_text(self, ref_entity, y_offset: float = 6.2):
        """(TYP.) 텍스트 생성"""
        # 참조 텍스트의 위치 가져오기
        ref_x = ref_entity.dxf.insert.x
        ref_y = ref_entity.dxf.insert.y
        
        # 새 텍스트 위치
        new_x = ref_x
        new_y = ref_y - y_offset
        
        # dxfattribs 딕셔너리 생성
        attribs = {
            'height': ref_entity.dxf.height,
            'layer': ref_entity.dxf.layer,
            'color': 4,  # CYAN 색상
        }
        
        # style 속성이 있으면 추가
        if hasattr(ref_entity.dxf, 'style'):
            attribs['style'] = ref_entity.dxf.style
        
        # rotation 속성이 있으면 추가
        if hasattr(ref_entity.dxf, 'rotation'):
            attribs['rotation'] = ref_entity.dxf.rotation
        
        # 텍스트 생성
        text = self.modelspace.add_text('(TYP.)', dxfattribs=attribs)
        
        # 위치 설정
        text.set_placement((new_x, new_y))
        
        return text
    
    def process_dxf_file(self, filepath: str):
        """DXF 파일 처리"""
        self.doc = ezdxf.readfile(filepath)
        self.modelspace = self.doc.modelspace()
        
        # 1. TEE를 포함하는 폴리라인 찾기
        initial_tee = self.find_tee_polylines()
        
        # 2. TEE에서 시작해서 연결된 모든 TEE/PIPE 찾기
        print(f"  - 초기 TEE 엔티티 수: {len(initial_tee)}")
        totee = self.find_all_connected_tee_pipe(initial_tee)
        print(f"  - 연결된 전체 TEE/PIPE 수: {len(totee)}")
        
        # 3. 각 끝점에서 GT_1, ARROW, PL2 찾기
        all_results = []
        
        for entity in totee:
            points = self.get_polyline_points(entity)
            if len(points) >= 2:
                for tp in [points[0], points[-1]]:
                    # AD1 (GT_1) 찾기
                    ad1_list = self.find_gt1_polylines(tp)
                    
                    for ad1 in ad1_list:
                        ad1_points = self.get_polyline_points(ad1)
                        
                        # AD2 (ARROW) 찾기
                        ad2_list = []
                        for p in ad1_points:
                            ad2_list.extend(self.find_arrow_lines(p))
                        
                        # AD3 (PL2) 찾기
                        ad3_list = []
                        for p in ad1_points:
                            ad3_list.extend(self.find_pl2_polylines(p))
                        
                        for ad3 in ad3_list:
                            ad3_points = self.get_polyline_points(ad3)
                            if ad3_points:
                                # AP1, AP2 결정
                                distances = [(p, self.distance(p, tp)) for p in ad3_points]
                                distances.sort(key=lambda x: x[1])
                                ap1 = distances[0][0]
                                ap2 = distances[-1][0]
                                
                                # T1 찾기
                                t1_list = self.find_text_in_range(ap2, -40, 15, 7)
                                
                                for t1 in t1_list:
                                    # T2 찾기
                                    t2 = self.find_el_fl_text(t1)
                                    
                                    all_results.append({
                                        'tp': tp,
                                        'ad1': ad1,
                                        'ad2': ad2_list,
                                        'ad3': ad3,
                                        't1': t1,
                                        't2': t2,
                                        't1_text': t1.dxf.text
                                    })
        
        # 4. 동일한 T1 텍스트 그룹화
        text_groups = {}
        for result in all_results:
            text = result['t1_text']
            if text not in text_groups:
                text_groups[text] = []
            text_groups[text].append(result)
        
        # 5. 각 그룹 처리
        entities_to_delete = []
        entities_to_color_cyan = []  # CYAN으로 변경할 엔티티들
        
        for text, group in text_groups.items():
            # T2가 있는 항목 찾기
            with_t2 = [r for r in group if r['t2'] is not None]
            
            if with_t2:
                # T2가 있는 첫 번째 항목 보존
                keep = with_t2[0]
                self.create_typ_text(keep['t2'])
                
                # 보존할 엔티티들을 CYAN 리스트에 추가
                entities_to_color_cyan.append(keep['ad1'])
                entities_to_color_cyan.extend(keep['ad2'])
                entities_to_color_cyan.append(keep['ad3'])
                entities_to_color_cyan.append(keep['t1'])
                if keep['t2']:
                    entities_to_color_cyan.append(keep['t2'])
                
                # 나머지 삭제
                for r in group:
                    if r != keep:
                        entities_to_delete.extend([r['ad1']] + r['ad2'] + [r['ad3'], r['t1']])
                        if r['t2']:
                            entities_to_delete.append(r['t2'])
            else:
                # T2가 없으면 첫 번째 항목만 보존
                keep = group[0]
                self.create_typ_text(keep['t1'])
                
                # 보존할 엔티티들을 CYAN 리스트에 추가
                entities_to_color_cyan.append(keep['ad1'])
                entities_to_color_cyan.extend(keep['ad2'])
                entities_to_color_cyan.append(keep['ad3'])
                entities_to_color_cyan.append(keep['t1'])
                
                # 나머지 삭제
                for r in group[1:]:
                    entities_to_delete.extend([r['ad1']] + r['ad2'] + [r['ad3'], r['t1']])
        
        # 6. TOTEE 엔티티들을 흰색으로 변경
        for entity in totee:
            if entity:
                try:
                    entity.dxf.color = 7  # 흰색
                except:
                    pass
        
        # 7. 선택된 AD1, AD2, AD3, T1, T2를 CYAN으로 변경
        for entity in entities_to_color_cyan:
            if entity:
                try:
                    entity.dxf.color = 4  # CYAN
                except:
                    pass
        
        # 8. 엔티티 삭제
        for entity in entities_to_delete:
            if entity:
                try:
                    self.modelspace.remove(entity)
                except:
                    pass
        
        # 9. 파일 저장
        base_name = os.path.splitext(os.path.basename(filepath))[0]
        output_path = os.path.join(os.path.dirname(filepath), f"{base_name}_TEEDIT.DXF")
        self.doc.saveas(output_path)
        print(f"처리 완료: {output_path}")

def main():
    # ezdxf 버전 확인
    print(f"ezdxf 버전: {ezdxf.__version__}")
    print("\nDXF TEE Editor")
    print("=" * 50)
    print("기능:")
    print("1. TEE 레이어에서 시작하여 연결된 모든 TEE/PIPE 찾기")
    print("   - 양 끝점에서 0.2mm 이내의 동일 기울기 폴리라인 검색")
    print("   - 더 이상 연결된 것이 없을 때까지 재귀적으로 탐색")
    print("\n2. 색상 변경:")
    print("   - TOTEE (TEE/PIPE 레이어): 흰색(White)")
    print("   - AD1, AD2, AD3, T1, T2, (TYP.): 청록색(Cyan)")
    print("=" * 50)
    
    editor = DXFTeeEditor()
    files = editor.select_dxf_files()
    
    if not files:
        print("파일이 선택되지 않았습니다.")
        return
    
    print(f"\n선택된 파일 수: {len(files)}")
    
    for file in files:
        try:
            print(f"\n처리 중: {file}")
            editor.process_dxf_file(file)
        except Exception as e:
            print(f"오류 발생: {file}")
            print(f"오류 내용: {str(e)}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    main()