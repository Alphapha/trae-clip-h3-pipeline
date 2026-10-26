#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
成片合成：把 video/shots/ 里的分镜按顺序拼成一支 9:16 竖屏长片。

两步走：
  1. 逐镜预转码：缩放裁切到 1080x1920（严格 9:16）、24fps、yuv420p、立体声 48k，
     统一参数后才能安全拼接（concat 解复用器要求各分镜流参数一致）；
  2. 拼接 + 叠加连续房间底噪（-42dB 粉红噪，让切点之间的房间声不断）+ 结尾淡出
     + 总时长对齐到目标（默认 600 秒）。

用法：
  python3 scripts/build_final.py --out video/身高差_10分钟成片.mp4
  python3 scripts/build_final.py --target 600 --no-ambience
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
SHOT_DIR = PROJECT_DIR / "video" / "shots"
MANIFEST = PROJECT_DIR / "prompts" / "manifest.json"
FFMPEG = "/usr/local/bin/ffmpeg"
FFPROBE = "/usr/local/bin/ffprobe"

OUT_W, OUT_H, FPS = 1080, 1920, 24


def probe_duration(path: Path) -> float:
    """用 ffprobe 读取单个文件的时长（秒）。"""
    r = subprocess.run([FFPROBE, "-v", "error", "-show_entries",
                        "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def probe_size(path: Path) -> tuple:
    """读取视频的宽高。"""
    r = subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", str(path)],
                       capture_output=True, text=True)
    try:
        w, h = r.stdout.strip().split("x")
        return int(w), int(h)
    except ValueError:
        return 0, 0


def transcode(src: Path, dst: Path, crf: int, width: int, height: int) -> None:
    """把单镜统一转成指定画幅 / 24fps / yuv420p / 立体声 48k。"""
    vf = (f"scale={width}:{height}:force_original_aspect_ratio=increase,"
          f"crop={width}:{height},fps={FPS},format=yuv420p")
    af = "aresample=48000,aformat=channel_layouts=stereo,volume=1.0"
    cmd = [FFMPEG, "-y", "-v", "error", "-i", str(src), "-vf", vf, "-af", af,
           "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
           "-c:a", "aac", "-b:a", "192k", str(dst)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"转码失败 {src.name}: {r.stderr[-500:]}")


def main() -> int:
    """主流程：统一画幅 → 拼接 → 混底噪 → 对齐时长 → 淡出。"""
    ap = argparse.ArgumentParser(description="合成分镜成片")
    ap.add_argument("--out", default="video/身高差_10分钟成片.mp4", help="成片路径")
    ap.add_argument("--target", type=float, default=600.0, help="目标时长（秒）")
    ap.add_argument("--no-ambience", action="store_true", help="不叠加连续房间底噪")
    ap.add_argument("--crf", type=int, default=18, help="H.264 CRF（越小越清晰）")
    args = ap.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    shots = [SHOT_DIR / f"{m['id']}.mp4" for m in manifest]
    shots = [s for s in shots if s.exists()]
    if not shots:
        print("没有可用分镜，先跑 gen_shots.py")
        return 1
    out_path = PROJECT_DIR / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(tempfile.mkdtemp(prefix="final_"))

    # ---- 第一步：统一画幅（只转码分辨率不一致的分镜，其余直接复制）----
    sizes = {}
    for s in shots:
        sizes[s] = probe_size(s)
    common = max(set(sizes.values()), key=lambda sz: sum(1 for v in sizes.values() if v == sz))
    cw, ch = common
    norm = []
    for i, s in enumerate(shots, start=1):
        if sizes[s] == common:
            norm.append(s)
            continue
        d = tmp_dir / f"{i:03d}_{s.stem}.mp4"
        transcode(s, d, args.crf, cw, ch)
        norm.append(d)
        print(f"  转码 {s.name} {sizes[s]} -> {common}", flush=True)
    raw_total = sum(probe_duration(d) for d in norm)
    print(f"分镜 {len(norm)} 个，统一画幅 {common}，原始总时长 {raw_total:.1f}s，"
          f"目标 {args.target:.1f}s")

    # ---- 第二步：拼接（参数已统一，可直接流拷贝）----
    list_path = tmp_dir / "concat.txt"
    list_path.write_text("".join(f"file '{d.as_posix()}'\n" for d in norm), encoding="utf-8")
    joined = tmp_dir / "joined.mp4"
    cmd = [FFMPEG, "-y", "-v", "error", "-f", "concat", "-safe", "0",
           "-i", str(list_path), "-c", "copy", str(joined)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("拼接失败:", r.stderr[-1000:])
        return 1

    # ---- 第三步：升到成片画幅 + 叠底噪 + 对齐时长 + 结尾淡出 ----
    cmd2 = [FFMPEG, "-y", "-v", "error", "-i", str(joined)]
    if not args.no_ambience:
        cmd2 += ["-f", "lavfi", "-i",
                 f"anoisesrc=color=pink:amplitude=0.004:sample_rate=48000:duration={args.target}"]
    fade_start = max(args.target - 2.0, 0.5)
    filters = (f"[0:v]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,"
               f"crop={OUT_W}:{OUT_H},fps={FPS},format=yuv420p,fade=t=out:st={fade_start}:d=2[v];")
    # 音频：叠底噪 → 响度标准化（短剧常见响度 -16 LUFS）→ 结尾淡出
    audio_chain = "loudnorm=I=-16:TP=-1.5:LRA=11,afade=t=out:st={:.1f}:d=3".format(max(args.target - 3.0, 0.5))
    if not args.no_ambience:
        filters += ("[1:a]atrim=0:{:.2f},volume=1.0[bg];[0:a]volume=1.0[main];"
                    "[main][bg]amix=inputs=2:duration=first:dropout_transition=0,{}"
                    "[a]").format(args.target, audio_chain)
    else:
        filters += f"[0:a]volume=1.0,{audio_chain}[a]"
    cmd2 += ["-filter_complex", filters, "-map", "[v]", "-map", "[a]",
             "-t", f"{args.target}", "-c:v", "libx264", "-preset", "veryfast",
             "-crf", str(args.crf), "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", str(out_path)]
    r = subprocess.run(cmd2, capture_output=True, text=True)
    if r.returncode != 0:
        print("混音失败:", r.stderr[-1000:])
        return 1

    final = probe_duration(out_path)
    size_mb = out_path.stat().st_size / 1024 / 1024
    shutil.rmtree(tmp_dir, ignore_errors=True)
    print(f"成片完成：{out_path}  {final:.1f}s  {size_mb:.1f}MB  {OUT_W}x{OUT_H}@{FPS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
