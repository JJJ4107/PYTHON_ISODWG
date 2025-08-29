import os
import sys
import math

try:
    import ezdxf
except ImportError:
    sys.exit(1)

# ─────────────────────────────────────────
# 상수 (AutoCAD ACI / ezdxf lineweight 단위는 0.01mm)
# ─────────────────────────────────────────
COLOR_RED = 1
COLOR_YELLOW = 2
COLOR_GREEN = 3
COLOR_CYAN = 4
COLOR_BLUE = 5
COLOR_WHITE = 7

LINEWEIGHT_0_60 = 60  # 0.60 mm

class DXFColorProcessor:
    def __init__(self):
        self.current_dir = os.path.dirname(os.path.abspath(__file__))

    # ─────────────────────────────────────────
    # 저장 파일명 규칙: <base_before_underscore>ACEPLANT.dxf
    # ─────────────────────────────────────────
    def get_clean_filename(self, original_file: str) -> str:
        d = os.path.dirname(original_file)
        base = os.path.splitext(os.path.basename(original_file))[0]
        if "_" in base:
            base = base.split("_")[0]
        if not base:
            base = os.path.splitext(os.path.basename(original_file))[0]
        return os.path.join(d, base + "ACEPLANT.dxf")

    # ─────────────────────────────────────────
    # 폴리라인 정점 수
    # ─────────────────────────────────────────
    def polyline_vertex_count(self, e) -> int:
        try:
            if e.dxftype() == "LWPOLYLINE":
                return len(list(e.get_points()))
            elif e.dxftype() == "POLYLINE":
                return len(list(e.vertices))
            else:
                return 0
        except Exception:
            return 0

    # ─────────────────────────────────────────
    # LINE → LWPOLYLINE (또는 POLYLINE) 변환
    # ─────────────────────────────────────────
    def _convert_line_to_lwpolyline(self, space, line_ent, color=None, lw=None):
        try:
            start = line_ent.dxf.start
            end = line_ent.dxf.end
            try:
                pl = space.add_lwpolyline([(start[0], start[1]), (end[0], end[1])])
                if lw is not None:
                    pl.dxf.const_width = lw / 100.0
                    pl.dxf.lineweight = int(lw)
                if color is not None:
                    pl.dxf.color = int(color)
                pl.dxf.layer = line_ent.dxf.layer
                if hasattr(line_ent.dxf, 'color') and color is None:
                    pl.dxf.color = line_ent.dxf.color
                space.delete_entity(line_ent)
                return pl
            except Exception:
                # 구버전 호환: POLYLINE으로 생성
                pl = space.add_polyline2d([(start[0], start[1]), (end[0], end[1])])
                if lw is not None:
                    width = lw / 100.0
                    for v in pl.vertices:
                        v.dxf.start_width = width
                        v.dxf.end_width = width
                if color is not None:
                    pl.dxf.color = int(color)
                pl.dxf.layer = line_ent.dxf.layer
                space.delete_entity(line_ent)
                return pl
        except Exception:
            return None

    # ─────────────────────────────────────────
    # POLYLINE(구형) → LWPOLYLINE 변환
    # ─────────────────────────────────────────
    def _convert_polyline_to_lwpolyline(self, space, old_poly, color=None, lw=None):
        pts = []
        closed = False
        try:
            closed = bool(old_poly.closed)
        except Exception:
            pass

        try:
            vertices = list(old_poly.vertices)
            for v in vertices:
                if hasattr(v.dxf, "location"):
                    x, y = float(v.dxf.location[0]), float(v.dxf.location[1])
                else:
                    x, y = float(v.dxf.x), float(v.dxf.y)
                pts.append((x, y))

            try:
                pl = space.add_lwpolyline(pts, dxfattribs={"closed": closed})
                if lw is not None:
                    pl.dxf.const_width = lw / 100.0
                    pl.dxf.lineweight = int(lw)
                if color is not None:
                    pl.dxf.color = int(color)
                pl.dxf.layer = old_poly.dxf.layer
                if hasattr(old_poly.dxf, 'color') and color is None:
                    pl.dxf.color = old_poly.dxf.color
                space.delete_entity(old_poly)
                return pl
            except Exception:
                # 변환 실패 시 속성만 변경
                if color is not None:
                    old_poly.dxf.color = int(color)
                if lw is not None:
                    width = lw / 100.0
                    for v in old_poly.vertices:
                        v.dxf.start_width = width
                        v.dxf.end_width = width
                return old_poly
        except Exception:
            return None

    # ─────────────────────────────────────────
    # TEXT/MTEXT → YELLOW
    # ─────────────────────────────────────────
    def _yellow_all_text(self, container):
        for e in list(container):
            try:
                if e.dxftype() in ("TEXT", "MTEXT"):
                    e.dxf.color = COLOR_YELLOW
            except Exception:
                pass

    # ─────────────────────────────────────────
    # PIPE/ELBO/TEE/TEXT 포함 레이어: LINE→LWPOLYLINE, BLUE + 0.6mm
    # ─────────────────────────────────────────
    def _enforce_blue_plines_for_pipe_elbo_tee_text(self, doc):
        def process_container(container):
            lines_to_convert = []
            for entity in list(container):
                try:
                    if not hasattr(entity, "dxf") or not hasattr(entity.dxf, "layer"):
                        continue
                    layer_upper = entity.dxf.layer.upper()
                    if ('PIPE' in layer_upper) or ('ELBO' in layer_upper) or ('TEE' in layer_upper) or ('TEXT' in layer_upper):
                        t = entity.dxftype()
                        if t == 'LINE':
                            lines_to_convert.append(entity)
                        elif t == 'POLYLINE':
                            entity.dxf.color = COLOR_BLUE
                            try:
                                for v in entity.vertices:
                                    v.dxf.start_width = 0.6
                                    v.dxf.end_width = 0.6
                            except Exception:
                                pass
                        elif t == 'LWPOLYLINE':
                            entity.dxf.color = COLOR_BLUE
                            entity.dxf.const_width = 0.6
                            entity.dxf.lineweight = LINEWEIGHT_0_60
                except Exception:
                    pass

            # 변환은 루프 밖에서
            for line in lines_to_convert:
                try:
                    self._convert_line_to_lwpolyline(
                        container, line, color=COLOR_BLUE, lw=LINEWEIGHT_0_60
                    )
                except Exception:
                    pass

        process_container(doc.modelspace())
        for layout in doc.layouts:
            if layout.name != "Model":
                process_container(layout)
        for block in doc.blocks:
            if not getattr(block, "name", "").startswith("*"):
                process_container(block)

    # ─────────────────────────────────────────
    # 빨간 폴리라인(또는 ByLayer=RED) → WHITE
    # ─────────────────────────────────────────
    def _whiten_red_polylines(self, doc):
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
                    col = getattr(e.dxf, "color", 256)
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

    # ─────────────────────────────────────────
    # CYAN 폴리라인(또는 ByLayer=CYAN) → WHITE
    # ─────────────────────────────────────────
    def _whiten_cyan_polylines(self, doc):
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
                    col = getattr(e.dxf, "color", 256)
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

    # ─────────────────────────────────────────
    # INSTNO CIRCLE → YELLOW, INSTBOX 폴리라인 → WHITE
    # ─────────────────────────────────────────
    def _instno_instbox_rules(self, doc):
        def process_container(container):
            for e in list(container):
                try:
                    layer = getattr(e.dxf, "layer", "")
                    u = layer.upper()
                    if u == "INSTNO" and e.dxftype() == "CIRCLE":
                        e.dxf.color = COLOR_YELLOW
                    elif u == "INSTBOX" and e.dxftype() in ("LWPOLYLINE", "POLYLINE"):
                        e.dxf.color = COLOR_WHITE
                except Exception:
                    pass

        process_container(doc.modelspace())
        for layout in doc.layouts:
            if layout.name != "Model":
                process_container(layout)
        for block in doc.blocks:
            process_container(block)

    # ─────────────────────────────────────────
    # PL2+GREEN → WHITE, GT_1+YELLOW → WHITE, SUPP+7점 → CYAN
    # ─────────────────────────────────────────
    def _specific_layer_color_rules(self, doc):
        def get_entity_color(e, doc):
            try:
                col = getattr(e.dxf, "color", 256)
                if col in (-1, 256):
                    layer_name = getattr(e.dxf, "layer", "")
                    if layer_name:
                        layer = doc.layers.get(layer_name)
                        if layer:
                            return getattr(layer.dxf, "color", 0)
                return col
            except Exception:
                return 0

        def process_container(container):
            for e in list(container):
                try:
                    if e.dxftype() not in ("LWPOLYLINE", "POLYLINE"):
                        continue
                    layer = getattr(e.dxf, "layer", "")
                    u = layer.upper()

                    if u == "PL2":
                        if get_entity_color(e, doc) == COLOR_GREEN:
                            e.dxf.color = COLOR_WHITE
                    elif u == "GT_1":
                        if get_entity_color(e, doc) == COLOR_YELLOW:
                            e.dxf.color = COLOR_WHITE
                    elif u == "SUPP":
                        vtx = self.polyline_vertex_count(e)
                        if vtx == 7:
                            e.dxf.color = COLOR_CYAN
                except Exception:
                    pass

        process_container(doc.modelspace())
        for layout in doc.layouts:
            if layout.name != "Model":
                process_container(layout)
        for block in doc.blocks:
            process_container(block)

    # ─────────────────────────────────────────
    # 기존 기본 룰 (요약 유지)
    #  - TEXT/MTEXT → YELLOW
    #  - ITEMNO/ITNO → WHITE
    #  - OLET/WOLET/REDU/VALV → YELLOW
    #  - 'PIPE' 포함 레이어의 LINE/PL → GREEN
    #  - 'TEE' 포함 레이어의 폴리라인 → CYAN
    #  - WDC 레이어 CIRCLE → WHITE
    # ─────────────────────────────────────────
    def _baseline_color_rules(self, doc):
        def is_pipe_layer(name: str) -> bool:
            return "PIPE" in (name or "").upper()

        def is_tee_layer(name: str) -> bool:
            return "TEE" in (name or "").upper()

        containers = [doc.modelspace()]
        containers.extend([l for l in doc.layouts if l.name != "Model"])
        containers.extend(list(doc.blocks))

        for container in containers:
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

    # ─────────────────────────────────────────
    # (옵션) 전체 레이어 ACEPLANT로 통일
    # ─────────────────────────────────────────
    def _unify_layers_to_aceplant(self, doc):
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

    # ─────────────────────────────────────────
    # 문서(메모리) 처리: 저장 없음
    # ─────────────────────────────────────────
    def process_doc(self, doc):
        # 1) 기본 룰
        self._baseline_color_rules(doc)
        # 2) PIPE/ELBO/TEE/TEXT 레이어 BLUE+0.6 & LINE→LWPOLYLINE
        self._enforce_blue_plines_for_pipe_elbo_tee_text(doc)
        # 3) 텍스트 보강 (전체 통합)
        self._yellow_all_text(doc.modelspace())
        for layout in doc.layouts:
            if layout.name != "Model":
                self._yellow_all_text(layout)
        for block in doc.blocks:
            self._yellow_all_text(block)
        # 4) RED PL → WHITE
        self._whiten_red_polylines(doc)
        # 5) CYAN PL → WHITE
        self._whiten_cyan_polylines(doc)
        # 6) PL2/GT_1/SUPP 세부 룰
        self._specific_layer_color_rules(doc)
        # 7) INSTNO/INSTBOX 룰
        self._instno_instbox_rules(doc)
        # 8) (옵션) 레이어 통일 필요 시 주석 해제
        # self._unify_layers_to_aceplant(doc)
        return doc

    # ─────────────────────────────────────────
    # 파일 1개 처리(읽기→가공→저장)
    # ─────────────────────────────────────────
    def process_file(self, path: str) -> bool:
        try:
            doc = ezdxf.readfile(path)
        except Exception:
            return False

        try:
            self.process_doc(doc)
        except Exception:
            return False

        out_path = self.get_clean_filename(path)
        tmp_path = out_path + ".tmp"
        try:
            try:
                doc.saveas(tmp_path)
            except Exception:
                doc.saveas(tmp_path, fmt="R2000")
            if os.path.exists(out_path):
                try:
                    os.remove(out_path)
                except Exception:
                    pass
            os.rename(tmp_path, out_path)
            return True
        except Exception:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
            return False

    # ─────────────────────────────────────────
    # 여러 파일 배치 처리 (명령행용)
    # ─────────────────────────────────────────
    def batch(self, files):
        if not files:
            return 0
        ok = 0
        for f in files:
            if self.process_file(f):
                ok += 1
        return ok


# ─────────────────────────────────────────
# in-memory 런너 호환 엔트리들
# ─────────────────────────────────────────
def process(doc):
    """
    런너(in-memory)에서 호출되는 표준 엔트리.
    전달된 ezdxf 문서를 메모리 상에서 수정하고 그대로 반환합니다.
    """
    try:
        processor = DXFColorProcessor()
        return processor.process_doc(doc)
    except Exception:
        return doc  # 실패 시에도 원본을 그대로 반환

# 호환 별칭
def pipeline(doc):
    return process(doc)

def main_process(doc):
    return process(doc)

# (선택) 파일 함수형 API
def process_file(path: str) -> bool:
    try:
        return DXFColorProcessor().process_file(path)
    except Exception:
        return False

# ─────────────────────────────────────────
# 명령행 실행: python THIS.py A.DXF B.DXF ...
# ─────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    files = sys.argv[1:]
    DXFColorProcessor().batch(files)
