# -*- coding: utf-8 -*-
"""
mto_fallback_reader.py

헤더(TEXT 'PT', 'COMPONENT', 'SIZE', "Q'TY", 'WEIGHT')가 도면에 표시되지 않은 경우,
고정 좌표(열 X)와 허용 오차(±X tol)를 사용하여
PT/COMP/SIZE/QTY/WEIGHT 열을 스캔해 행 단위로 읽어오는 유틸리티.

■ 제공 함수
- read_rows_headerless(doc, msp, ...): ezdxf 문서/모델스페이스에서 직접 읽기
- read_rows_headerless_from_file(file_path, ...): DXF 파일 경로에서 읽기

■ 반환 형식 (리스트[딕셔너리])
[
  {
    'pt': '101',
    'comp': 'PIPE, SMLS, A106B, S-40',
    'size': 'DN50',
    'qty': '2',
    'weight': '3.5',
    'totxt': '해당 행의 전체 텍스트(좌→우 병합)',
    'y_pos': 512.3
  },
  ...
]
"""

import math
import re
from typing import Dict, List, Tuple, Iterable, Optional

try:
    import ezdxf
except ImportError:
    ezdxf = None  # 가져다 쓰는 쪽에서 보장해야 함.

# ──────────────────────────────────────────────────────────────────────────────
# 기본 좌표/파라미터 (필요시 인자에서 덮어쓰기)
DEFAULT_FALLBACK_COLS = {
    'PT': 618.0,
    'COMPONENT': 630.0,
    'SIZE': 738.0,
    "Q'TY": 766.0,
    'WEIGHT': 793.2,
}
DEFAULT_Y_HEADER = 546.0   # 헤더가 있다고 가정되는 Y (여기서 아래로 스캔 시작)
DEFAULT_Y_LIMIT  = 250.0   # 스캔 하한 Y
DEFAULT_X_TOL    = 9.0     # 열 X 허용오차 (±)
DEFAULT_Y_MERGE_TOL = 2.0  # 같은 행으로 볼 Y 간격 허용오차
DEFAULT_STOP_KEYWORDS = ('ERECTION WEIGHT',)  # 나오면 이후 행 무시
# ──────────────────────────────────────────────────────────────────────────────


# ─────────────── 내부 유틸 ───────────────
def _get_xy(e) -> Tuple[float, float]:
    """TEXT/MTEXT/INSERT 내부 텍스트 등에서 좌표 가져오기."""
    try:
        if hasattr(e, 'dxf') and hasattr(e.dxf, 'insert'):
            ins = e.dxf.insert
            if hasattr(ins, 'x') and hasattr(ins, 'y'):
                return float(ins.x), float(ins.y)
            elif isinstance(ins, (tuple, list)) and len(ins) >= 2:
                return float(ins[0]), float(ins[1])
        elif hasattr(e, 'insert'):
            ins = e.insert
            if isinstance(ins, (tuple, list)) and len(ins) >= 2:
                return float(ins[0]), float(ins[1])
    except Exception:
        pass
    return 0.0, 0.0


def _get_text(e) -> str:
    """TEXT/MTEXT의 문자열 가져오기."""
    try:
        if hasattr(e, 'dxf') and hasattr(e.dxf, 'text'):
            return e.dxf.text
        elif hasattr(e, 'text'):
            return e.text
    except Exception:
        pass
    return ''


def _collect_all_texts_with_blocks(doc, msp) -> List[Tuple[float, float, str, str]]:
    """
    모델공간 + 블록 내부 TEXT/MTEXT를 절대좌표로 모두 수집.
    반환: 리스트[(x, y, txt, source)], source in {'normal', 'block'}
    """
    all_texts = []

    # 1) 모델공간
    for e in msp.query('TEXT MTEXT'):
        txt = _get_text(e).strip()
        x, y = _get_xy(e)
        if txt:
            all_texts.append((x, y, txt, 'normal'))

    # 2) 블록 내부
    for insert in msp.query('INSERT'):
        try:
            insert_point = insert.dxf.insert
            x_scale = getattr(insert.dxf, 'xscale', 1.0)
            y_scale = getattr(insert.dxf, 'yscale', 1.0)
            rotation = getattr(insert.dxf, 'rotation', 0.0)
            block_name = insert.dxf.name
            if block_name not in doc.blocks:
                continue

            block = doc.blocks[block_name]
            rad = math.radians(rotation)
            cos_r = math.cos(rad)
            sin_r = math.sin(rad)

            for entity in block:
                if entity.dxftype() not in ('TEXT', 'MTEXT'):
                    continue
                txt = _get_text(entity).strip()
                if not txt:
                    continue
                local_x, local_y = _get_xy(entity)

                if rotation != 0:
                    abs_x = insert_point[0] + (local_x * cos_r - local_y * sin_r) * x_scale
                    abs_y = insert_point[1] + (local_x * sin_r + local_y * cos_r) * y_scale
                else:
                    abs_x = insert_point[0] + local_x * x_scale
                    abs_y = insert_point[1] + local_y * y_scale

                all_texts.append((abs_x, abs_y, txt, 'block'))
        except Exception:
            # 손상된 블록이 있어도 전체 처리는 계속
            continue

    return all_texts


