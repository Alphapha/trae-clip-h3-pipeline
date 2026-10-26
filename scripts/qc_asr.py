#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对白质检：用本地 ASR（faster-whisper，CPU）把每个分镜的原生音轨转写成文字，
和提示词里写的台词对照，判断 H3 原生音频是否真的把话说对了。

这一步是「声音一致性」的关键验收：H3 的对白是原生生成的，不是外挂配音，
所以必须逐镜核对，否则会出现「有声音但不是台词」的哑片。

依赖（与主流程解耦，单独装在 .venv-asr 里）：
  python3 -m venv .venv-asr
  .venv-asr/bin/pip install faster-whisper
  HF_ENDPOINT=https://hf-mirror.com .venv-asr/bin/python scripts/qc_asr.py

用法：
  .venv-asr/bin/python scripts/qc_asr.py                 # 全量
  .venv-asr/bin/python scripts/qc_asr.py --only S01 S02  # 指定镜头
"""

import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
SHOT_DIR = PROJECT_DIR / "video" / "shots"
MANIFEST = PROJECT_DIR / "prompts" / "manifest.json"


def normalize(text: str) -> str:
    """去掉标点与空白，只留汉字与字母数字，便于宽松比对。"""
    return re.sub(r"[^一-鿿a-zA-Z0-9]", "", text or "")


def similarity(a: str, b: str) -> float:
    """用字符集合的 Jaccard 相似度做宽松比对（tiny 模型会有同音字误差）。"""
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def main() -> int:
    """逐镜转写并与期望台词比对，输出报告。"""
    ap = argparse.ArgumentParser(description="对白 ASR 质检")
    ap.add_argument("--only", nargs="*", default=None, help="只查指定镜头 id")
    ap.add_argument("--model", default="tiny", help="faster-whisper 模型（tiny/base/small）")
    ap.add_argument("--out", default="video/_qc/asr_report.json", help="报告输出路径")
    args = ap.parse_args()

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("未安装 faster-whisper，见文件头部的安装说明")
        return 1

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    rows, bad = [], []
    for m in manifest:
        if args.only and m["id"] not in args.only:
            continue
        path = SHOT_DIR / f"{m['id']}.mp4"
        if not path.exists():
            continue
        segs, _ = model.transcribe(str(path), language="zh", vad_filter=False)
        heard = "".join(s.text for s in segs)
        expect = "".join(d["line"] for d in m["dialogue"])
        score = similarity(normalize(heard), normalize(expect))
        rows.append({"id": m["id"], "heard": heard, "expect": expect, "score": round(score, 3)})
        flag = "OK " if score >= 0.5 else ("近似" if score >= 0.3 else "差异")
        print(f"{flag} {m['id']}  相似度 {score:.2f}  听到：{heard.strip()[:40]}  期望：{expect[:30]}")
        if score < 0.3 and expect:
            bad.append(m["id"])
    out = PROJECT_DIR / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    avg = sum(r["score"] for r in rows) / max(len(rows), 1)
    print(f"\n共 {len(rows)} 镜，平均相似度 {avg:.2f}；差异较大：{'、'.join(bad) if bad else '无'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
