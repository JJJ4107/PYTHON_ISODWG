# ------------------ paste-start: arial & spacing utils ------------------
# 목적:
# - TEXT/MTEXT를 ARIAL 스타일로 통일
# - TEXT의 width factor(폭 비율) 적용
# - 단어 사이 공백(" ")을 2/3-em 유니코드 공백으로 치환하여 길이 일관화
#
# 사용법 예:
#   doc = ezdxf.readfile(path)
#   msp = doc.modelspace()
#   n = apply_arial_and_spacing(doc, msp, x_min=600, x_max=850, y_bottom=250, y_top=550,
#                               width_factor=0.87, style_name="ARIAL", font_file="arial.ttf")
#   print("updated:", n)
#   doc.saveas(new_path)

import ezdxf

# 기본값 상수
DEFAULT_STYLE_NAME = "ARIAL"
DEFAULT_FONT_FILE  = "arial.ttf"
DEFAULT_WIDTH_FACTOR = 0.87

# 유니코드 공백: 1/3-em 두 개 = 2/3-em
THREE_PER_EM   = "\u2004"                     # 1/3 em
TWO_THIRDS_EM  = THREE_PER_EM + THREE_PER_EM  # 2/3 em

def ensure_text_style(doc, style_name: str = DEFAULT_STYLE_NAME,
                      font_file: str = DEFAULT_FONT_FILE,
                      width_factor: float = DEFAULT_WIDTH_FACTOR):
    """ARIAL 스타일이 없으면 생성하고, width_factor를 통일."""
    try:
        style = doc.styles.get(style_name)
    except ezdxf.DXFKeyError:
        style = doc.styles.new(style_name, dxfattribs={"font": font_file})
    try:
        style.dxf.width_factor = width_factor
    except Exception:
        pass
    return style

def replace_spaces_two_thirds_em(text: str) -> str:
    """일반 스페이스(' ')를 2/3-em 공백으로 치환 (TEXT/MTEXT 공통, 인라인 코드 미사용)."""
    if not text:
        return text
    return text.replace(" ", TWO_THIRDS_EM)

def get_text_reference_xy(e):
    """좌표 필터링용 기준점: TEXT는 align_point 우선, 없으면 insert / MTEXT는 insert."""
    try:
        if e.dxftype() == "TEXT":
            if e.dxf.hasattr("align_point"):
                ap = e.dxf.align_point
                if ap is not None:
                    ax, ay = float(ap[0]), float(ap[1])
                    if ax != 0.0 or ay != 0.0:
                        return ax, ay
            ins = getattr(e.dxf, "insert", None)
            if ins is not None:
                return float(ins[0]), float(ins[1])
        elif e.dxftype() == "MTEXT":
            ins = getattr(e.dxf, "insert", None)
            if ins is not None:
                return float(ins[0]), float(ins[1])
    except Exception:
        return None
    return None

def is_in_band(xy, x_min, x_max, y_bottom, y_top):
    if xy is None:
        return False
    px, py = xy
    return (x_min <= px <= x_max) and (min(y_bottom, y_top) <= py <= max(y_bottom, y_top))

def apply_arial_and_spacing(doc, msp,
                            x_min=None, x_max=None, y_bottom=None, y_top=None,
                            width_factor: float = DEFAULT_WIDTH_FACTOR,
                            style_name: str = DEFAULT_STYLE_NAME,
                            font_file: str = DEFAULT_FONT_FILE):
    """
    TEXT/MTEXT에 대해:
      - 스타일 style_name(기본 ARIAL)로 통일
      - TEXT는 폭 비율(width factor) 설정
      - TEXT/MTEXT 모두 단어 사이 공백을 2/3-em으로 치환
    좌표 범위(x_min~x_max, y_bottom~y_top)를 모두 지정하면 해당 구간에만 적용.
    범위를 하나도 지정하지 않으면 전체에 적용.
    반환값: 변경된 엔티티 수
    """
    ensure_text_style(doc, style_name=style_name, font_file=font_file, width_factor=width_factor)
    count = 0

    for e in msp:
        if e.dxftype() not in ("TEXT", "MTEXT"):
            continue

        # 좌표 필터: 범위를 모두 제공한 경우에만 필터링
        if None not in (x_min, x_max, y_bottom, y_top):
            xy = get_text_reference_xy(e)
            if not is_in_band(xy, x_min, x_max, y_bottom, y_top):
                continue

        # 스타일 통일
        try:
            e.dxf.style = style_name
        except Exception:
            pass

        # 폭 비율: TEXT에만 개별 속성 설정 (MTEXT는 스타일 width_factor가 기본 적용)
        if e.dxftype() == "TEXT":
            try:
                e.dxf.width = width_factor
            except Exception:
                pass
            # 공백 치환
            try:
                e.dxf.text = replace_spaces_two_thirds_em(e.dxf.text)
            except Exception:
                pass
        else:  # MTEXT
            try:
                e.text = replace_spaces_two_thirds_em(e.text)
            except Exception:
                pass

        count += 1

    return count
# ------------------ paste-end: arial & spacing utils ------------------