def _merge_y_positions(y_values: Iterable[float], y_tol: float) -> List[float]:
    """Y 좌표들을 내림차순으로 정렬하고, y_tol 이내는 같은 행으로 취급해 대표값만 남긴다."""
    ys = sorted(set(y_values), reverse=True)
    merged = []
    for y in ys:
        if not merged:
            merged.append(y)
            continue
        if abs(merged[-1] - y) <= y_tol:
            # 같은 행으로 판단 → 건너뜀(가장 먼저(큰 Y) 남김)
            continue
        merged.append(y)
    return merged


# ─────────────── 공개 함수 ───────────────
def read_rows_headerless(
    doc,
    msp,
    fallback_cols: Dict[str, float] = None,
    y_header: float = DEFAULT_Y_HEADER,
    y_limit: float = DEFAULT_Y_LIMIT,
    x_tol: float = DEFAULT_X_TOL,
    y_merge_tol: float = DEFAULT_Y_MERGE_TOL,
    stop_keywords: Tuple[str, ...] = DEFAULT_STOP_KEYWORDS,
    require_numeric_pt: bool = False,
) -> List[Dict[str, str]]:
    """
    헤더가 없을 때, 고정 X(±x_tol) 창과 Y 범위를 이용하여
    PT / COMPONENT / SIZE / Q'TY / WEIGHT 행을 읽어온다.

    Parameters
    ----------
    doc, msp : ezdxf 문서와 모델스페이스
    fallback_cols : 각 열의 기준 X 값 딕셔너리
        예) {'PT': 618.0, 'COMPONENT': 630.0, 'SIZE': 738.0, "Q'TY": 766.0, 'WEIGHT': 793.2}
    y_header : 스캔 시작 Y (이 값 아래로만 스캔)
    y_limit  : 스캔 하한 Y
    x_tol    : 각 열 X 허용오차 (±x_tol)
    y_merge_tol : 같은 행으로 볼 수 있는 Y 차이
    stop_keywords : 행의 전체 텍스트(totxt)에 포함되면 이후 행 무시
    require_numeric_pt : True면 PT가 순수 숫자인 행만 반환

    Returns
    -------
    List[Dict[str, str]]: 각 행 딕셔너리
        keys = 'pt', 'comp', 'size', 'qty', 'weight', 'totxt', 'y_pos'
    """
    if fallback_cols is None:
        fallback_cols = DEFAULT_FALLBACK_COLS

    # 모든 텍스트 수집
    all_texts = _collect_all_texts_with_blocks(doc, msp)

    # 열 윈도우 (Xmin, Xmax)
    col_windows = {
        name: (xc - x_tol, xc + x_tol) for name, xc in fallback_cols.items()
    }

    # 행 후보 Y 수집 (모든 열 윈도우에 들어오는 텍스트의 Y를 모은 후 병합)
    y_candidates = []
    for x, y, txt, _src in all_texts:
        if not txt:
            continue
        if (y < y_header - 5.0) and (y >= y_limit):
            for (xmin, xmax) in col_windows.values():
                if xmin <= x <= xmax:
                    y_candidates.append(y)
                    break
    merged_y_positions = _merge_y_positions(y_candidates, y_merge_tol)

    rows: List[Dict[str, str]] = []
    stop_detected = False

    for data_y in merged_y_positions:
        # 열별 토큰과 행 전체 토큰 수집
        per_col_tokens = {k: [] for k in col_windows.keys()}
        row_tokens_for_totxt = []

        for x, y, txt, _src in all_texts:
            if not txt:
                continue
            if abs(y - data_y) <= y_merge_tol:
                matched_any = False
                for col_name, (xmin, xmax) in col_windows.items():
                    if xmin <= x <= xmax:
                        per_col_tokens[col_name].append((x, y, txt))
                        matched_any = True
                if matched_any:
                    row_tokens_for_totxt.append((x, y, txt))

        # 열별 X 정렬
        for col in per_col_tokens:
            per_col_tokens[col].sort(key=lambda t: t[0])
        row_tokens_for_totxt.sort(key=lambda t: t[0])

        # 문자열 생성
        pt_value     = ' '.join([t[2] for t in per_col_tokens.get('PT', [])]).strip()
        comp_value   = ' '.join([t[2] for t in per_col_tokens.get('COMPONENT', [])]).strip()
        size_value   = ' '.join([t[2] for t in per_col_tokens.get('SIZE', [])]).strip()
        qty_value    = ' '.join([t[2] for t in per_col_tokens.get("Q'TY", [])]).strip()
        weight_value = ' '.join([t[2] for t in per_col_tokens.get('WEIGHT', [])]).strip()
        totxt        = ' '.join([t[2] for t in row_tokens_for_totxt]).strip()

        if not any([pt_value, comp_value, size_value, qty_value, weight_value]):
            # 완전 빈 행은 패스
            continue

        # 중단 키워드 체크
        if any(kw.upper() in totxt.upper() for kw in stop_keywords):
            stop_detected = True
            break

        # PT 숫자 강제 옵션
        if require_numeric_pt:
            if not re.fullmatch(r'\d+(\.\d+)?', pt_value or ''):
                continue

        rows.append({
            'pt': pt_value,
            'comp': comp_value,
            'size': size_value,
            'qty': qty_value,
            'weight': weight_value,
            'totxt': totxt,
            'y_pos': data_y,
        })

    # stop_detected는 사용처에서 필요시 활용 가능
    return rows


