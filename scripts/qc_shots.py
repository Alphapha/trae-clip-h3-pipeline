#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分镜质检：逐镜检查时长/分辨率/音轨，并抽取首中尾三帧拼成 QC 联络表。

用途：
  1) 快速发现某一镜没有音轨、黑帧、时长异常、画幅不对；
  2) 人工肉眼核对人物一致性（是否还是那两个人、身高差是否明显）。

用法：
  python3 scripts/qc_shots.py                 # 全量检查并生成 QC 拼图
  python3 scripts/qc_shots.py --only S01 S02  # 只查指定镜头
"""

import argparse
import json
import subprocess
import sys
from typing import Optional
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
SHOT_DIR = PROJECT_DIR / "video" / "shots"
QC_DIR = PROJECT_DIR / "video" / "_qc"
MANIFEST = PROJECT_DIR / "prompts" / "manifest.json"
FFMPEG = "/usr/local/bin/ffmpeg"
FFPROBE = "/usr/local/bin/ffprobe"


def probe(path: Path) -> dict:
    """用 ffprobe 读取时长/分辨率/音轨信息。"""
    r = subprocess.run([FFPROBE, "-v", "error", "-print_format", "json",
                        "-show_format", "-show_streams", str(path)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return {"error": r.stderr[:300]}
    data = json.loads(r.stdout)
    v = next((s for s in data["streams"] if s.get("codec_type") == "video"), None)
    a = next((s for s in data["streams"] if s.get("codec_type") == "audio"), None)
    return {
        "duration": float(data["format"].get("duration", 0)),
        "width": v.get("width") if v else 0,
        "height": v.get("height") if v else 0,
        "fps": v.get("r_frame_rate") if v else "",
        "has_audio": a is not None,
        "audio_codec": a.get("codec_name") if a else "",
    }


def grab_frames(path: Path, out_prefix: Path, times: list) -> list:
    """在指定时间点抽帧，返回生成的文件列表。"""
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    files = []
    for i, t in enumerate(times, start=1):
        dest = out_prefix.with_name(f"{out_prefix.stem}_{i}.jpg")
        r = subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", f"{t:.2f}",
                            "-i", str(path), "-frames:v", "1", "-q:v", "3", str(dest)],
                           capture_output=True, text=True)
        if r.returncode == 0 and dest.exists():
            files.append(dest)
    return files


def make_contact_sheet(shot_ids: list) -> Optional[Path]:
    """把所有分镜的中间帧拼成一张总览图，方便一眼检查人物一致性。"""
    from PIL import Image

    cols, cw, ch = 6, 180, 320
    tiles = []
    for sid in shot_ids:
        frames = sorted(QC_DIR.glob(f"{sid}_*.jpg"))
        if len(frames) < 2:
            continue
        try:
            im = Image.open(frames[1]).convert("RGB").resize((cw, ch))
        except Exception:  # noqa: BLE001 - 单帧损坏不影响拼图
            continue
        tiles.append(im)
    if not tiles:
        return None
    rows = (len(tiles) + cols - 1) // cols
    sheet = QC_DIR / "总览拼图.jpg"
    canvas = Image.new("RGB", (cols * cw, rows * ch), (20, 20, 20))
    for i, im in enumerate(tiles):
        canvas.paste(im, ((i % cols) * cw, (i // cols) * ch))
    canvas.save(sheet, quality=88)
    return sheet


def main() -> int:
    """检查所有分镜并输出质检报告与拼图。"""
    ap = argparse.ArgumentParser(description="分镜质检")
    ap.add_argument("--only", nargs="*", default=None, help="只查指定镜头 id")
    ap.add_argument("--contact-sheet", action="store_true", help="生成首帧拼图")
    args = ap.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    QC_DIR.mkdir(parents=True, exist_ok=True)
    report, problems = [], []
    for m in manifest:
        path = SHOT_DIR / f"{m['id']}.mp4"
        if args.only and m["id"] not in args.only:
            continue
        if not path.exists():
            problems.append(f"{m['id']}: 缺失")
            report.append((m["id"], None))
            continue
        info = probe(path)
        info["id"] = m["id"]
        info["expect_sec"] = m["seconds"]
        report.append((m["id"], info))
        if info.get("error"):
            problems.append(f"{m['id']}: 解析失败 {info['error'][:80]}")
            continue
        if not info["has_audio"]:
            problems.append(f"{m['id']}: 无音轨")
        if abs(info["duration"] - m["seconds"]) > 1.0:
            problems.append(f"{m['id']}: 时长 {info['duration']:.2f}s ≠ 预期 {m['seconds']}s")
        ratio = (info["width"] / info["height"]) if info["height"] else 0
        if not (0.5 <= ratio <= 0.65):      # 只校验是不是竖屏近 9:16，不锁死分辨率
            problems.append(f"{m['id']}: 画幅异常 {info['width']}x{info['height']}")
        grab_frames(path, QC_DIR / f"{m['id']}", [0.2, m["seconds"] / 2, m["seconds"] - 0.3])
    print(f"{'镜头':<6}{'时长':>7}{'画幅':>12}{'音轨':>6}  预期")
    for sid, info in report:
        if not info:
            print(f"{sid:<6}{'缺失':>7}")
            continue
        if info.get("error"):
            print(f"{sid:<6}  解析失败")
            continue
        size = f"{info['width']}x{info['height']}"
        audio = "有" if info["has_audio"] else "无"
        print(f"{sid:<6}{info['duration']:>7.2f}{size:>12}{audio:>6}  预期 {info['expect_sec']}s")
    (QC_DIR / "report.json").write_text(
        json.dumps([{k: v for k, v in i.items()} for _, i in report if i],
                   ensure_ascii=False, indent=2), encoding="utf-8")
    if args.contact_sheet:
        sheet = make_contact_sheet([sid for sid, i in report if i])
        if sheet:
            print(f"总览拼图 -> {sheet}")
    if problems:
        print("\n问题：")
        for p in problems:
            print("  -", p)
    else:
        print("\n全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
