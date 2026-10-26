#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MiniMax H3 Ref2VA 分镜批量生成器。

对每一镜：把 asset/ 里的参考图上传到 ComfyUI input/，用 prompts/manifest.json 里的
六段式提示词提交 MiniMaxH3ReferenceToVideo（ref2va），生成带原生音频的竖屏视频，
下载到 video/shots/<id>.mp4。

关键参数（与官方 H3 模板一致）：
  - 画布短边 768（上限 768x1344），9:16 取 480x832 或 768x1344，均为 32 的倍数
  - 帧长吸附到 17k+5 网格（311 帧 = 12.96 秒）
  - 采样 res_multistep / simple / denoise 1.0
  - SaveVideo 必须显式传 format 与 codec，否则采样跑完才报错

用法：
  python3 scripts/gen_shots.py --only S01 --steps 12
  python3 scripts/gen_shots.py --from 2 --deadline 2026-10-27T08:00:00
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comfy_client import (collect_outputs, download_output, free_memory, load_env,  # noqa: E402
                          submit_prompt, upload_image, wait_prompt)

PROJECT_DIR = Path(__file__).resolve().parent.parent
PROMPT_DIR = PROJECT_DIR / "prompts"
ASSET_DIR = PROJECT_DIR / "asset"
SHOT_DIR = PROJECT_DIR / "video" / "shots"
MANIFEST = PROMPT_DIR / "manifest.json"

ENV = load_env()
UNET_REF2VA = ENV.get("H3_UNET_REF2VA", "minimax_h3_ref2va_pruned_int8_convrot.safetensors")
CLIP = ENV.get("H3_CLIP", "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors")
VAE_VIDEO = ENV.get("H3_VAE_VIDEO", "minimax_h3_video_vae_fp16.safetensors")
VAE_AUDIO = ENV.get("H3_VAE_AUDIO", "minimax_h3_audio_vae_fp32.safetensors")

# 参考图上传缓存：文件名 → 服务器侧名
_UPLOADED: dict = {}


def upload_ref(path: Path) -> str:
    """上传参考图（同一文件只上传一次），返回服务器侧文件名。"""
    if path.name not in _UPLOADED:
        _UPLOADED[path.name] = upload_image(path, subfolder="ref")
        print(f"  上传参考图 {path.name} -> {_UPLOADED[path.name]}")
    return _UPLOADED[path.name]


def build_workflow(prompt: str, width: int, height: int, length: int, seed: int,
                   ref_names: list, name: str, steps: int, with_audio: bool) -> dict:
    """构建单个镜头的 H3 Ref2VA API 工作流。"""
    wf = {
        # ---- 模型加载 ----
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": UNET_REF2VA, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": CLIP, "type": "minimax", "device": "default"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": VAE_VIDEO}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": VAE_AUDIO}},
        # ---- 条件与潜空间：参考图 + 提示词 → 视频+音频潜空间 ----
        "104": {"class_type": "MiniMaxH3ReferenceToVideo",
                "inputs": {"clip": ["2", 0], "vae": ["3", 0], "audio_vae": ["4", 0],
                           "prompt": prompt, "width": width, "height": height,
                           "length": length, "ref_image_size": "match"}},
        # ---- 采样（官方模板：res_multistep / simple / denoise 1.0）----
        "15": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "16": {"class_type": "BasicGuider",
               "inputs": {"model": ["1", 0], "conditioning": ["104", 0]}},
        "17": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "9": {"class_type": "BasicScheduler",
              "inputs": {"model": ["1", 0], "scheduler": "simple",
                         "steps": steps, "denoise": 1.0}},
        "14": {"class_type": "SamplerCustomAdvanced",
               "inputs": {"noise": ["15", 0], "guider": ["16", 0],
                          "sampler": ["17", 0], "sigmas": ["9", 0],
                          "latent_image": ["104", 1]}},
        # ---- 解码与封装 ----
        "20": {"class_type": "VAEDecode",
               "inputs": {"samples": ["14", 0], "vae": ["3", 0]}},
        "91": {"class_type": "CreateVideo",
               "inputs": {"images": ["20", 0], "fps": 24, "bit_depth": 8}},
        "92": {"class_type": "SaveVideo",
               "inputs": {"video": ["91", 0], "filename_prefix": f"shots/{name}",
                          "format": "auto", "codec": "auto"}},
    }
    if with_audio:
        wf["23"] = {"class_type": "VAEDecodeAudio",
                    "inputs": {"samples": ["14", 0], "vae": ["4", 0]}}
        wf["91"]["inputs"]["audio"] = ["23", 0]
    # 参考图：Autogrow 输入在 API 里是 {"ref_image_0": [节点, 输出索引], ...}
    if ref_names:
        refs = {}
        for i, rn in enumerate(ref_names):
            lid = f"10_{i}"
            wf[lid] = {"class_type": "LoadImage", "inputs": {"image": rn}}
            refs[f"ref_image_{i}"] = [lid, 0]
        wf["104"]["inputs"]["ref_images"] = refs
    return {"prompt": wf, "client_id": "h3shots"}


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    ap = argparse.ArgumentParser(description="H3 Ref2VA 分镜批量生成")
    ap.add_argument("--only", nargs="*", default=None, help="只生成指定镜头 id")
    ap.add_argument("--from", dest="start", type=int, default=None, help="起始镜号（含）")
    ap.add_argument("--to", dest="end", type=int, default=None, help="结束镜号（含）")
    ap.add_argument("--steps", type=int, default=12, help="采样步数（官方模板 20，12 为提速档）")
    ap.add_argument("--width", type=int, default=480, help="画布宽")
    ap.add_argument("--height", type=int, default=832, help="画布高")
    ap.add_argument("--ref-size", default="match", choices=["match", "max"],
                    help="参考图尺寸策略：match 快，max 身份保真更好但更慢")
    ap.add_argument("--no-audio", action="store_true", help="不生成音频轨")
    ap.add_argument("--force", action="store_true", help="已存在的分镜也重新生成")
    ap.add_argument("--deadline", default=None,
                    help="截止时间（YYYY-MM-DDTHH:MM:SS），超过后不再启动新镜头")
    ap.add_argument("--free-memory", action="store_true", help="开跑前清一次显存")
    ap.add_argument("--frames", type=int, default=None, help="覆盖帧长（测速用）")
    ap.add_argument("--tag", default=None, help="输出文件名后缀（测速用，如 probe）")
    ap.add_argument("--order", default=None,
                    help="生成优先顺序（逗号分隔的镜头 id），用于时间不够时先出重点镜头")
    ap.add_argument("--free-each", action="store_true",
                    help="每镜前清空显存（20GB DiT 与 15.7GB 文本编码器无法同时常驻，"
                         "不清理会让 DiT 部分 offload，单步耗时暴涨约 4 倍）")
    return ap.parse_args()


