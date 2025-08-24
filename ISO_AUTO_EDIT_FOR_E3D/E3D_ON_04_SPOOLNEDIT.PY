import ezdxf
import os
import re
import sys

# 전역 위치 기억 변수
ESNP = None  # (x, y)
ESLP = None  # (x, y)

def extract_texts(msp):
    texts = []
    for e in msp.query("TEXT"):
        if hasattr(e, "dxf") and hasattr(e.dxf, "insert"):
            texts.append((e.plain_text().strip(), e.dxf.insert.x, e.dxf.insert.y, e))
    return texts

def find_pipe_spools(texts):
    for text, x, y, _ in texts:
        if "PIPE SPOOLS" in text.upper():
            return text.strip(), x, y
    return None, None, None

def find_spna_all(texts, spn_x, spn_y):
    spna_list = []
    for text, x, y, e in texts:
        if -50 <= y - spn_y <= 0 and 0 <= x - spn_x <= 220:
            if "-S" in text or "-P" in text:
                spna_list.append((text.strip().replace("0", "O"), x, y))
    return spna_list

def find_spnb_and_spnbl(texts):
    results = []
    for text, x, y, e in texts:
        if 150 <= x <= 250 and 0 <= y <= 95 and ("-S" in text or "-P" in text):
            style = e.dxf.style if hasattr(e.dxf, "style") else "STANDARD"
            spnb_text = text.strip()
            spnbl_text = "-"
            spnbl_x = x
            spnbl_y = y
            spnbl_e = None
            for t2, x2, y2, e2 in texts:
                if 0 < x2 - x <= 95 and abs(y2 - y) <= 5 and re.search(r'\d+', t2):
                    bl_candidate = ''.join(t2.split())
                    if bl_candidate:
                        spnbl_text = bl_candidate
                        spnbl_x = x2
                        spnbl_y = y2
                        spnbl_e = e2
                        break
            results.append((spnb_text, x, y, e, style, spnbl_text, spnbl_x, spnbl_y, spnbl_e))
    return results

def find_bl_for_spna(texts, spna_x, spna_y):
    bl_text = "-"
    bl_x = spna_x
    bl_y = spna_y
    bl_e = None
    for t2, x2, y2, e2 in texts:
        if 0 < x2 - spna_x <= 95 and abs(y2 - spna_y) <= 5 and re.search(r'\d+', t2):
            bl_candidate = ''.join(t2.split())
            if bl_candidate:
                bl_text = bl_candidate
                bl_x = x2
                bl_y = y2
                bl_e = e2
                break
    return bl_text, bl_x, bl_y, bl_e

def replace_tall_texts(msp):
    new_texts = []
    for e in msp.query("TEXT"):
        if not hasattr(e, "dxf") or not hasattr(e.dxf, "text"):
            continue
        text = e.dxf.text.strip()
        if "-S" in text or "-P" in text:
            match = re.search(r"(-[SP])(.*)", text)
            if match:
                prefix = match.group(1)
                tb = match.group(2).strip()
                ta = text.split(prefix)[0].strip()
                ta = ta.replace("O", "0")
                numeric_part = re.sub(r"[^0-9]", "", tb)
                has_over_10 = any(int(numeric_part[i:i+2]) > 9 for i in range(len(numeric_part)-1)) if len(numeric_part) > 1 else False
                if has_over_10:
                    tb_new = tb.replace("O", "", 1)
                else:
                    tb_new = tb
                new_value = ta + prefix + tb_new
                new_texts.append((e, new_value))
    for e, new_val in new_texts:
        e.dxf.text = new_val

def replace_O_to_0_for_SPNA_SPNA_ESN(msp):
    for e in msp.query("TEXT"):
        if not hasattr(e, "dxf") or not hasattr(e.dxf, "text"):
            continue
        layer = getattr(e.dxf, "layer", "")
        text = e.dxf.text
        if (layer == "ESN") or ("-S" in text or "-P" in text):
            if "O" in text:
                e.dxf.text = text.replace("O", "0")

def _make_output_path(input_path, suffix="_SPN.dxf"):
    base = os.path.basename(input_path)
    name, _ = os.path.splitext(base)
    out_name = f"{name}{suffix}"
    target_dir = os.path.dirname(input_path)
    if not target_dir or not os.path.isdir(target_dir) or not os.access(target_dir, os.W_OK):
        target_dir = os.getcwd()
    return os.path.join(target_dir, out_name)

def _safe_save(doc, desired_path):
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

