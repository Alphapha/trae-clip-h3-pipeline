#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
参考资产生成：用服务器上的 FLUX.2 Klein 9B（base 20 步 / cfg 5 / euler）生成
两位主角与房间的定妆参考图，输出到本地 asset/ 目录。

两级策略保证人物一致性：
  1) 先文生图（T2I）出「母版」半身像；
  2) 再以母版为参考图走图生图（ReferenceLatent）生成全身像与双人合影，
     让五官与发型从母版传递到全身构图。

产出的参考图随后作为 H3 Ref2VA 的 <Picture 1..N> 输入，锁定跨镜人物一致性。

用法：
  python3 scripts/gen_ref_images.py                 # 生成全部参考图
  python3 scripts/gen_ref_images.py --only room     # 只生成指定条目
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from comfy_client import (base_url, collect_outputs, download_output, free_memory,  # noqa: E402
                          load_env, submit_prompt, upload_image, wait_prompt)

PROJECT_DIR = Path(__file__).resolve().parent.parent
ASSET_DIR = PROJECT_DIR / "asset"

ENV = load_env()
UNET = ENV.get("FLUX2_UNET", "flux-2-klein-base-9b-fp8.safetensors")
CLIP = ENV.get("FLUX2_CLIP", "qwen_3_8b_fp8mixed.safetensors")
VAE = ENV.get("FLUX2_VAE", "full_encoder_small_decoder.safetensors")

STEPS, CFG = 20, 5.0
PORTRAIT_W, PORTRAIT_H = 864, 1152      # 3:4 半身母版
FULL_W, FULL_H = 864, 1536              # 9:16 全身立绘

# 两位主角的外观锁定描述：所有相关出图共用同一段文字
TALL_DESC = ("a 25-year-old East Asian woman with waist-length straight black hair, "
             "an oval face, soft light-brown almond eyes, a gentle smile, "
             "wearing a cream oversized knit sweater, light grey loose trousers, "
             "white canvas sneakers and a thin silver necklace")
SHORT_DESC = ("a 22-year-old East Asian woman with a short straight black bob just below "
              "the ears, a round face with light freckles, large dark eyes and a playful "
              "smile, wearing a light pink hoodie, dark blue denim shorts, white socks, "
              "canvas sneakers and a small hair clip")
ROOM_DESC = ("the same bright apartment living room with a large floor-to-ceiling window "
             "on the left with sheer curtains, light oak wooden floor, a beige sofa on the "
             "right, white walls with one framed picture and a low coffee table with a "
             "small plant, warm afternoon daylight and soft shadows")

# 参考图条目定义：key -> (输出文件名, 宽, 高, 文生图提示词, 参考图key列表, seed)
JOBS = {
    "tall_master": (
        "ref_tall_master.png", PORTRAIT_W, PORTRAIT_H,
        f"photorealistic waist-up portrait photo of {TALL_DESC}, "
        "warm indoor window light coming from the left, plain light beige wall behind her, "
        "natural skin texture, 85mm lens, sharp focus, full face clearly visible",
        [], 41001),
    "short_master": (
        "ref_short_master.png", PORTRAIT_W, PORTRAIT_H,
        f"photorealistic waist-up portrait photo of {SHORT_DESC}, "
        "warm indoor window light coming from the left, plain light beige wall behind her, "
        "natural skin texture, 85mm lens, sharp focus, full face clearly visible",
        [], 42001),
    "tall_full": (
        "ref_tall_full.png", FULL_W, FULL_H,
        f"photorealistic full body photo, head to toe, of {TALL_DESC}, "
        "she is extraordinarily tall, 2.2 meters high, exceptionally long limbs, "
        "very large hands and feet, standing straight facing the camera, "
        f"in {ROOM_DESC}, low camera angle looking slightly up so the ceiling is close "
        "to her head, both feet visible, correct human anatomy",
        ["tall_master"], 41002),
    "short_full": (
        "ref_short_full.png", FULL_W, FULL_H,
        f"photorealistic full body photo, head to toe, of {SHORT_DESC}, "
        "she is very short, only 1.4 meters high, short limbs, small hands and feet, "
        "standing straight facing the camera, "
        f"in {ROOM_DESC}, camera at her own eye level, both feet visible, "
        "correct human anatomy",
        ["short_master"], 42002),
    "room": (
        "ref_room.png", FULL_W, FULL_H,
        f"photorealistic empty interior photo of {ROOM_DESC}, "
        "vertical composition, no people, no text",
        [], 43001),
    "both_full": (
        "ref_both_full.png", FULL_W, FULL_H,
        "photorealistic full body photo of the same two women standing side by side, "
        "the tall woman on the left wearing a cream oversized knit sweater and light grey "
        "trousers, the petite woman on the right wearing a light pink hoodie and denim "
        "shorts, the tall woman is 2.2 meters tall and her head almost touches the ceiling "
        "while the petite woman is only 1.4 meters tall and reaches barely her waist, "
        f"in {ROOM_DESC}, both faces clearly visible, both feet visible, correct scale "
        "difference between the two people",
        ["tall_master", "short_master"], 44001),
}


