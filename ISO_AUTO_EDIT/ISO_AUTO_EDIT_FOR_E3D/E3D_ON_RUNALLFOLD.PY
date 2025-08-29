#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
SAE3D_ON_RUNTEST.PY
- *_ON_00 ~ *_ON_14 스텝 스크립트를 번호순 실행 (총 15개)
- 커맨드: python SAE3D_ON_RUNTEST.PY A.DXF B.DXF
- 중간 저장 금지(논리 처리만), 마지막에만 저장
- 스텝 호환:
  1) 함수형: process(doc)/pipeline(doc)/run(doc)/main_process(doc)
  2) 스크립트형: process_file(path)/process_single_dxf(path)/main()/run()/execute()
- 스크립트형도 현재 in-memory 문서를 쓰도록 ezdxf.readfile을 패치
"""

import argparse
import importlib.util
import os
import re
import sys
import traceback
from contextlib import contextmanager
from typing import Callable, Optional, List, Tuple

try:
    import ezdxf
    from ezdxf.document import Drawing
except ImportError:
    print("[ERROR] ezdxf 라이브러리가 필요합니다. 설치: pip install ezdxf")
    sys.exit(1)

from importlib.machinery import SourceFileLoader

# *_ON_00, *_ON_01, ..., *_ON_14* 형태를 포착
STEP_PATTERN = re.compile(r"_ON_(\d{2})", re.IGNORECASE)
MAX_STEP_INDEX = 14  # ← 11에서 14로 상향 (00~14 총 15개)

FUNC_DOC_CANDIDATES = [
    "process", "pipeline", "run", "main_process",  # doc 인자 1개
]
FUNC_PATH_CANDIDATES = [
    "process_file", "process_single_dxf",          # path 인자 1개
]
FUNC_ZERO_ARG_CANDIDATES = [
    "main", "run", "execute",                      # 인자 없음
]


# ──────────────────────────────────────────────────────────────────────
# 스텝 검색/정렬
# ──────────────────────────────────────────────────────────────────────
def find_step_scripts(folder: str) -> List[str]:
    found: List[Tuple[int, str]] = []
    for fn in os.listdir(folder):
        if not fn.lower().endswith(".py"):
            continue
        m = STEP_PATTERN.search(fn)
        if not m:
            continue
        idx = int(m.group(1))
        if 0 <= idx <= MAX_STEP_INDEX:
            found.append((idx, os.path.abspath(os.path.join(folder, fn))))
    found.sort(key=lambda x: x[0])
    return [p for _, p in found]


# ──────────────────────────────────────────────────────────────────────
# 모듈 로딩
# ──────────────────────────────────────────────────────────────────────
def load_module_from_path(path: str):
    mod_name = f"_sae3d_step_{os.path.basename(path).replace('.', '_')}"
    loader = SourceFileLoader(mod_name, path)
    spec = importlib.util.spec_from_loader(mod_name, loader)
    if spec is None:
        raise ImportError(f"spec_from_loader() 실패: {path}")
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)  # type: ignore
    return mod


# ──────────────────────────────────────────────────────────────────────
# 중간 저장 차단 & readfile 주입
# ──────────────────────────────────────────────────────────────────────
@contextmanager
def suppress_dxf_save_and_inject_readfile(current_doc: Drawing):
    """
    - Drawing.save / saveas → NO-OP
    - ezdxf.readfile(path) → 현재 in-memory 문서를 반환
    """
    original_save = getattr(Drawing, "save", None)
    original_saveas = getattr(Drawing, "saveas", None)
    original_readfile = getattr(ezdxf, "readfile", None)

    def _noop_save(self, *args, **kwargs):
        return None

    def _inject_readfile(*args, **kwargs) -> Drawing:
        # 어떤 경로가 오더라도 현재 문서를 그대로 넘겨줌
        return current_doc

    try:
        if original_save is not None:
            Drawing.save = _noop_save  # type: ignore
        if original_saveas is not None:
            Drawing.saveas = _noop_save  # type: ignore
        if original_readfile is not None:
            ezdxf.readfile = _inject_readfile  # type: ignore
        yield
    finally:
        if original_save is not None:
            Drawing.save = original_save  # type: ignore
        if original_saveas is not None:
            Drawing.saveas = original_saveas  # type: ignore
        if original_readfile is not None:
            ezdxf.readfile = original_readfile  # type: ignore


# ──────────────────────────────────────────────────────────────────────
# 스텝 실행(함수형 & 스크립트형)
# ──────────────────────────────────────────────────────────────────────
def try_call_func_with_doc(mod, fname: str, doc: Drawing):
    func = getattr(mod, fname, None)
    if callable(func):
        return func(doc)
    return None

def try_call_func_with_path(mod, fname: str, input_path: str):
    func = getattr(mod, fname, None)
    if callable(func):
        return func(input_path)
    return None

def try_call_zero_arg(mod, fname: str, argv0: str, input_path: str):
    func = getattr(mod, fname, None)
    if callable(func):
        # CLI 스크립트 호환: argv 세팅
        old_argv = sys.argv[:]
        try:
            # 일반적으로 한 개 파일만 요구하는 스크립트 호환
            sys.argv = [argv0, input_path]
            return func()
        finally:
            sys.argv = old_argv
    return None

def run_single_step(mod, current_doc: Drawing, input_path: str) -> Optional[Drawing]:
    """
    - 우선 doc 인자 1개 함수 시도
    - 실패 시 path 인자 1개 함수 시도
    - 실패 시 zero-arg(main/run/execute) 시도 (argv에 input_path 주입)
    - 반환이 Drawing이면 교체, None이면 in-place로 수정된 것으로 보고 current_doc 유지
    """
    # 1) doc 인자
    for name in FUNC_DOC_CANDIDATES:
        if callable(getattr(mod, name, None)):
            res = try_call_func_with_doc(mod, name, current_doc)
            if isinstance(res, Drawing):
                return res
            return current_doc  # None 또는 다른 타입 → in-place 가정

    # 2) path 인자
    for name in FUNC_PATH_CANDIDATES:
        if callable(getattr(mod, name, None)):
            res = try_call_func_with_path(mod, name, input_path)
            if isinstance(res, Drawing):
                return res
            return current_doc

    # 3) zero-arg 엔트리
    for name in FUNC_ZERO_ARG_CANDIDATES:
        if callable(getattr(mod, name, None)):
            res = try_call_zero_arg(mod, name, mod.__name__, input_path)
            if isinstance(res, Drawing):
                return res
            return current_doc

    # 어떤 것도 못 찾음
    return None


def run_pipeline_on_doc(doc: Drawing, step_paths: List[str], input_path: str) -> Drawing:
    current = doc
    for spath in step_paths:
        basename = os.path.basename(spath)
        print(f"[RUN] Step: {basename}")

        try:
            mod = load_module_from_path(spath)
        except SyntaxError as se:
            print(f"  └─ 구문 오류: {basename} (line {se.lineno}): {se.msg}")
            continue
        except Exception as e:
            print(f"  └─ 오류: {basename} 로드 실패. 직전 상태 유지.")
            print(f"     ↳ {e}")
            continue

        # 중간 저장 차단 + readfile 주입
        try:
            with suppress_dxf_save_and_inject_readfile(current):
                result = run_single_step(mod, current, input_path)
        except Exception:
            print(f"  └─ 오류: {basename} 실행 중 예외. 직전 상태 유지.")
            traceback.print_exc(limit=1)
            continue

        if result is None:
            print("  └─ 경고: 스텝 엔트리 함수를 찾지 못해 스킵.")
            continue

        if isinstance(result, Drawing):
            current = result
            print("  └─ OK: 문서 갱신.")
        else:
            # None 또는 타 타입 → in-place 로 보고 current 유지
            print("  └─ 정보: 반환 없음(또는 비문서) → in-place 수정으로 간주.")
    return current


# ──────────────────────────────────────────────────────────────────────
# I/O
# ──────────────────────────────────────────────────────────────────────
def resolve_input_paths(args_files: List[str]) -> List[str]:
    paths = []
    if args_files:
        for p in args_files:
            if os.path.isfile(p) and p.lower().endswith(".dxf"):
                paths.append(os.path.abspath(p))
    else:
        cwd = os.getcwd()
        for name in ["A.DXF", "B.DXF"]:
            p = os.path.join(cwd, name)
            if os.path.isfile(p):
                paths.append(os.path.abspath(p))
    return paths

def output_name_for(input_path: str) -> str:
    stem, _ = os.path.splitext(os.path.basename(input_path))
    return f"{stem}_ON_FINAL.dxf"


# ──────────────────────────────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="*_ON_00 ~ *_ON_14 파이프라인을 A.DXF/B.DXF에 적용(중간 저장 금지, 마지막만 저장)"
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="처리할 DXF 파일들 (예: A.DXF B.DXF). 생략 시 현재 폴더의 A.DXF, B.DXF 자동 탐색."
    )
    args = parser.parse_args()

    step_paths = find_step_scripts(os.getcwd())
    if not step_paths:
        print("[경고] *_ON_00 ~ *_ON_14 패턴의 스텝 스크립트를 찾지 못했습니다. 입력을 그대로 저장합니다.")

    inputs = resolve_input_paths(args.files)
    if not inputs:
        print("[ERROR] 입력 DXF(A.DXF/B.DXF)를 찾지 못했습니다. 인자로 지정하거나 현재 폴더에 배치하세요.")
        sys.exit(2)

    for in_path in inputs:
        print(f"\n[INPUT] {in_path}")
        try:
            doc = ezdxf.readfile(in_path)
        except Exception as e:
            print(f"[ERROR] DXF 읽기 실패: {in_path} :: {e}")
            continue

        final_doc = run_pipeline_on_doc(doc, step_paths, in_path) if step_paths else doc

        out_path = os.path.abspath(os.path.join(os.getcwd(), output_name_for(in_path)))
        try:
            final_doc.saveas(out_path)
            print(f"[SAVE] 최종 결과 저장 완료: {out_path}")
        except Exception as e:
            print(f"[ERROR] 최종 저장 실패: {out_path} :: {e}")

if __name__ == "__main__":
    main()