def read_rows_headerless_from_file(
    file_path: str,
    fallback_cols: Dict[str, float] = None,
    y_header: float = DEFAULT_Y_HEADER,
    y_limit: float = DEFAULT_Y_LIMIT,
    x_tol: float = DEFAULT_X_TOL,
    y_merge_tol: float = DEFAULT_Y_MERGE_TOL,
    stop_keywords: Tuple[str, ...] = DEFAULT_STOP_KEYWORDS,
    require_numeric_pt: bool = False,
) -> List[Dict[str, str]]:
    """
    DXF 파일 경로에서 바로 읽어서 headerless 행들을 반환.
    """
    if ezdxf is None:
        raise RuntimeError("ezdxf가 설치되어 있어야 합니다. pip install ezdxf")

    doc = ezdxf.readfile(file_path)
    msp = doc.modelspace()
    return read_rows_headerless(
        doc,
        msp,
        fallback_cols=fallback_cols,
        y_header=y_header,
        y_limit=y_limit,
        x_tol=x_tol,
        y_merge_tol=y_merge_tol,
        stop_keywords=stop_keywords,
        require_numeric_pt=require_numeric_pt,
    )


# ─────────────── 사용 예시 (직접 실행 시) ───────────────
if __name__ == "__main__":
    """
    python mto_fallback_reader.py path/to/file.dxf
    """
    import sys
    if len(sys.argv) < 2:
        print("사용법: python mto_fallback_reader.py <dxf_file>")
        sys.exit(0)

    path = sys.argv[1]
    rows = read_rows_headerless_from_file(
        path,
        fallback_cols=DEFAULT_FALLBACK_COLS,
        y_header=DEFAULT_Y_HEADER,
        y_limit=DEFAULT_Y_LIMIT,
        x_tol=DEFAULT_X_TOL,
        y_merge_tol=DEFAULT_Y_MERGE_TOL,
        stop_keywords=DEFAULT_STOP_KEYWORDS,
        require_numeric_pt=False,  # 필요시 True
    )
    print(f"[{path}] 추출 행 수: {len(rows)}")
    for r in rows[:10]:
        print(f"Y={r['y_pos']:.1f} | PT='{r['pt']}' | COMP='{r['comp']}' | SIZE='{r['size']}' | QTY='{r['qty']}' | WGT='{r['weight']}'")