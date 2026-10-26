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
    """归一化文本：繁转简、阿拉伯数字转中文数字、去标点空白，只留可读字符。

    ASR 常把「两米二」写成「2.2.2」、把「飞」写成「飛」，不归一化会误判成没对上。
    """
    text = text or ""
    try:
        from opencc import OpenCC
        text = OpenCC("t2s").convert(text)
    except ImportError:
        pass
    text = re.sub(r"(\d+)", lambda m: DIGITS.get(m.group(1), m.group(1)), text)
    return re.sub(r"[^一-鿿a-zA-Z0-9]", "", text)


# 阿拉伯数字 → 中文数字（只覆盖 0–99，足够「两米二」这类量词表达）
DIGITS = {
    "0": "零", "1": "一", "2": "二", "3": "三", "4": "四", "5": "五",
    "6": "六", "7": "七", "8": "八", "9": "九", "10": "十", "11": "十一",
    "12": "十二", "13": "十三", "14": "十四", "15": "十五", "16": "十六",
    "17": "十七", "18": "十八", "19": "十九", "20": "二十", "22": "二十二",
}


def similarity(a: str, b: str) -> float:
    """字符集合的 Jaccard 与包含度取较大值，容忍同音字与繁简差异。"""
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    inter = len(sa & sb)
    jac = inter / len(sa | sb)
    contain = inter / min(len(sa), len(sb))
    return max(jac, contain)


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
        if not expect:                      # 本镜无台词（如空镜/片尾），只记录环境音转写
            rows.append({"id": m["id"], "heard": heard, "expect": "", "score": None})
            print(f"无台词 {m['id']}  环境音转写：{heard.strip()[:40]}")
            continue
        score = similarity(normalize(heard), normalize(expect))
        rows.append({"id": m["id"], "heard": heard, "expect": expect, "score": round(score, 3)})
        flag = "OK " if score >= 0.5 else ("近似" if score >= 0.3 else "差异")
        print(f"{flag} {m['id']}  相似度 {score:.2f}  听到：{heard.strip()[:40]}  期望：{expect[:30]}")
        if score < 0.3:
            bad.append(m["id"])
    out = PROJECT_DIR / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    scored = [r["score"] for r in rows if r["score"] is not None]
    avg = sum(scored) / max(len(scored), 1)
    print(f"\n共 {len(rows)} 镜（{len(scored)} 镜有台词），平均相似度 {avg:.2f}；差异较大：{'、'.join(bad) if bad else '无'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
