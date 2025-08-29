#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compare_drawings.py
- TK 창에서 DXF 또는 PDF 2개 파일을 선택해 비교/표기 후 저장
- 규칙:
  * 위치만 변경: 2번째 도면 CYAN
  * 텍스트 변경: 2번째 도면 YELLOW
  * 삭제(1에만 존재): 1번째 도면 RED
  * 추가(2에만 존재): 2번째 도면 RED
- DXF: TEXT / MTEXT 비교
- PDF: 페이지별 단어(words) 비교
- 설치: pip install ezdxf PyMuPDF
"""

import os
import sys
import math
import tkinter as tk
from tkinter import filedialog, messagebox

# --- 외부 라이브러리 ---
try:
    import ezdxf
    EZDXF_AVAILABLE = True
except Exception:
    EZDXF_AVAILABLE = False

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except Exception:
    PYMUPDF_AVAILABLE = False

# ───────── 설정값 (필요 시 조정) ─────────
# DXF 위치판정 허용거리(도면 단위)
DXF_NEAR_TOL = 5.0      # 근접(같은 위치로 간주)
DXF_MOVE_TOL = 10.0     # 이 값 초과 이동이면 "위치 변경"으로 간주

# PDF 위치판정 허용거리(포인트, 1pt ≈ 0.3528mm)
PDF_NEAR_TOL = 12.0     # 근접(같은 위치로 간주)
PDF_MOVE_TOL = 24.0     # 이 값 초과 이동이면 "위치 변경"으로 간주

# DXF ACI 색상
ACI_RED = 1
ACI_YELLOW = 2
ACI_CYAN = 4

# PDF RGB (0~1)
RGB_RED = (1.0, 0.0, 0.0)
RGB_YELLOW = (1.0, 1.0, 0.0)
RGB_CYAN = (0.0, 1.0, 1.0)

# ───────── 공용 유틸 ─────────
def norm_text(s: str) -> str:
    if s is None:
        return ""
    # 공백 정규화 + 대문자 비교(현장 텍스트가 대문자 위주라는 가정)
    return " ".join(str(s).split()).upper()

def dist(p1, p2) -> float:
    return math.hypot(p2[0] - p1[0], p2[1] - p1[1])

def before_after_paths(path1: str, path2: str) -> tuple[str, str]:
    d1, b1 = os.path.dirname(path1), os.path.splitext(os.path.basename(path1))[0]
    d2, b2 = os.path.dirname(path2), os.path.splitext(os.path.basename(path2))[0]
    ext1 = os.path.splitext(path1)[1].lower()
    ext2 = os.path.splitext(path2)[1].lower()
    # 동일 타입 가정(아래에서 체크)
    out1 = os.path.join(d1, f"{b1}_BEFORE{ext1}")
    out2 = os.path.join(d2, f"{b2}_AFTER{ext2}")
    return out1, out2

def ask_two_files() -> tuple[str, str] | None:
    root = tk.Tk()
    root.withdraw()
    paths = filedialog.askopenfilenames(
        title="비교할 2개의 DXF 또는 PDF 파일을 선택하세요",
        filetypes=[("DXF / PDF", "*.dxf *.pdf")]
    )
    if not paths or len(paths) != 2:
        messagebox.showerror("선택 오류", "정확히 2개의 파일을 선택해야 합니다.")
        return None
    p1, p2 = paths[0], paths[1]
    e1, e2 = os.path.splitext(p1)[1].lower(), os.path.splitext(p2)[1].lower()
    if e1 != e2:
        messagebox.showerror("형식 불일치", "두 파일 형식이 다릅니다. (둘 다 DXF 또는 둘 다 PDF)")
        return None
    if e1 not in (".dxf", ".pdf"):
        messagebox.showerror("형식 오류", "DXF 또는 PDF만 지원합니다.")
        return None
    return p1, p2

# ───────── DXF 비교 ─────────
class DXFItem:
    def __init__(self, text: str, xy: tuple[float, float], ent):
        self.text = norm_text(text)
        self.xy = xy
        self.ent = ent
        self.used = False

def _iter_all_text_entities(doc: "ezdxf.document.Drawing"):
    # 모든 레이아웃(Model/Paper)을 대상으로 TEXT/MTEXT 순회
    for layout in doc.layouts:
        # TEXT
        for e in layout.query("TEXT"):
            try:
                x, y = float(e.dxf.insert.x), float(e.dxf.insert.y)
                yield ("TEXT", e.dxf.text, (x, y), e)
            except Exception:
                continue
        # MTEXT
        for e in layout.query("MTEXT"):
            try:
                x, y = float(e.dxf.insert.x), float(e.dxf.insert.y)
                # plain_text()가 가장 안전
                t = e.plain_text() if hasattr(e, "plain_text") else e.text
                yield ("MTEXT", t, (x, y), e)
            except Exception:
                continue

def _extract_dxf_items(doc) -> list[DXFItem]:
    items = []
    for _, t, (x, y), e in _iter_all_text_entities(doc):
        nt = norm_text(t)
        if nt:
            items.append(DXFItem(nt, (x, y), e))
    return items

def _nearest(indices, items2, pt):
    """indices 중 pt에 가장 가까운 2의 인덱스 반환"""
    best = None
    best_d = 1e30
    for j in indices:
        if items2[j].used:
            continue
        d = dist(items2[j].xy, pt)
        if d < best_d:
            best_d = d
            best = j
    return best, best_d

def compare_dxf(path1: str, path2: str):
    if not EZDXF_AVAILABLE:
        raise RuntimeError("ezdxf가 설치되어 있지 않습니다. pip install ezdxf")
    doc1 = ezdxf.readfile(path1)
    doc2 = ezdxf.readfile(path2)

    items1 = _extract_dxf_items(doc1)
    items2 = _extract_dxf_items(doc2)

    # 텍스트별 인덱스 맵(문구 동일 빠른 탐색)
    map2_by_text = {}
    for idx, it in enumerate(items2):
        map2_by_text.setdefault(it.text, []).append(idx)

    # 1) 동일문구 매칭 → 거리 판정 (이동 여부)
    for i, a in enumerate(items1):
        # 동일 문구 후보
        candidates = map2_by_text.get(a.text, [])
        if candidates:
            j, d = _nearest(candidates, items2, a.xy)
            if j is not None:
                items2[j].used = True
                # 이동 판정
                if d > DXF_MOVE_TOL:
                    try:
                        items2[j].ent.dxf.color = ACI_CYAN  # 위치 변경 → 둘째 CYAN
                    except Exception:
                        pass
                # 근접하면 unchanged → 색 변경 없음
                continue
        # 동일 문구가 없으면 다음 단계에서 처리

    # 2) 텍스트 변경 (위치는 근접, 문구 다름)
    #    - 1의 매칭에서 소모되지 않은 2의 아이템 중 위치가 근접하고 문구가 다른 경우
    for a in items1:
        if any((j for j, it in enumerate(items2) if it.used and it.text == a.text)):
            continue  # 이미 동일문구 매칭 완료된 a는 스킵

        # 근접(NEAR_TOL) 내에서 다른 텍스트 찾기
        near_candidates = []
        for j, b in enumerate(items2):
            if b.used:
                continue
            if dist(a.xy, b.xy) <= DXF_NEAR_TOL and b.text != a.text:
                near_candidates.append(j)
        if near_candidates:
            j, _ = _nearest(near_candidates, items2, a.xy)
            if j is not None:
                items2[j].used = True
                try:
                    items2[j].ent.dxf.color = ACI_YELLOW  # 텍스트 변경 → 둘째 YELLOW
                except Exception:
                    pass
            continue

    # 3) 삭제(1에만 존재) → 1 RED
    matched2 = {j for j, it in enumerate(items2) if it.used}
    # a가 동일문구/근접문구로 매칭되지 않았다면 삭제로 간주
    for a in items1:
        # 동일문구 중 하나라도 매칭 되었는지 확인
        same_in_2 = map2_by_text.get(a.text, [])
        same_used = any((j in matched2) for j in same_in_2)
        # 근접-다른문구 매칭이 있었는지 대략 판정(근사)
        # 근접 영역 내에서 used 된게 있으면 바뀐 것으로 취급(이미 위에서 노랗게 처리)
        was_changed = False
        for j, b in enumerate(items2):
            if j in matched2 and dist(a.xy, b.xy) <= DXF_NEAR_TOL:
                was_changed = True
                break
        if not same_used and not was_changed:
            try:
                a.ent.dxf.color = ACI_RED  # 삭제 → 첫째 RED
            except Exception:
                pass

    # 4) 추가(2에만 존재) → 2 RED
    for j, b in enumerate(items2):
        if not b.used:
            try:
                b.ent.dxf.color = ACI_RED
            except Exception:
                pass

    out1, out2 = before_after_paths(path1, path2)
    doc1.saveas(out1)
    doc2.saveas(out2)
    return out1, out2

# ───────── PDF 비교 ─────────
class PDFItem:
    def __init__(self, text: str, rect: "fitz.Rect"):
        self.text = norm_text(text)
        self.rect = rect
        self.xy = ((rect.x0 + rect.x1) * 0.5, (rect.y0 + rect.y1) * 0.5)
        self.used = False

def _pdf_make_highlight(page, rect: "fitz.Rect", rgb=(1,1,0), opacity=0.35):
    try:
        annot = page.add_highlight_annot(rect)
        annot.set_colors(stroke=rgb)   # highlight는 stroke 컬러 사용
        annot.set_opacity(opacity)
        annot.update()
    except Exception:
        # fallback: 사각형 주석
        annot = page.add_rect_annot(rect)
        annot.set_colors(stroke=rgb, fill=rgb)
        annot.set_opacity(opacity * 0.6)
        annot.update()

def _extract_pdf_items(page) -> list[PDFItem]:
    items = []
    try:
        # words: (x0, y0, x1, y1, "word", block_no, line_no, word_no)
        for x0, y0, x1, y1, w, *_ in page.get_text("words"):
            nt = norm_text(w)
            if not nt:
                continue
            rect = fitz.Rect(x0, y0, x1, y1)
            items.append(PDFItem(nt, rect))
    except Exception:
        pass
    return items

def _nearest_pdf(indices, items2, pt):
    best = None
    best_d = 1e30
    for j in indices:
        if items2[j].used:
            continue
        d = dist(items2[j].xy, pt)
        if d < best_d:
            best_d = d
            best = j
    return best, best_d

def compare_pdf(path1: str, path2: str):
    if not PYMUPDF_AVAILABLE:
        raise RuntimeError("PyMuPDF가 설치되어 있지 않습니다. pip install PyMuPDF")
    doc1 = fitz.open(path1)
    doc2 = fitz.open(path2)

    n1, n2 = doc1.page_count, doc2.page_count
    n = max(n1, n2)

    for pno in range(n):
        p1 = doc1.load_page(pno) if pno < n1 else None
        p2 = doc2.load_page(pno) if pno < n2 else None

        if p1 and p2:
            items1 = _extract_pdf_items(p1)
            items2 = _extract_pdf_items(p2)

            # 문구별 index 맵
            map2_by_text = {}
            for idx, it in enumerate(items2):
                map2_by_text.setdefault(it.text, []).append(idx)

            # 1) 동일문구 → 이동 판정
            for a in items1:
                candidates = map2_by_text.get(a.text, [])
                if candidates:
                    j, d = _nearest_pdf(candidates, items2, a.xy)
                    if j is not None:
                        items2[j].used = True
                        if d > PDF_MOVE_TOL:
                            _pdf_make_highlight(p2, items2[j].rect, rgb=RGB_CYAN, opacity=0.35)  # 위치 변경
                        continue

            # 2) 텍스트 변경(근접)
            for a in items1:
                # 이미 동일문구 매칭 완료한 a는 스킵(근사적으로 판단)
                matched_same = False
                for j, b in enumerate(items2):
                    if b.used and b.text == a.text:
                        matched_same = True
                        break
                if matched_same:
                    continue

                near_candidates = []
                for j, b in enumerate(items2):
                    if b.used:
                        continue
                    if dist(a.xy, b.xy) <= PDF_NEAR_TOL and b.text != a.text:
                        near_candidates.append(j)
                if near_candidates:
                    j, _ = _nearest_pdf(near_candidates, items2, a.xy)
                    if j is not None:
                        items2[j].used = True
                        _pdf_make_highlight(p2, items2[j].rect, rgb=RGB_YELLOW, opacity=0.35)  # 텍스트 변경
                    continue

            # 3) 삭제(1에만 존재) → 1 RED
            # 동일문구/근접문구로도 못찾은 1의 단어는 삭제로 간주
            matched2 = {j for j, it in enumerate(items2) if it.used}
            for a in items1:
                # 동일문구가 매칭되었는지
                same_in_2 = map2_by_text.get(a.text, [])
                same_used = any((j in matched2) for j in same_in_2)
                # 근접-다른문구 매칭이 있었는지(근사)
                was_changed = False
                for j, b in enumerate(items2):
                    if j in matched2 and dist(a.xy, b.xy) <= PDF_NEAR_TOL:
                        was_changed = True
                        break
                if not same_used and not was_changed:
                    _pdf_make_highlight(p1, a.rect, rgb=RGB_RED, opacity=0.35)  # 삭제

            # 4) 추가(2에만 존재) → 2 RED
            for j, b in enumerate(items2):
                if not b.used:
                    _pdf_make_highlight(p2, b.rect, rgb=RGB_RED, opacity=0.35)  # 추가

        elif p1 and not p2:
            # 둘째 문서에 해당 페이지 없음 → 1쪽 전부 삭제로 표시(빨강)
            items1 = _extract_pdf_items(p1)
            for a in items1:
                _pdf_make_highlight(p1, a.rect, rgb=RGB_RED, opacity=0.35)
        elif p2 and not p1:
            # 첫째 문서에 해당 페이지 없음 → 2쪽 전부 추가로 표시(빨강)
            items2 = _extract_pdf_items(p2)
            for b in items2:
                _pdf_make_highlight(p2, b.rect, rgb=RGB_RED, opacity=0.35)

    out1, out2 = before_after_paths(path1, path2)
    # 주석 포함 저장
    doc1.save(out1, deflate=True)
    doc2.save(out2, deflate=True)
    doc1.close()
    doc2.close()
    return out1, out2

# ───────── 엔트리 ─────────
def main():
    sel = ask_two_files()
    if not sel:
        return
    p1, p2 = sel
    ext = os.path.splitext(p1)[1].lower()
    try:
        if ext == ".dxf":
            out1, out2 = compare_dxf(p1, p2)
        else:
            out1, out2 = compare_pdf(p1, p2)
    except Exception as e:
        messagebox.showerror("오류", f"처리 중 오류가 발생했습니다.\n{e}")
        return

    messagebox.showinfo("완료", f"저장 완료:\n{out1}\n{out2}")

if __name__ == "__main__":
    main()