def final_main():
    global ESNP, ESLP
    args = sys.argv[1:]
    files = [p for p in args if p.lower().endswith(".dxf")]
    for filepath in files:
        doc = None
        try:
            if os.path.exists(filepath):
                doc = ezdxf.readfile(filepath)
            else:
                doc = ezdxf.new("R2018")
        except Exception:
            doc = ezdxf.new("R2018")

        try:
            msp = doc.modelspace()
        except Exception:
            # 최소 구조 생성 보장
            doc = ezdxf.new("R2018")
            msp = doc.modelspace()

        try:
            texts = extract_texts(msp)
            spn_text, spn_x, spn_y = find_pipe_spools(texts)
            if spn_text is None:
                spn_x, spn_y = 0, 0

            spna_list = find_spna_all(texts, spn_x, spn_y)
            spnb_data = find_spnb_and_spnbl(texts)

            dy = 5.5
            index = 0

            if spnb_data:
                ESNP = (spnb_data[0][1], spnb_data[0][2])
                ESLP = (spnb_data[0][6], spnb_data[0][7])
            else:
                ESNP = (219, 63)
                ESLP = (279, 63)

            for _, _, _, spnb_e, _, _, _, _, spnbl_e in spnb_data:
                try:
                    if hasattr(spnb_e, "dxf"):
                        msp.delete_entity(spnb_e)
                except Exception:
                    pass
                try:
                    if spnbl_e and hasattr(spnbl_e, "dxf"):
                        msp.delete_entity(spnbl_e)
                except Exception:
                    pass

            if spnb_data:
                for spna_text, _, _ in spna_list:
                    matched = False
                    esn_val = spna_text
                    esl_val = "-"
                    spna_no_ws = ''.join(spna_text.split())
                    for spnb_text, _, _, _, _, spnbl_text, _, _, _ in spnb_data:
                        spnb_no_ws = ''.join(spnb_text.replace("0", "O").split())
                        if spna_no_ws in spnb_no_ws:
                            esn_val = spnb_text
                            esl_candidate = spnbl_text if spnbl_text else "-"
                            esl_val = ''.join(esl_candidate.split()) if ''.join(esl_candidate.split()) else "-"
                            matched = True
                            break
                    if esl_val == "-" and matched:
                        for spnb_text, _, _, _, _, spnbl_text, _, _, _ in spnb_data:
                            spnb_no_ws = ''.join(spnb_text.replace("0", "O").split())
                            if spna_no_ws in spnb_no_ws:
                                bl_force = ''.join(spnbl_text.split())
                                if bl_force:
                                    esl_val = bl_force
                                break
                    try:
                        msp.add_text(esn_val, dxfattribs={
                            "insert": (ESNP[0], ESNP[1] - dy * index),
                            "height": 2.5,
                            "layer": "ESN",
                            "color": 2,
                            "style": "STANDARD"
                        })
                    except Exception:
                        pass
                    try:
                        msp.add_text(esl_val, dxfattribs={
                            "insert": (ESLP[0], ESLP[1] - dy * index),
                            "height": 2.5,
                            "layer": "ESL",
                            "color": 2,
                            "style": "STANDARD"
                        })
                    except Exception:
                        pass
                    index += 1
            else:
                for spna_text, spna_x, spna_y in spna_list:
                    esn_val = spna_text
                    bl_text, bl_x, bl_y, bl_e = find_bl_for_spna(texts, spna_x, spna_y)
                    bl_text_clean = ''.join(bl_text.split()) if bl_text else ""
                    esl_val = bl_text_clean if bl_text_clean else "-"
                    try:
                        msp.add_text(esn_val, dxfattribs={
                            "insert": (ESNP[0], ESNP[1] - dy * index),
                            "height": 2.5,
                            "layer": "ESN",
                            "color": 2,
                            "style": "STANDARD"
                        })
                    except Exception:
                        pass
                    try:
                        msp.add_text(esl_val, dxfattribs={
                            "insert": (ESLP[0], ESLP[1] - dy * index),
                            "height": 2.5,
                            "layer": "ESL",
                            "color": 2,
                            "style": "STANDARD"
                        })
                    except Exception:
                        pass
                    index += 1

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

        out_path = _make_output_path(filepath, suffix="_SPN.dxf")
        saved = _safe_save(doc, out_path)
        if saved is None:
            # 최후 수단: 완전히 새 문서를 만들어 현재 폴더에 저장 시도
            try:
                fallback = ezdxf.new("R2018")
                _safe_save(fallback, os.path.join(os.getcwd(), "unnamed_SPN.dxf"))
            except Exception:
                pass

if __name__ == "__main__":
    final_main()
