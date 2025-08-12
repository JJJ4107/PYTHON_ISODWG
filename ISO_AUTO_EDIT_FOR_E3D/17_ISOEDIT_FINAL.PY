import os
import sys
import tkinter as tk
from tkinter import filedialog, messagebox
import json

# DXF 파일 처리를 위한 ezdxf 라이브러리
try:
    import ezdxf
    EZDXF_AVAILABLE = True
except ImportError:
    EZDXF_AVAILABLE = False
    print("ezdxf 라이브러리가 필요합니다. 설치하세요: pip install ezdxf")

class DXFColorProcessor:
    def __init__(self):
        self.current_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_file = os.path.join(self.current_dir, "dxf_color_config.json")
        self.last_dxf_dir = self.load_last_directory()
        
        # DXF 색상 코드
        self.COLOR_WHITE = 7
        self.COLOR_YELLOW = 2
        self.COLOR_GREEN = 3
        self.COLOR_CYAN = 4
        
    def load_last_directory(self):
        """마지막으로 사용한 디렉토리 로드"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    config = json.load(f)
                    return config.get('last_dxf_dir', self.current_dir)
        except:
            pass
        return self.current_dir
    
    def save_last_directory(self, directory):
        """마지막 사용 디렉토리 저장"""
        try:
            config = {'last_dxf_dir': directory}
            with open(self.config_file, 'w') as f:
                json.dump(config, f)
        except:
            pass
    
    def select_dxf_files(self):
        """DXF 파일 선택 대화상자"""
        root = tk.Tk()
        root.withdraw()
        
        initial_dir = self.last_dxf_dir if os.path.exists(self.last_dxf_dir) else self.current_dir
        
        files = filedialog.askopenfilenames(
            title="처리할 DXF 파일을 선택하세요 (여러 개 선택 가능)",
            filetypes=[("DXF files", "*.dxf"), ("All files", "*.*")],
            initialdir=initial_dir
        )
        
        root.destroy()
        
        if files:
            self.last_dxf_dir = os.path.dirname(files[0])
            self.save_last_directory(self.last_dxf_dir)
        
        return list(files)
    
    def get_clean_filename(self, original_file):
        """파일명에서 _ 뒤의 내용을 제거하고 ACEPLANT를 추가한 이름 반환"""
        dir_name = os.path.dirname(original_file)
        base_name = os.path.splitext(os.path.basename(original_file))[0]
        
        # _ 문자가 있으면 그 앞까지만 사용
        if '_' in base_name:
            base_name = base_name.split('_')[0]
        
        # 빈 문자열이 되면 원본 이름 사용
        if not base_name:
            base_name = os.path.splitext(os.path.basename(original_file))[0]
        
        # ACEPLANT 추가
        clean_name = base_name + 'ACEPLANT.dxf'
        return os.path.join(dir_name, clean_name)
    
    def get_polyline_vertex_count(self, entity):
        """폴리라인의 정점 개수를 반환"""
        try:
            if entity.dxftype() == 'LWPOLYLINE':
                return len(list(entity.get_points()))
            elif entity.dxftype() == 'POLYLINE':
                return len(list(entity.vertices))
            else:
                return 0
        except:
            return 0
    
    def has_pipe_text_nearby(self, line_entity, doc, search_radius=50):
        """LINE 근처에 'PIPE TEXT'를 포함하는 텍스트가 있는지 확인"""
        try:
            # LINE의 중점 계산
            if hasattr(line_entity.dxf, 'start') and hasattr(line_entity.dxf, 'end'):
                mid_x = (line_entity.dxf.start[0] + line_entity.dxf.end[0]) / 2
                mid_y = (line_entity.dxf.start[1] + line_entity.dxf.end[1]) / 2
            else:
                return False
            
            # 모든 텍스트 엔티티 검색
            for entity in doc.modelspace():
                if entity.dxftype() in ['TEXT', 'MTEXT']:
                    text_content = ""
                    if entity.dxftype() == 'TEXT':
                        text_content = entity.dxf.text.upper() if hasattr(entity.dxf, 'text') else ""
                    elif entity.dxftype() == 'MTEXT':
                        text_content = entity.text.upper() if hasattr(entity, 'text') else ""
                    
                    if 'PIPE TEXT' in text_content:
                        # 텍스트 위치 확인
                        if hasattr(entity.dxf, 'insert'):
                            text_x = entity.dxf.insert[0]
                            text_y = entity.dxf.insert[1]
                            
                            # 거리 계산
                            distance = ((text_x - mid_x)**2 + (text_y - mid_y)**2)**0.5
                            if distance <= search_radius:
                                return True
            
            return False
        except:
            return False
    
    def has_text_layer_nearby(self, polyline_entity, doc, layer_name, search_radius=50):
        """폴리라인 근처에 특정 레이어의 텍스트가 있는지 확인"""
        try:
            # 폴리라인의 중점 계산
            points = []
            if polyline_entity.dxftype() == 'LWPOLYLINE':
                points = list(polyline_entity.get_points())
            elif polyline_entity.dxftype() == 'POLYLINE':
                points = [(v.dxf.location[0], v.dxf.location[1]) for v in polyline_entity.vertices]
            
            if not points:
                return False
            
            # 중점 계산
            mid_x = sum(p[0] for p in points) / len(points)
            mid_y = sum(p[1] for p in points) / len(points)
            
            # 모든 텍스트 엔티티 검색
            for entity in doc.modelspace():
                if entity.dxftype() in ['TEXT', 'MTEXT']:
                    # 텍스트의 레이어 확인
                    if hasattr(entity.dxf, 'layer') and entity.dxf.layer.upper() == layer_name.upper():
                        # 텍스트 위치 확인
                        if hasattr(entity.dxf, 'insert'):
                            text_x = entity.dxf.insert[0]
                            text_y = entity.dxf.insert[1]
                            
                            # 거리 계산
                            distance = ((text_x - mid_x)**2 + (text_y - mid_y)**2)**0.5
                            if distance <= search_radius:
                                return True
            
            return False
        except:
            return False
    
    def process_dxf_colors(self, dxf_file):
        """DXF 파일의 색상 변경 처리"""
        if not EZDXF_AVAILABLE:
            print(f"  ✗ ezdxf 라이브러리가 없어 색상 변경을 건너뜁니다.")
            return False
            
        try:
            print(f"\n색상 변경 중: {os.path.basename(dxf_file)}")
            
            # DXF 파일 읽기
            doc = ezdxf.readfile(dxf_file)
            
            text_count = 0
            line_count = 0
            pipe_text_line_count = 0
            pipe_layer_count = 0
            itemno_count = 0
            olet_count = 0
            polyline_3pt_count = 0
            tee_polyline_count = 0
            wdc_circle_count = 0
            
            # 모든 스페이스의 엔티티를 처리하는 함수
            def process_entities(entities, space_name=""):
                nonlocal text_count, line_count, pipe_text_line_count, pipe_layer_count, itemno_count, olet_count, polyline_3pt_count, tee_polyline_count, wdc_circle_count
                
                for entity in entities:
                    try:
                        layer_name = entity.dxf.layer.upper() if hasattr(entity.dxf, 'layer') else ""
                        
                        # 1. 모든 TEXT 엔티티를 YELLOW로 변경
                        if entity.dxftype() in ['TEXT', 'MTEXT']:
                            entity.dxf.color = self.COLOR_YELLOW
                            text_count += 1
                        
                        # 2. itemno와 ITNO 레이어는 흰색으로
                        elif layer_name in ['ITEMNO', 'ITNO']:
                            entity.dxf.color = self.COLOR_WHITE
                            itemno_count += 1
                        
                        # 3. OLET, WOLET, REDU, VALV 레이어는 YELLOW로
                        elif layer_name in ['OLET', 'WOLET', 'REDU', 'VALV']:
                            entity.dxf.color = self.COLOR_YELLOW
                            olet_count += 1
                        
                        # 4. LINE 처리
                        elif entity.dxftype() == 'LINE':
                            # 레이어 이름에 'PIPE'가 포함된 LINE은 GREEN으로
                            if 'PIPE' in layer_name:
                                entity.dxf.color = self.COLOR_GREEN
                                pipe_layer_count += 1
                            # PIPE TEXT가 포함된 LINE은 GREEN으로
                            elif self.has_pipe_text_nearby(entity, doc):
                                entity.dxf.color = self.COLOR_GREEN
                                pipe_text_line_count += 1
                        
                        # 5. POLYLINE/LWPOLYLINE 처리
                        elif entity.dxftype() in ['POLYLINE', 'LWPOLYLINE']:
                            # 레이어 이름에 'PIPE'가 포함된 폴리라인은 GREEN으로
                            if 'PIPE' in layer_name:
                                entity.dxf.color = self.COLOR_GREEN
                                pipe_layer_count += 1
                            # TEE 레이어 TEXT가 근처에 있는 폴리라인은 CYAN으로
                            elif self.has_text_layer_nearby(entity, doc, 'TEE'):
                                entity.dxf.color = self.COLOR_CYAN
                                tee_polyline_count += 1
                            # GREEN 색상의 PL2 레이어는 흰색으로
                            elif layer_name == 'PL2' and hasattr(entity.dxf, 'color') and entity.dxf.color == self.COLOR_GREEN:
                                entity.dxf.color = self.COLOR_WHITE
                                line_count += 1
                            # 3점 폴리라인으로 YELLOW 색상의 GT_1 레이어는 흰색으로
                            elif layer_name == 'GT_1' and hasattr(entity.dxf, 'color') and entity.dxf.color == self.COLOR_YELLOW:
                                vertex_count = self.get_polyline_vertex_count(entity)
                                if vertex_count == 3:
                                    entity.dxf.color = self.COLOR_WHITE
                                    polyline_3pt_count += 1
                            # 기존 규칙: CYAN, GREEN, YELLOW 색상의 GT_1 또는 PL2 레이어의 라인들을 흰색으로
                            elif layer_name in ['GT_1', 'PL2']:
                                if hasattr(entity.dxf, 'color') and entity.dxf.color in [self.COLOR_CYAN, self.COLOR_GREEN, self.COLOR_YELLOW]:
                                    # 위의 특별 규칙에 해당하지 않는 경우만 처리
                                    if not (layer_name == 'PL2' and entity.dxf.color == self.COLOR_GREEN) and \
                                       not (layer_name == 'GT_1' and entity.dxf.color == self.COLOR_YELLOW and self.get_polyline_vertex_count(entity) == 3):
                                        entity.dxf.color = self.COLOR_WHITE
                                        line_count += 1
                        
                        # 6. CIRCLE 처리 - WDC 레이어의 원은 흰색으로
                        elif entity.dxftype() == 'CIRCLE':
                            if layer_name == 'WDC':
                                entity.dxf.color = self.COLOR_WHITE
                                wdc_circle_count += 1
                    
                    except Exception as e:
                        print(f"    경고: {space_name} 엔티티 처리 중 오류: {str(e)}")
            
            # 모델스페이스 처리
            process_entities(doc.modelspace(), "모델스페이스")
            
            # 페이퍼스페이스 처리
            for layout in doc.layouts:
                if layout.name != 'Model':
                    process_entities(layout, f"레이아웃 '{layout.name}'")
            
            # 블록 내부 처리
            for block in doc.blocks:
                process_entities(block, f"블록 '{block.name}'")
            
            # 모든 레이어를 ACEPLANT로 변경
            print(f"  레이어 이름 변경 중...")
            
            # 모든 엔티티의 레이어를 ACEPLANT로 변경
            for entity in doc.modelspace():
                entity.dxf.layer = "ACEPLANT"
            
            # 페이퍼스페이스의 엔티티도 처리
            for layout in doc.layouts:
                if layout.name != 'Model':
                    for entity in layout:
                        try:
                            entity.dxf.layer = "ACEPLANT"
                        except:
                            pass
            
            # 블록 내부의 엔티티도 처리
            for block in doc.blocks:
                for entity in block:
                    try:
                        entity.dxf.layer = "ACEPLANT"
                    except:
                        pass
            
            # 기존 레이어들 삭제 (ACEPLANT와 0 레이어 제외)
            layers_to_delete = []
            for layer in doc.layers:
                if layer.dxf.name not in ['ACEPLANT', '0']:
                    layers_to_delete.append(layer.dxf.name)
            
            # ACEPLANT 레이어가 없으면 생성
            if 'ACEPLANT' not in [layer.dxf.name for layer in doc.layers]:
                doc.layers.new(name='ACEPLANT')
            
            # 불필요한 레이어 삭제
            for layer_name in layers_to_delete:
                try:
                    doc.layers.remove(layer_name)
                except:
                    pass
            
            # 최종 파일명 생성
            final_path = self.get_clean_filename(dxf_file)
            
            # 파일 저장 (백업 없이)
            # 임시 파일로 먼저 저장
            temp_file = final_path + '.tmp'
            doc.saveas(temp_file)
            
            # 기존 파일이 있으면 삭제
            if os.path.exists(final_path):
                os.remove(final_path)
            
            # 임시 파일을 최종 파일로 이름 변경
            os.rename(temp_file, final_path)
            
            print(f"  ✓ 색상 변경 완료:")
            print(f"    - TEXT를 YELLOW로 변경: {text_count}개")
            print(f"    - PIPE TEXT 근처 LINE을 GREEN으로 변경: {pipe_text_line_count}개")
            print(f"    - 'PIPE' 포함 레이어의 LINE/폴리라인을 GREEN으로 변경: {pipe_layer_count}개")
            print(f"    - TEE 레이어 TEXT 근처 폴리라인을 CYAN으로 변경: {tee_polyline_count}개")
            print(f"    - itemno/ITNO 레이어를 WHITE로 변경: {itemno_count}개")
            print(f"    - OLET/WOLET/REDU/VALV 레이어를 YELLOW로 변경: {olet_count}개")
            print(f"    - WDC 레이어의 원을 WHITE로 변경: {wdc_circle_count}개")
            print(f"    - GT_1 레이어의 3점 폴리라인을 WHITE로 변경: {polyline_3pt_count}개")
            print(f"    - 기타 GT_1/PL2 레이어의 선을 WHITE로 변경: {line_count}개")
            print(f"    - 모든 레이어를 ACEPLANT로 변경")
            print(f"  ✓ 저장 완료: {os.path.basename(final_path)}")
            
            return True
            
        except Exception as e:
            print(f"  ✗ 처리 실패: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def process_files(self):
        """선택된 DXF 파일들을 처리"""
        files = self.select_dxf_files()
        
        if not files:
            messagebox.showinfo("알림", "선택된 파일이 없습니다.")
            return
        
        print(f"\n{'='*60}")
        print(f"DXF 색상 변경 처리 시작")
        print(f"선택된 파일: {len(files)}개")
        for f in files:
            print(f"  - {os.path.basename(f)}")
        print(f"{'='*60}")
        
        success_count = 0
        
        # 각 파일을 개별적으로 처리
        for file_idx, dxf_file in enumerate(files, 1):
            print(f"\n[파일 {file_idx}/{len(files)}]")
            if self.process_dxf_colors(dxf_file):
                success_count += 1
        
        # 결과 출력
        print(f"\n\n{'='*60}")
        print("🎉 모든 처리가 완료되었습니다!")
        print(f"\n처리 결과:")
        print(f"  전체 파일: {len(files)}개")
        print(f"  성공: {success_count}개")
        print(f"  실패: {len(files) - success_count}개")
        print(f"{'='*60}")

def main():
    print("DXF 색상 변경 프로그램 v3.2")
    print("="*60)
    print("이 프로그램의 기능:")
    print("  1. 모든 TEXT를 YELLOW 색상으로 변경")
    print("  2. 'PIPE TEXT' 근처의 LINE을 GREEN 색상으로 변경")
    print("  3. 레이어 이름에 'PIPE'가 포함된 모든 LINE/폴리라인을 GREEN으로 변경")
    print("  4. TEE 레이어 TEXT 근처의 폴리라인을 CYAN 색상으로 변경")
    print("  5. itemno/ITNO 레이어를 WHITE 색상으로 변경")
    print("  6. OLET/WOLET/REDU/VALV 레이어를 YELLOW 색상으로 변경")
    print("  7. WDC 레이어의 원(CIRCLE)을 WHITE 색상으로 변경")
    print("  8. GREEN 색상의 PL2 레이어를 WHITE로 변경")
    print("  9. YELLOW 색상의 GT_1 레이어 3점 폴리라인을 WHITE로 변경")
    print("  10. 모든 레이어를 ACEPLANT로 통일")
    print("  11. 파일명에서 _ 뒤의 내용을 제거하고 'ACEPLANT.dxf'로 저장")
    print("      예: drawing_Final_v2.dxf → drawingACEPLANT.dxf")
    print("="*60)
    
    # ezdxf 라이브러리 확인
    if not EZDXF_AVAILABLE:
        print("\n⚠ ezdxf 라이브러리가 설치되어 있지 않습니다!")
        print("설치 명령어: pip install ezdxf")
        return
    
    try:
        # 버전 확인
        version = None
        if hasattr(ezdxf, '__version__'):
            version = ezdxf.__version__
        elif hasattr(ezdxf, 'version'):
            if isinstance(ezdxf.version, str):
                version = ezdxf.version
            elif hasattr(ezdxf.version, '__version__'):
                version = ezdxf.version.__version__
        
        if version:
            print(f"ezdxf 버전: {version}")
        else:
            print("ezdxf가 설치되어 있습니다.")
    except Exception as e:
        print(f"ezdxf 버전 확인 중 오류: {e}")
        print("ezdxf가 설치되어 있습니다.")
    
    processor = DXFColorProcessor()
    
    try:
        processor.process_files()
    except KeyboardInterrupt:
        print("\n\n사용자에 의해 중단되었습니다.")
    except Exception as e:
        print(f"\n\n오류 발생: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()