def main() -> int:
    """主流程：读取清单 → 逐镜提交 → 等待 → 下载。"""
    args = parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    deadline = datetime.fromisoformat(args.deadline) if args.deadline else None

    todo = []
    for m in manifest:
        if args.only and m["id"] not in args.only:
            continue
        if args.start and m["no"] < args.start:
            continue
        if args.end and m["no"] > args.end:
            continue
        todo.append(m)
    if args.order:                       # 按指定优先顺序重排（时间不够时先出重点镜头）
        rank = {sid: i for i, sid in enumerate(args.order.split(","))}
        todo.sort(key=lambda m: rank.get(m["id"], 999))
    if not todo:
        print("没有符合条件的镜头")
        return 0

    if args.free_memory:
        free_memory()

    total_frames = 0
    plan_frames = sum((args.frames or m["frames"]) for m in todo)
    t_start = time.time()
    for i, m in enumerate(todo, start=1):
        dest = SHOT_DIR / f"{m['id']}.mp4"
        if dest.exists() and dest.stat().st_size > 10000 and not args.force:
            print(f"[{i}/{len(todo)}] {m['id']} 已存在，跳过")
            total_frames += m["frames"]
            continue
        if deadline and datetime.now() >= deadline:
            print(f"!! 已到截止时间 {deadline}，停止提交新镜头（已完成 {i-1}/{len(todo)}）")
            break
        try:
            frames = args.frames or m["frames"]
            if args.free_each:
                free_memory()
            ref_names = [upload_ref(ASSET_DIR / r["file"]) for r in m["refs"]]
            wf = build_workflow(m["prompt"], args.width, args.height, frames,
                                m["seed"], ref_names, m["id"], args.steps,
                                not args.no_audio)
            if args.ref_size != "match":
                wf["prompt"]["104"]["inputs"]["ref_image_size"] = args.ref_size
            t0 = time.time()
            pid = submit_prompt(wf)
            print(f"[{i}/{len(todo)}] {m['id']} 已提交（{frames}帧≈{frames/24:.2f}s, "
                  f"{args.width}x{args.height}, {args.steps}步, refs={len(ref_names)}）")
            hist = wait_prompt(pid, timeout=7200, label=m["id"])
            files = collect_outputs(hist)
            if not files:
                raise RuntimeError("无产物输出")
            if args.tag:
                dest = SHOT_DIR / f"{m['id']}_{args.tag}.mp4"
            download_output(files[0], dest)
            cost = time.time() - t0
            total_frames += frames
            done_frames = sum((args.frames or x["frames"]) for x in todo[:i])
            eta = (time.time() - t_start) / max(done_frames, 1) * max(plan_frames - done_frames, 0)
            print(f"\n    -> {dest.name} ({dest.stat().st_size//1024} KB, {int(cost)}s, "
                  f"预计剩余 {eta/60:.0f} 分钟)")
        except Exception as e:  # noqa: BLE001 - 单镜失败继续下一镜
            print(f"\n    !! {m['id']} 失败: {e}")
            continue
    print(f"批量生成结束，共 {len(todo)} 镜，总时长 {total_frames/24:.1f} 秒")
    return 0


if __name__ == "__main__":
    sys.exit(main())
