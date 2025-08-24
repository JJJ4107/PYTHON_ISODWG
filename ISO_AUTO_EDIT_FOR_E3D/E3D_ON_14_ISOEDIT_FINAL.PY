import os
import sys
import math

try:
    import ezdxf
except ImportError:
    sys.exit(1)

# 색상 인덱스 (AutoCAD ACI)
COLOR_RED = 1
COLOR_YELLOW = 2
COLOR_GREEN = 3
COLOR_CYAN = 4
COLOR_BLUE = 5
COLOR_WHITE = 7

# 라인웨이트: ezdxf는 0.01mm 단위 정수 (0.60mm = 60)
LINEWEIGHT_0_60 = 60

class DXFColorProcessor:
    def __init__(self):
        self.current_dir = os.path.dirname(os.path.abspath(__file__))

    # -------------------------------
    # 파일명 정리: 기본이름에서 '_' 뒤 제거 후 'ACEPLANT.dxf' 접미
    # -------------------------------
    def get_clean_filename(self, original_file):
        d = os.path.dirname(original_file)
        base = os.path.splitext(os.path.basename(original_file))[0]
        if "_" in base:
            base = base.split("_")[0]
        if not base:
            base = os.path.splitext(os.path.basename(original_file))[0]
        return os.path.join(d, base + "ACEPLANT.dxf")

    # -------------------------------
    # 폴리라인 꼭짓점 개수
    # -------------------------------
    def polyline_vertex_count(self, e):
        try:
            if e.dxftype() == "LWPOLYLINE":
                # LWPOLYLINE.get_points() -> [(x, y, [start_width, end_width, bulge]), ...]
                return len(list(e.get_points()))
            elif e.dxftype() == "POLYLINE":
                return len(list(e.vertices))
            else:
                return 0
        except Exception:
            return 0

    # -------------------------------
    # LINE → LWPOLYLINE 변환 (첨부 코드와 동일한 방식)
    # -------------------------------
    def _convert_line_to_lwpolyline(self, space, line_ent, color=None, lw=None):
        try:
            # LINE의 시작점과 끝점 가져오기
            start = line_ent.dxf.start
            end = line_ent.dxf.end
            
            try:
                # LWPOLYLINE 생성 (첨부 코드와 동일한 방식)
                polyline = space.add_lwpolyline([(start[0], start[1]), (end[0], end[1])])
                
                # 선폭 설정 (const_width 사용)
                if lw is not None:
                    polyline.dxf.const_width = lw / 100.0  # ezdxf lineweight는 0.01mm 단위, const_width는 도면 단위
                
                # 색상 설정
                if color is not None:
                    polyline.dxf.color = int(color)
                
                # 속성 복사
                polyline.dxf.layer = line_ent.dxf.layer
                if hasattr(line_ent.dxf, 'color') and color is None:
                    polyline.dxf.color = line_ent.dxf.color
                
                # 기존 LINE 삭제
                space.delete_entity(line_ent)
                return polyline
                
            except Exception as e:
                # R2000 미만에서는 POLYLINE 사용
                polyline = space.add_polyline2d([(start[0], start[1]), (end[0], end[1])])
                # POLYLINE의 경우 각 정점에 폭 설정
                if lw is not None:
                    width = lw / 100.0
                    for vertex in polyline.vertices:
                        vertex.dxf.start_width = width
                        vertex.dxf.end_width = width
                
                if color is not None:
                    polyline.dxf.color = int(color)
                
                polyline.dxf.layer = line_ent.dxf.layer
                space.delete_entity(line_ent)
                return polyline
                
        except Exception as e:
            return None

    # -------------------------------
    # POLYLINE(구형) → LWPOLYLINE 변환 (첨부 코드와 동일한 방식)
    # -------------------------------
    def _convert_polyline_to_lwpolyline(self, space, old_poly, color=None, lw=None):
        pts = []
        closed = False
        try:
            closed = bool(old_poly.closed)
        except Exception:
            pass

        try:
            # 정점 수집
            vertices = list(old_poly.vertices)
            for v in vertices:
                if hasattr(v.dxf, "location"):
                    x, y = float(v.dxf.location[0]), float(v.dxf.location[1])
                else:
                    x, y = float(v.dxf.x), float(v.dxf.y)
                pts.append((x, y))
            
            try:
                # LWPOLYLINE 생성
                pl = space.add_lwpolyline(pts, dxfattribs={"closed": closed})
                
                # 선폭 설정 (const_width 사용)
                if lw is not None:
                    pl.dxf.const_width = lw / 100.0  # ezdxf lineweight는 0.01mm 단위
                    pl.dxf.lineweight = int(lw)
                
                # 색상 설정
                if color is not None:
                    pl.dxf.color = int(color)
                
                # 속성 복사
                pl.dxf.layer = old_poly.dxf.layer
                if hasattr(old_poly.dxf, 'color') and color is None:
                    pl.dxf.color = old_poly.dxf.color
                
                # 기존 POLYLINE 삭제
                space.delete_entity(old_poly)
                return pl
                
            except Exception as e:
                # 변환 실패 시 기존 POLYLINE의 속성만 변경
                if color is not None:
                    old_poly.dxf.color = int(color)
                if lw is not None:
                    width = lw / 100.0
                    for vertex in old_poly.vertices:
                        vertex.dxf.start_width = width
                        vertex.dxf.end_width = width
                return old_poly
                
        except Exception as e:
            return None

    # -------------------------------
    # TEXT/MTEXT → YELLOW
    # -------------------------------
    def _yellow_all_text(self, container):
        for e in list(container):
            try:
                if e.dxftype() in ("TEXT", "MTEXT"):
                    e.dxf.color = COLOR_YELLOW
            except Exception:
                pass

    # -------------------------------
    # PIPE/ELBO/TEE/TEXT 포함 레이어: LINE을 LWPOLYLINE으로 변환, BLUE + 0.6mm
    # (첨부 코드와 동일한 방식 사용)
    # -------------------------------
    def _enforce_blue_plines_for_pipe_elbo_tee_text(self, doc):
        # 변환 통계
        line_count = 0
        polyline_count = 0
        lwpolyline_count = 0
        
        def process_container(container, container_name):
            nonlocal line_count, polyline_count, lwpolyline_count
            
            # LINE을 변환할 리스트 (반복 중 삭제 방지)
            lines_to_convert = []
            
            for entity in list(container):
                try:
                    if hasattr(entity.dxf, 'layer'):
                        layer_upper = entity.dxf.layer.upper()
                        
                        # 레이어 이름에 PIPE, ELBO, TEE, TEXT가 포함되는지 확인 (첨부 코드 방식)
                        if 'PIPE' in layer_upper or 'ELBO' in layer_upper or 'TEE' in layer_upper or 'TEXT' in layer_upper:
                            dxft = entity.dxftype()
                            
                            if dxft == 'LINE':
                                lines_to_convert.append(entity)
                            elif dxft == 'POLYLINE':
                                # 기존 POLYLINE은 색상과 선폭만 변경
                                entity.dxf.color = COLOR_BLUE
                                # POLYLINE의 경우 각 정점에 폭 설정
                                try:
                                    for vertex in entity.vertices:
                                        vertex.dxf.start_width = 0.6
                                        vertex.dxf.end_width = 0.6
                                    polyline_count += 1
                                except Exception:
                                    pass
                            elif dxft == 'LWPOLYLINE':
                                # 기존 LWPOLYLINE은 색상과 선폭만 변경
                                entity.dxf.color = COLOR_BLUE
                                entity.dxf.const_width = 0.6  # LWPOLYLINE은 const_width 사용
                                entity.dxf.lineweight = LINEWEIGHT_0_60
                                lwpolyline_count += 1
                
                except Exception as e:
                    pass
            
            # LINE → LWPOLYLINE 변환
            for line in lines_to_convert:
                try:
                    # 첨부 코드와 동일한 방식으로 변환
                    start = line.dxf.start
                    end = line.dxf.end
                    
                    try:
                        # LWPOLYLINE 생성
                        polyline = container.add_lwpolyline([(start[0], start[1]), (end[0], end[1])])
                        polyline.dxf.const_width = 0.6  # 선폭 0.6mm
                        polyline.dxf.color = COLOR_BLUE  # BLUE
                        polyline.dxf.lineweight = LINEWEIGHT_0_60
                        
                        # 속성 복사
                        polyline.dxf.layer = line.dxf.layer
                        
                        # 기존 LINE 삭제
                        container.delete_entity(line)
                        line_count += 1
                        
                    except Exception as e1:
                        try:
                            # POLYLINE으로 대체 시도
                            polyline = container.add_polyline2d([(start[0], start[1]), (end[0], end[1])])
                            for vertex in polyline.vertices:
                                vertex.dxf.start_width = 0.6
                                vertex.dxf.end_width = 0.6
                            polyline.dxf.color = COLOR_BLUE
                            polyline.dxf.layer = line.dxf.layer
                            container.delete_entity(line)
                            line_count += 1
                        except Exception as e2:
                            pass
                            
                except Exception as e:
                    pass
        
        # Modelspace 처리
        process_container(doc.modelspace(), "Modelspace")
        
        # Paperspace layouts 처리
        for layout in doc.layouts:
            if layout.name != "Model":
                process_container(layout, f"Layout:{layout.name}")
        
        # Blocks 처리
        for block in doc.blocks:
            if not block.name.startswith('*'):  # 내부 블록 제외
                process_container(block, f"Block:{block.name}")

    # -------------------------------
    # 빨간색(RED) 모든 폴리라인 → WHITE (꼭짓점 수 무관)
    #  - ByLayer가 RED인 경우도 포함
    # -------------------------------
    def _whiten_red_polylines(self, doc):
        # 레이어 색상 조회 헬퍼
        def layer_is_red(layer_name):
            try:
                lay = doc.layers.get(layer_name)
                return getattr(lay.dxf, "color", 0) == COLOR_RED
            except Exception:
                return False

        def process_container(container):
            for e in list(container):
                try:
                    if e.dxftype() not in ("LWPOLYLINE", "POLYLINE"):
                        continue
                    # 꼭짓점 수 조건 제거 - 모든 RED 폴리라인을 WHITE로
                    col = getattr(e.dxf, "color", 256)  # 256=BYLAYER
                    is_red = (col == COLOR_RED) or (col in (-1, 256) and layer_is_red(getattr(e.dxf, "layer", "")))
                    if is_red:
                        e.dxf.color = COLOR_WHITE
                except Exception:
                    pass

        process_container(doc.modelspace())
        for layout in doc.layouts:
            if layout.name != "Model":
                process_container(layout)
        for block in doc.blocks:
            process_container(block)

    # -------------------------------
    # CYAN 폴리라인 → WHITE
    # -------------------------------
    def _whiten_cyan_polylines(self, doc):
        # 레이어 색상 조회 헬퍼
        def layer_is_cyan(layer_name):
            try:
                lay = doc.layers.get(layer_name)
                return getattr(lay.dxf, "color", 0) == COLOR_CYAN
            except Exception:
                return False

        def process_container(container):
            for e in list(container):
                try:
                    if e.dxftype() not in ("LWPOLYLINE", "POLYLINE"):
                        continue
                    col = getattr(e.dxf, "color", 256)  # 256=BYLAYER
                    is_cyan = (col == COLOR_CYAN) or (col in (-1, 256) and layer_is_cyan(getattr(e.dxf, "layer", "")))
                    if is_cyan:
                        e.dxf.color = COLOR_WHITE
                except Exception:
                    pass

        process_container(doc.modelspace())
        for layout in doc.layouts:
            if layout.name != "Model":
                process_container(layout)
        for block in doc.blocks:
            process_container(block)

    # -------------------------------
    # INSTNO 레이어의 원(CIRCLE) → YELLOW
    # INSTBOX 레이어의 폴리라인 → WHITE
    # -------------------------------
    def _instno_instbox_rules(self, doc):
        def process_container(container):
            for e in list(container):
                try:
                    layer = getattr(e.dxf, "layer", "")
                    layer_upper = layer.upper()
                    
                    # INSTNO 레이어의 CIRCLE → YELLOW
                    if layer_upper == "INSTNO" and e.dxftype() == "CIRCLE":
                        e.dxf.color = COLOR_YELLOW
                    
                    # INSTBOX 레이어의 폴리라인 → WHITE
                    elif layer_upper == "INSTBOX" and e.dxftype() in ("LWPOLYLINE", "POLYLINE"):
                        e.dxf.color = COLOR_WHITE
                        
                except Exception:
                    pass

        process_container(doc.modelspace())
        for layout in doc.layouts:
            if layout.name != "Model":
                process_container(layout)
        for block in doc.blocks:
            process_container(block)

    # -------------------------------
    # PL2 레이어 + GREEN 폴리라인 → WHITE
    # GT_1 레이어 + YELLOW 폴리라인 → WHITE
    # SUPP 레이어 + 7점 폴리라인 → CYAN
    # -------------------------------
    def _specific_layer_color_rules(self, doc):
        def get_entity_color(e, doc):
            """엔티티의 실제 색상을 가져옵니다 (ByLayer 처리 포함)"""
            try:
                col = getattr(e.dxf, "color", 256)
                if col in (-1, 256):  # ByLayer
                    layer_name = getattr(e.dxf, "layer", "")
                    if layer_name:
                        layer = doc.layers.get(layer_name)
                        if layer:
                            return getattr(layer.dxf, "color", 0)
                return col
            except Exception:
                return 0

        def process_container(container, doc):
            for e in list(container):
                try:
                    if e.dxftype() not in ("LWPOLYLINE", "POLYLINE"):
                        continue
                    
                    layer = getattr(e.dxf, "layer", "")
                    layer_upper = layer.upper()
                    
                    # PL2 레이어 + GREEN → WHITE
                    if layer_upper == "PL2":
                        if get_entity_color(e, doc) == COLOR_GREEN:
                            e.dxf.color = COLOR_WHITE
                    
                    # GT_1 레이어 + YELLOW → WHITE
                    elif layer_upper == "GT_1":
                        if get_entity_color(e, doc) == COLOR_YELLOW:
                            e.dxf.color = COLOR_WHITE
                    
                    # SUPP 레이어 + 7점 → CYAN
                    elif layer_upper == "SUPP":
                        vtx_count = self.polyline_vertex_count(e)
                        if vtx_count == 7:
                            e.dxf.color = COLOR_CYAN
                
                except Exception:
                    pass

        process_container(doc.modelspace(), doc)
        for layout in doc.layouts:
            if layout.name != "Model":
                process_container(layout, doc)
        for block in doc.blocks:
            process_container(block, doc)

    # -------------------------------
    # 기존 색상/레이어 처리(원 코드의 주요 로직 유지·요약)
    #  - TEXT: YELLOW
    #  - ITEMNO/ITNO: WHITE
    #  - OLET/WOLET/REDU/VALV: YELLOW
    #  - 'PIPE' 포함 레이어의 LINE/PL: GREEN
    #  - TEE 레이어 텍스트 근처 폴리라인: CYAN (간단화: 레이어명 'TEE' 포함인 경우로 처리)
    #  - WDC 레이어 CIRCLE: WHITE
    # -------------------------------
    def _baseline_color_rules(self, doc):
        def is_pipe_layer(name):
            return "PIPE" in (name or "").upper()

        def is_tee_layer(name):
            return "TEE" in (name or "").upper()

        for container in [doc.modelspace(), *[l for l in doc.layouts if l.name != "Model"], *list(doc.blocks)]:
            for e in list(container):
                try:
                    layer = (e.dxf.layer if hasattr(e.dxf, "layer") else "") or ""
                    u = layer.upper()
                    t = e.dxftype()

                    if t in ("TEXT", "MTEXT"):
                        e.dxf.color = COLOR_YELLOW
                    elif u in ("ITEMNO", "ITNO"):
                        e.dxf.color = COLOR_WHITE
                    elif u in ("OLET", "WOLET", "REDU", "VALV"):
                        e.dxf.color = COLOR_YELLOW
                    elif t in ("LINE", "LWPOLYLINE", "POLYLINE") and is_pipe_layer(layer):
                        e.dxf.color = COLOR_GREEN
                    elif t in ("LWPOLYLINE", "POLYLINE") and is_tee_layer(layer):
                        e.dxf.color = COLOR_CYAN
                    elif t == "CIRCLE" and u == "WDC":
                        e.dxf.color = COLOR_WHITE
                except Exception:
                    pass

    # -------------------------------
    # 모든 엔티티의 레이어를 'ACEPLANT' 로 통일 (선택사항: 기존 동작 유지)
    # -------------------------------
    def _unify_layers_to_aceplant(self, doc):
        # ACEPLANT 가 없으면 생성
        try:
            if "ACEPLANT" not in [l.dxf.name for l in doc.layers]:
                doc.layers.new(name="ACEPLANT")
        except Exception:
            pass

        def set_ace(container):
            for e in list(container):
                try:
                    e.dxf.layer = "ACEPLANT"
                except Exception:
                    pass

        set_ace(doc.modelspace())
        for layout in doc.layouts:
            if layout.name != "Model":
                set_ace(layout)
        for block in doc.blocks:
            set_ace(block)

        # 불필요한 레이어 삭제(ACEPLANT, 0 제외)
        try:
            to_remove = []
            for layer in doc.layers:
                nm = layer.dxf.name
                if nm not in ("ACEPLANT", "0"):
                    to_remove.append(nm)
            for nm in to_remove:
                try:
                    doc.layers.remove(nm)
                except Exception:
                    pass
        except Exception:
            pass

    # -------------------------------
    # DXF 1개 파일 처리
    # -------------------------------
    def process_one(self, path):
        try:
            doc = ezdxf.readfile(path)
        except Exception as e:
            return False

        # 파일의 모든 레이어 확인
        all_layers = set()
        msp = doc.modelspace()
        for entity in msp:
            if hasattr(entity.dxf, 'layer'):
                all_layers.add(entity.dxf.layer)

        # 1) 기본 룰 적용
        self._baseline_color_rules(doc)

        # 2) 추가 요구사항
        #   - 레이어명이 PIPE/ELBO/TEE/TEXT 포함 → LWPOLYLINE(BLUE, 0.6mm)
        self._enforce_blue_plines_for_pipe_elbo_tee_text(doc)

        #   - 모든 TEXT 는 YELLOW (보강)
        self._yellow_all_text(doc.modelspace())
        for layout in doc.layouts:
            if layout.name != "Model":
                self._yellow_all_text(layout)
        for block in doc.blocks:
            self._yellow_all_text(block)

        #   - 모든 RED 폴리라인은 WHITE (꼭짓점 수 무관)
        self._whiten_red_polylines(doc)

        #   - 모든 CYAN 폴리라인은 WHITE
        self._whiten_cyan_polylines(doc)

        #   - PL2/GREEN → WHITE, GT_1/YELLOW → WHITE, SUPP/7점 → CYAN
        self._specific_layer_color_rules(doc)

        #   - INSTNO 레이어의 원 → YELLOW, INSTBOX 레이어의 폴리라인 → WHITE
        self._instno_instbox_rules(doc)

        # 3) (옵션) 모든 레이어를 ACEPLANT 로 통일 (기존 코드 유지 원하시면 주석 해제)
        # self._unify_layers_to_aceplant(doc)

        # 4) 저장 (임시 → 최종명)
        out_path = self.get_clean_filename(path)
        tmp_path = out_path + ".tmp"
        try:
            # 파일 저장 (원본과 동일한 DXF 버전으로)
            try:
                doc.saveas(tmp_path)
            except:
                # 버전 문제가 있으면 R2000으로 저장
                doc.saveas(tmp_path, fmt='R2000')
            
            if os.path.exists(out_path):
                os.remove(out_path)
            os.rename(tmp_path, out_path)
            return True
        except Exception as e:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            return False

    # -------------------------------
    # 배치 처리
    # -------------------------------
    def run(self, files):
        if not files:
            return
        
        ok = 0
        for i, f in enumerate(files, 1):
            if self.process_one(f):
                ok += 1

# -------------------------------
# main
# -------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    
    files = sys.argv[1:]
    
    try:
        processor = DXFColorProcessor()
        processor.run(files)
    except Exception as e:
        pass