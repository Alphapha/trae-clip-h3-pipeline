#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ComfyUI HTTP API 客户端（3090 服务器 / x3090:8188）。

提供上传参考图、提交工作流、轮询等待、下载产物四个基础能力，
供 gen_ref_images.py（FLUX2 出参考图）与 gen_shots.py（H3 Ref2VA 出分镜）复用。

注意：ComfyUI 的 LoadImage 节点基于文件列表缓存，scp 直写 input/ 不会刷新缓存，
所有参考图必须走 /upload/image 接口。
"""

import json
import time
from pathlib import Path

import requests

PROJECT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_DIR / ".env"
POLL_INTERVAL = 8


def load_env(path: Path = ENV_FILE) -> dict:
    """解析 .env 文件，返回 KEY=VALUE 字典（忽略注释与空行）。"""
    env = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def base_url() -> str:
    """返回 ComfyUI 服务根地址（去掉末尾斜杠）。"""
    return load_env().get("COMFY_URL", "http://x3090:8188").rstrip("/")


def upload_image(image_path: Path, subfolder: str = "ref") -> str:
    """上传本地图片到服务器 input/ 目录，返回服务器侧文件名（含子目录前缀）。"""
    url = f"{base_url()}/upload/image"
    with open(image_path, "rb") as f:
        r = requests.post(
            url,
            files={"image": (image_path.name, f, "image/png")},
            data={"overwrite": "true", "subfolder": subfolder, "type": "input"},
            timeout=180,
        )
    r.raise_for_status()
    data = r.json()
    name = data["name"]
    sub = data.get("subfolder", "")
    return f"{sub}/{name}" if sub else name


def submit_prompt(workflow: dict, client_id: str = "clipgen") -> str:
    """提交工作流到 ComfyUI 队列，返回 prompt_id。"""
    r = requests.post(f"{base_url()}/prompt", json=workflow, timeout=120)
    if r.status_code != 200:
        raise RuntimeError(f"提交失败 HTTP {r.status_code}: {r.text[:2000]}")
    return r.json()["prompt_id"]


def wait_prompt(prompt_id: str, timeout: int = 7200, label: str = "") -> dict:
    """轮询 /history 等待任务完成，返回该 prompt_id 的 history 条目。"""
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = requests.get(f"{base_url()}/history/{prompt_id}", timeout=30)
        r.raise_for_status()
        hist = r.json().get(prompt_id)
        if hist and hist.get("outputs"):
            return hist
        q = requests.get(f"{base_url()}/queue", timeout=15).json()
        running = len(q.get("queue_running", []))
        pending = len(q.get("queue_pending", []))
        print(f"\r  等待 {label} 生成 ... (运行 {running} / 排队 {pending}，已等 {int(time.time()-t0)}s)   ",
              end="", flush=True)
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"等待 {label} 超时")


def collect_outputs(hist: dict) -> list:
    """从 history 条目中收集全部产物元数据（图片/视频/音频）。"""
    files = []
    for node_out in hist.get("outputs", {}).values():
        for key in ("images", "videos", "audio", "gifs"):
            for item in node_out.get(key, []) or []:
                if item.get("filename"):
                    files.append(item)
    return files


def download_output(item: dict, dest: Path) -> Path:
    """下载单个产物到本地路径。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    r = requests.get(f"{base_url()}/view", params={
        "filename": item["filename"],
        "subfolder": item.get("subfolder", ""),
        "type": item.get("type", "output"),
    }, timeout=900)
    r.raise_for_status()
    dest.write_bytes(r.content)
    return dest


def free_memory() -> None:
    """请求 ComfyUI 卸载模型并清理显存（切换图像/视频管线前调用）。"""
    try:
        requests.post(f"{base_url()}/free",
                      json={"unload_models": True, "free_memory": True}, timeout=120)
        print("已请求 ComfyUI 卸载模型并清理显存")
    except requests.RequestException as e:
        print(f"清理显存失败（忽略继续）: {e}")


def queue_state() -> dict:
    """返回队列状态（运行中/排队数量）。"""
    return requests.get(f"{base_url()}/queue", timeout=15).json()
