#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
备用配音：用 edge-tts 为每一镜的台词生成中文语音。

只有当 H3 原生音轨里的对白不可用（静音/糊成一团）时才启用本脚本，
作为 B 方案：H3 只出画面与环境音，台词由本脚本生成后在 build_final.py 里混音。

两个角色固定音色，保证跨镜声音一致：
  S1 高个子：zh-CN-YunxiNeural（低沉男声偏中性）→ 实际用 zh-CN-XiaoyiNeural 更柔；
  S2 低个子：zh-CN-XiaoxiaoNeural（清亮少女音）

用法：
  python3 scripts/gen_tts.py --out audio/tts
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shots import SHOTS  # noqa: E402

PROJECT_DIR = Path(__file__).resolve().parent.parent
MANIFEST = PROJECT_DIR / "prompts" / "manifest.json"

VOICES = {
    "S1": ("zh-CN-YunxiNeural", "-8%"),    # 低沉、语速略慢
    "S2": ("zh-CN-XiaoxiaoNeural", "+6%"),  # 清亮、语速偏快
}


def synth_line(text: str, voice: str, rate: str, out_path: Path) -> Path:
    """用 edge-tts 合成一句中文语音。"""
    import edge_tts

    async def run() -> None:
        comm = edge_tts.Communicate(text, voice, rate=rate)
        await comm.save(str(out_path))

    asyncio.run(run())
    return out_path


def main() -> int:
    """按清单逐句合成，输出 audio/tts/<shot>_<n>.wav。"""
    ap = argparse.ArgumentParser(description="edge-tts 备用配音")
    ap.add_argument("--out", default="audio/tts", help="输出目录")
    args = ap.parse_args()
    out_dir = PROJECT_DIR / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    index = {m["id"]: m for m in manifest}
    total = 0
    for shot in SHOTS:
        meta = index.get(shot["id"])
        if not meta:
            continue
        for i, (spk, line) in enumerate(shot["dial"], start=1):
            voice, rate = VOICES[spk]
            dest = out_dir / f"{shot['id']}_{i}.mp3"
            if dest.exists():
                continue
            synth_line(line, voice, rate, dest)
            total += 1
            print(f"  {dest.name} <- {line}")
    print(f"配音完成，共 {total} 句 -> {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
