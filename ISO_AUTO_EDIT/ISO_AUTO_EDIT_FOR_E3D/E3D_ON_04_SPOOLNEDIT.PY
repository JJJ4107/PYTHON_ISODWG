#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
E3D_ON_04_SPOOLNEDIT
- in-memory runner 연동용 process(doc) 제공 (pipeline/run/main_process 별칭 포함)
- CLI: python E3D_ON_04_SPOOLNEDIT.py A.DXF B.DXF ...  (여러 DXF 처리, 자동 *_SPN.dxf 저장)
- tkinter/print 사용 없음, 실패는 최대한 조용히 무시하고 다음 파일 진행
"""

import os
import re
import sys
from typing import Any, List, Tuple, Optional

import ezdxf  # pip install ezdxf

# 전역 위치 기억 변수(문서 처리마다 process()에서 설정)
ESNP = None  # (x, y)
ESLP = None  # (x, y)


# ──────────────────────────────────────────────────────────────────────────────
# 내부 유틸
def _text_of(e) -> str:
    try:
        if hasattr(e, "plain_text"):
            return (e.plain_text() or "").strip()
        if hasattr(e, "dxf") and hasattr(e.dxf, "text"):
            return (e.dxf.text or "").strip()
    except Exception:
        pass
    return ""


def extract_texts(msp) -> List[Tuple[str, float, float, Any]]:
    out = []
    try:
        for e in msp.query("TEXT"):
            try:
                if hasattr(e, "dxf") and hasattr(e.dxf, "insert"):
                    txt = _text_of(e)
                    out.append((txt, float(e.dxf.insert.x), float(e.dxf.insert.y), e))
            except Exception:
                continue
    except Exception:
        pass
    return out


def find_pipe_spools(texts) -> Tuple[Optional[str], Optional[float], Optional[float]]:
    try:
        for text, x, y, _ in texts:
            if "PIPE SPOOLS" in (text or "").upper():
                return text.strip(), x, y
    except Exception:
        pass
    return None, None, None


def find_spna_all(texts, spn_x: float, spn_y: float) -> List[Tuple[str, float, float]]:
    spna_list = []
    try:
        for text, x, y, _ in texts:
            if -50 <= y - spn_y <= 0 and 0 <= x - spn_x <= 220:
                if ("-S" in text) or ("-P" in text):
                    spna_list.append((text.strip().replace("0", "O"), x, y))
    except Exception:
        pass
    return spna_list


def find_spnb_and_spnbl(texts):
    """
    SPNB: (150<=x<=250, 0<=y<=95) & '-S' or '-P'
    BL:   오른쪽 0<dx<=95, |dy|<=5 이고 숫자 포함
    반환: (spnb_text, x, y, spnb_e, style, spnbl_text, bl_x, bl_y, bl_e)
    """
    results = []
    try:
        for text, x, y, e in texts:
            if 150 <= x <= 250 and 0 <= y <= 95 and (("-S" in text) or ("-P" in text)):
                try:
                    style = e.dxf.style if hasattr(e.dxf, "style") else "STANDARD"
                except Exception:
                    style = "STANDARD"

                spnb_text = text.strip()
                spnbl_text = "-"
                spnbl_x = x
                spnbl_y = y
                spnbl_e = None

                for t2, x2, y2, e2 in texts:
                    try:
                        if 0 < x2 - x <= 95 and abs(y2 - y) <= 5 and re.search(r"\d+", t2 or ""):
                            bl_candidate = "".join((t2 or "").split())
                            if bl_candidate:
                                spnbl_text = bl_candidate
                                spnbl_x = x2
                                spnbl_y = y2
                                spnbl_e = e2
                                break
                    except Exception:
                        continue

                results.append((spnb_text, x, y, e, style, spnbl_text, spnbl_x, spnbl_y, spnbl_e))
    except Exception:
        pass
    return results


def find_bl_for_spna(texts, spna_x: float, spna_y: float):
    bl_text = "-"
    bl_x = spna_x
    bl_y = spna_y
    bl_e = None
    try:
        for t2, x2, y2, e2 in texts:
            if 0 < x2 - spna_x <= 95 and abs(y2 - spna_y) <= 5 and re.search(r"\d+", t2 or ""):
                bl_candidate = "".join((t2 or "").split())
                if bl_candidate:
                    bl_text = bl_candidate
                    bl_x = x2
                    bl_y = y2
                    bl_e = e2
                    break
    except Exception:
        pass
    return bl_text, bl_x, bl_y, bl_e


def replace_tall_texts(msp):
    to_update = []
    try:
        for e in msp.query("TEXT"):
            try:
                if not hasattr(e, "dxf") or not hasattr(e.dxf, "text"):
                    continue
                text = (e.dxf.text or "").strip()
                if ("-S" in text) or ("-P" in text):
                    match = re.search(r"(-[SP])(.*)", text)
                    if match:
                        prefix = match.group(1)
                        tb = (match.group(2) or "").strip()
                        ta = text.split(prefix)[0].strip()
                        ta = ta.replace("O", "0")

                        numeric_part = re.sub(r"[^0-9]", "", tb)
                        if len(numeric_part) > 1:
                            has_over_10 = any(
                                int(numeric_part[i : i + 2]) > 9
                                for i in range(len(numeric_part) - 1)
                            )
                        else:
                            has_over_10 = False

                        tb_new = tb.replace("O", "", 1) if has_over_10 else tb
                        new_value = ta + prefix + tb_new
                        to_update.append((e, new_value))
            except Exception:
                continue

        for e, val in to_update:
            try:
                e.dxf.text = val
            except Exception:
                continue
    except Exception:
        pass


def replace_O_to_0_for_SPNA_SPNA_ESN(msp):
    try:
        for e in msp.query("TEXT"):
            try:
                if not hasattr(e, "dxf") or not hasattr(e.dxf, "text"):
                    continue
                layer = getattr(e.dxf, "layer", "") or ""
                text = e.dxf.text or ""
                if (layer == "ESN") or ("-S" in text) or ("-P" in text):
                    if "O" in text:
                        e.dxf.text = text.replace("O", "0")
            except Exception:
                continue
    except Exception:
        pass


def _make_output_path(input_path: str, suffix: str = "_SPN.dxf") -> str:
    base = os.path.basename(input_path or "unnamed.dxf")
    name, _ = os.path.splitext(base)
    out_name = f"{name}{suffix}"
    target_dir = os.path.dirname(input_path) if input_path else ""
    if (not target_dir) or (not os.path.isdir(target_dir)) or (not os.access(target_dir, os.W_OK)):
        target_dir = os.getcwd()
    return os.path.join(target_dir, out_name)


def _safe_save(doc, desired_path: str) -> Optional[str]:
    try:
        doc.saveas(desired_path)
        return desired_path
    except Exception:
        base_name = os.path.splitext(os.path.basename(desired_path))[0]
        for i in range(1, 1001):
            alt = os.path.join(os.getcwd(), f"{base_name}_{i}.dxf")
            try:
                doc.saveas(alt)
                return alt
            except Exception:
                continue
    return None


# ──────────────────────────────────────────────────────────────────────────────
# 핵심 처리 (런너용): 타입힌트는 Any로 유지하여 실행시 AttributeError 방지
def process(doc: Any) -> Any:
    """
    in-memory 문서를 입력받아 ESN/ESL 생성 및 보정 수행.
    저장/입출력 없음. 예외는 내부에서 조용히 처리 후 doc 반환.
    """
    global ESNP, ESLP
    try:
        try:
            msp = doc.modelspace()
        except Exception:
            doc = ezdxf.new("R2018")
            msp = doc.modelspace()

        texts = extract_texts(msp)

        spn_text, spn_x, spn_y = find_pipe_spools(texts)
        if spn_text is None:
            spn_x, spn_y = 0.0, 0.0

        spna_list = find_spna_all(texts, spn_x, spn_y)
        spnb_data = find_spnb_and_spnbl(texts)

        dy = 5.5
        index = 0

        if spnb_data:
            try:
                ESNP = (float(spnb_data[0][1]), float(spnb_data[0][2]))
                ESLP = (float(spnb_data[0][6]), float(spnb_data[0][7]))
            except Exception:
                ESNP = (219.0, 63.0)
                ESLP = (279.0, 63.0)
        else:
            ESNP = (219.0, 63.0)
            ESLP = (279.0, 63.0)

        # 기존 SPNB/BL 제거
        try:
            for _, _, _, spnb_e, _, _, _, _, spnbl_e in spnb_data:
                try:
                    if spnb_e is not None:
                        msp.delete_entity(spnb_e)
                except Exception:
                    pass
                try:
                    if spnbl_e is not None:
                        msp.delete_entity(spnbl_e)
                except Exception:
                    pass
        except Exception:
            pass

        # 매칭 우선 경로
        if spnb_data:
            for spna_text, _, _ in spna_list:
                matched = False
                esn_val = spna_text
                esl_val = "-"

                spna_no_ws = "".join((spna_text or "").split())
                try:
                    for spnb_text, _, _, _, _, spnbl_text, _, _, _ in spnb_data:
                        spnb_no_ws = "".join((spnb_text or "").replace("0", "O").split())
                        if spna_no_ws in spnb_no_ws:
                            esn_val = spnb_text
                            esl_candidate = spnbl_text if spnbl_text else "-"
                            esl_val = "".join((esl_candidate or "").split()) if "".join((esl_candidate or "").split()) else "-"
                            matched = True
                            break
                except Exception:
                    pass

                if (esl_val == "-") and matched:
                    try:
                        for spnb_text, _, _, _, _, spnbl_text, _, _, _ in spnb_data:
                            spnb_no_ws = "".join((spnb_text or "").replace("0", "O").split())
                            if spna_no_ws in spnb_no_ws:
                                bl_force = "".join((spnbl_text or "").split())
                                if bl_force:
                                    esl_val = bl_force
                                break
                    except Exception:
                        pass

                try:
                    msp.add_text(
                        esn_val,
                        dxfattribs={
                            "insert": (ESNP[0], ESNP[1] - dy * index),
                            "height": 2.5,
                            "layer": "ESN",
                            "color": 2,
                            "style": "STANDARD",
                        },
                    )
                except Exception:
                    pass

                try:
                    msp.add_text(
                        esl_val,
                        dxfattribs={
                            "insert": (ESLP[0], ESLP[1] - dy * index),
                            "height": 2.5,
                            "layer": "ESL",
                            "color": 2,
                            "style": "STANDARD",
                        },
                    )
                except Exception:
                    pass

                index += 1
        else:
            # BL 직접 탐색
            for spna_text, spna_x, spna_y in spna_list:
                esn_val = spna_text
                bl_text, _, _, _ = find_bl_for_spna(texts, spna_x, spna_y)
                bl_text_clean = "".join((bl_text or "").split()) if bl_text else ""
                esl_val = bl_text_clean if bl_text_clean else "-"

                try:
                    msp.add_text(
                        esn_val,
                        dxfattribs={
                            "insert": (ESNP[0], ESNP[1] - dy * index),
                            "height": 2.5,
                            "layer": "ESN",
                            "color": 2,
                            "style": "STANDARD",
                        },
                    )
                except Exception:
                    pass

                try:
                    msp.add_text(
                        esl_val,
                        dxfattribs={
                            "insert": (ESLP[0], ESLP[1] - dy * index),
                            "height": 2.5,
                            "layer": "ESL",
                            "color": 2,
                            "style": "STANDARD",
                        },
                    )
                except Exception:
                    pass

                index += 1

        # 보정 단계
        try:
            replace_tall_texts(msp)
        except Exception:
            pass
        try:
            replace_O_to_0_for_SPNA_SPNA_ESN(msp)
        except Exception:
            pass

    except Exception:
        pass

    return doc


# 별칭(호환)
def pipeline(doc: Any) -> Any:
    return process(doc)


def run(doc: Any) -> Any:
    return process(doc)


def main_process(doc: Any) -> Any:
    return process(doc)


# ──────────────────────────────────────────────────────────────────────────────
# 경로 기반 처리(읽기→process→저장)
def process_file(input_path: str) -> Optional[str]:
    doc = None
    try:
        if input_path and os.path.exists(input_path):
            try:
                doc = ezdxf.readfile(input_path)
            except Exception:
                doc = ezdxf.new("R2018")
        else:
            doc = ezdxf.new("R2018")
    except Exception:
        doc = ezdxf.new("R2018")

    try:
        doc = process(doc)
    except Exception:
        pass

    try:
        out_path = _make_output_path(input_path, suffix="_SPN.dxf")
        saved = _safe_save(doc, out_path)
        return saved
    except Exception:
        try:
            fallback = ezdxf.new("R2018")
            saved = _safe_save(fallback, os.path.join(os.getcwd(), "unnamed_SPN.dxf"))
            return saved
        except Exception:
            return None


def main():
    # CLI: python E3D_ON_04_SPOOLNEDIT.py A.DXF B.DXF ...
    args = sys.argv[1:]
    files = [p for p in args if isinstance(p, str) and p.lower().endswith(".dxf")]
    for fp in files:
        try:
            process_file(fp)
        except Exception:
            continue


if __name__ == "__main__":
    main()