def build_workflow(prompt: str, width: int, height: int, seed: int,
                   ref_names: list, filename_prefix: str) -> dict:
    """构建 FLUX2 工作流。ref_names 为空即文生图，否则走 ReferenceLatent 图生图。"""
    wf = {
        "1": {"class_type": "UNETLoader",
              "inputs": {"unet_name": UNET, "weight_dtype": "default"}},
        "2": {"class_type": "CLIPLoader",
              "inputs": {"clip_name": CLIP, "type": "flux2"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": VAE}},
        "4": {"class_type": "CLIPTextEncode",
              "inputs": {"clip": ["2", 0], "text": prompt}},
        "5": {"class_type": "CLIPTextEncode",
              "inputs": {"clip": ["2", 0], "text": ""}},
        "63": {"class_type": "CFGGuider",
               "inputs": {"model": ["1", 0], "positive": ["4", 0],
                          "negative": ["5", 0], "cfg": CFG}},
        "62": {"class_type": "Flux2Scheduler",
               "inputs": {"steps": STEPS, "width": width, "height": height}},
        "61": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "euler"}},
        "73": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "6": {"class_type": "EmptyFlux2LatentImage",
              "inputs": {"width": width, "height": height, "batch_size": 1}},
        "64": {"class_type": "SamplerCustomAdvanced",
               "inputs": {"noise": ["73", 0], "guider": ["63", 0],
                          "sampler": ["61", 0], "sigmas": ["62", 0],
                          "latent_image": ["6", 0]}},
        "65": {"class_type": "VAEDecode",
               "inputs": {"samples": ["64", 0], "vae": ["3", 0]}},
        "9": {"class_type": "SaveImage",
              "inputs": {"images": ["65", 0], "filename_prefix": filename_prefix}},
    }
    # 图生图：母版经 VAEEncode 后以 ReferenceLatent 注入正负两支 conditioning
    for idx, ref_name in enumerate(ref_names):
        load_id, scale_id, enc_id = f"10_{idx}", f"80_{idx}", f"81_{idx}"
        wf[load_id] = {"class_type": "LoadImage", "inputs": {"image": ref_name}}
        wf[scale_id] = {"class_type": "ImageScaleToTotalPixels",
                        "inputs": {"image": [load_id, 0], "upscale_method": "lanczos",
                                   "megapixels": 1.0, "resolution_steps": 1}}
        wf[enc_id] = {"class_type": "VAEEncode",
                      "inputs": {"pixels": [scale_id, 0], "vae": ["3", 0]}}
        pos_ref = f"124_{idx}"
        neg_ref = f"122_{idx}"
        wf[pos_ref] = {"class_type": "ReferenceLatent",
                       "inputs": {"conditioning": ["4", 0], "latent": [enc_id, 0]}}
        wf[neg_ref] = {"class_type": "ReferenceLatent",
                       "inputs": {"conditioning": ["5", 0], "latent": [enc_id, 0]}}
        if idx == 0:
            wf["63"]["inputs"]["positive"] = [pos_ref, 0]
            wf["63"]["inputs"]["negative"] = [neg_ref, 0]
        else:
            # 多张参考图：链式挂在上一级 conditioning 上
            wf[pos_ref]["inputs"]["conditioning"] = [f"124_{idx-1}", 0]
            wf[neg_ref]["inputs"]["conditioning"] = [f"122_{idx-1}", 0]
    return {"prompt": wf, "client_id": "refimages"}


def run_job(key: str) -> Path:
    """生成一张参考图：组装工作流 → 提交 → 等待 → 下载到 asset/。"""
    fname, w, h, prompt, ref_keys, seed = JOBS[key]
    dest = ASSET_DIR / fname
    if dest.exists() and dest.stat().st_size > 10000:   # 断点续跑：已存在则跳过
        print(f"\n  {key} 已存在，跳过 -> {dest.name}")
        return dest
    ref_names = []
    for rk in ref_keys:
        p = ASSET_DIR / JOBS[rk][0]
        if not p.exists():
            raise FileNotFoundError(f"参考图缺失，无法做图生图: {p}")
        ref_names.append(upload_image(p, subfolder="ref"))
    wf = build_workflow(prompt, w, h, seed, ref_names, f"refs/{key}")
    t0 = time.time()
    pid = submit_prompt(wf)
    hist = wait_prompt(pid, timeout=3600, label=key)
    files = collect_outputs(hist)
    if not files:
        raise RuntimeError(f"{key}: 无产物输出")
    dest = ASSET_DIR / fname
    download_output(files[0], dest)
    print(f"\n  {key} -> {dest.name} ({dest.stat().st_size//1024} KB, {int(time.time()-t0)}s)")
    return dest


def main() -> int:
    """按依赖顺序生成全部参考图（母版优先，供后续图生图引用）。"""
    ap = argparse.ArgumentParser(description="生成 H3 Ref2VA 所需参考图")
    ap.add_argument("--only", nargs="*", default=None, help="只生成指定条目")
    args = ap.parse_args()
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    free_memory()
    order = ["tall_master", "short_master", "tall_full", "short_full", "room", "both_full"]
    todo = [k for k in order if not args.only or k in args.only]
    for key in todo:
        print(f"[ref] 生成 {key} ...")
        try:
            run_job(key)
        except Exception as e:  # noqa: BLE001 - 单条失败不阻断整体流程
            print(f"  !! {key} 失败: {e}")
            return 1
    print("参考图生成完成 ->", ASSET_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
