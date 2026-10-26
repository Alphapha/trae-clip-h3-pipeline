#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
按 skill.md 的六段式规范，把 scripts/shots.py 的分镜表编译成 MiniMax H3 全参考提示词。

输出：
  prompts/S01.md ... 每个镜头一份六段式明文（可直接粘贴进 H3 提示词框）
  prompts/manifest.json  批量生成用的清单（时长/帧数/参考图/seed/提示词路径）

六段顺序固定：subject_definitions / summary / retention_analysis /
detailed_description / overall_soundscape / non_diegetic_music。
叙述用简体中文，结构标签与参考标签保持英文原样。
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shots import FINAL_SHOT, ROOM_DESC, SHOTS, SUBJECT1_DESC, SUBJECT2_DESC  # noqa: E402

PROJECT_DIR = Path(__file__).resolve().parent.parent
PROMPT_DIR = PROJECT_DIR / "prompts"
ASSET_DIR = PROJECT_DIR / "asset"

FPS = 24
FRAME_GRID = 17          # H3 帧长吸附到 17k+5
SHOT_FRAMES = 311        # 12.96 秒
FINAL_FRAMES = 124       # 5.17 秒（片尾静止远景；成片阶段再对齐到 600 秒）

# 参考图编号 → (文件名, 说明)
REF_FILES = {
    1: ("ref_tall_full.png", "身高 2.2 米的高个子女生全身像"),
    2: ("ref_short_full.png", "身高 1.4 米的低个子女生全身像"),
    3: ("ref_room.png", "两人所在的公寓客厅"),
    4: ("ref_tall_master.png", "高个子女生的上半身母版，面部细节参考"),
    5: ("ref_short_master.png", "低个子女生的上半身母版，面部细节参考"),
    6: ("ref_both_full.png", "两人同框的全身比例参考"),
}

STYLE_OPENING = (
    "写实电影质感的暖调室内摄影，9:16 竖构图，浅景深，35mm 镜头，午后阳光从镜头左侧的落地窗"
    "斜照进来，脸的右侧留有柔和但看得清五官的阴影。全片保持两位角色的长相、发型、服装与身高比例"
    "完全一致：高个子约为低个子的 1.6 倍，同框时身高差必须一眼可见，绝不能变成身高接近。"
    "沿用参考图的身份与服装，台词口型同步；画面不得出现任何字幕、文字、标题或水印。"
)

AMBIENCE_BASE = (
    "这间客厅的低底噪贯穿全镜，窗外是极淡且不间断的车流声，偶尔有风吹动纱帘的细微响动。"
    "对白贴近、清楚，室内带一点自然回声。"
)

# 说话人 → 主体
SPEAKER = {"S1": ("<Subject 1>", "高个子女生"), "S2": ("<Subject 2>", "低个子女生")}


def frames_for_seconds(seconds: float) -> int:
    """秒 → 帧长，吸附到 H3 的 17k+5 帧网格。"""
    n = max(5, round(seconds * FPS))
    k = max(0, -(-(n - 5) // FRAME_GRID))
    return FRAME_GRID * k + 5


def build_subject_definitions() -> str:
    """主体定义段：锁身份，不写动作与运镜。"""
    lines = [
        f"<Subject 1> 是 <Picture 1> 中的年轻女子，{SUBJECT1_DESC}。",
        f"<Subject 2> 是 <Picture 2> 中的年轻女子，{SUBJECT2_DESC}。",
        f"<Picture 3> 是两人所在的公寓客厅，{ROOM_DESC}。",
        "<Picture 4>、<Picture 5> 分别是 <Subject 1>、<Subject 2> 的上半身母版，只补充面部细节；"
        "<Picture 6> 是两人同框的全身合影，只用于确定身高比例。",
    ]
    return "\n".join(lines)


def build_retention(shot_no: int, refs: list) -> str:
    """保留关系段：只评已定义内容是否保住，appears in 与正文镜头一致。"""
    lines = []
    if 1 in refs or 4 in refs:
        lines.append(
            f"<Subject 1> (appears in [Shot {shot_no}]): fully_preserved - 黑色直发、鹅蛋脸、"
            "浅棕杏眼、奶油白针织衫与浅灰长裤、身高 2.2 米全部不变，只有姿态与表情改变。")
    if 2 in refs or 5 in refs:
        lines.append(
            f"<Subject 2> (appears in [Shot {shot_no}]): fully_preserved - 齐耳黑短发、圆脸雀斑、"
            "大而亮的眼睛、淡粉卫衣与牛仔短裤、身高 1.4 米全部不变，只有姿态与表情改变。")
    lines.append(
        f"<Picture 3> ([Shot {shot_no}] 全程背景): fully_preserved - 左侧落地窗、橡木地板、"
        "右侧米色沙发、白墙挂画与茶几绿植的位置与色调不变。")
    return "\n".join(lines)


def build_dialogue(dial: list) -> str:
    """对白段：主体标签 + 说话人编号 + 中文发声动词 + <d>[Chinese] 台词</d>。"""
    if not dial:
        return ""
    parts = []
    for spk, line in dial:
        tag, name = SPEAKER[spk]
        voice = "低沉温柔的中音" if spk == "S1" else "清亮偏高的少女音"
        parts.append(f"{tag} ({spk}) 用{voice}说出，<d>[Chinese] {line}</d>")
    return "。".join(parts) + "。"


def build_prompt(shot: dict, shot_no: int, with_dialogue: bool = True) -> str:
    """组装单个镜头的六段式提示词。with_dialogue=False 时不写台词（配合外挂配音）。"""
    refs = shot["refs"]
    dia = build_dialogue(shot["dial"]) if with_dialogue else ""
    detail = (
        f"[Shot {shot_no}] {shot['size']}。{shot['action']}"
        f" {shot['sound']}"
    )
    if dia:
        detail += f" {dia}"
    detail += f" 运镜：{shot['cam']}，在动作结束、姿态稳定之后才停住。"
    summary = (
        f"[reference generation] 竖屏短片《身高差》的第 {shot_no} 镜："
        f"{shot['act']}段落，{shot['action'].split('，')[0]}，"
        "保持两人身高悬殊、人物一致、声音与画面一致。"
    )
    sections = [
        "subject_definitions:\n" + build_subject_definitions(),
        "summary:\n" + summary,
        "retention_analysis:\n" + build_retention(shot_no, refs),
        "detailed_description:\n" + STYLE_OPENING + "\n" + detail,
        "overall_soundscape:\n" + AMBIENCE_BASE + " " + shot["sound"],
        "non_diegetic_music:\nN/A",
    ]
    return "\n\n".join(sections) + "\n"


def main() -> int:
    """编译全部分镜提示词并写出 manifest。"""
    ap = argparse.ArgumentParser(description="编译六段式提示词")
    ap.add_argument("--no-dialogue", action="store_true",
                    help="不写台词（H3 原生对白不可用时，配合外挂配音）")
    args = ap.parse_args()
    PROMPT_DIR.mkdir(parents=True, exist_ok=True)
    all_shots = list(SHOTS) + [FINAL_SHOT]
    manifest = []
    for idx, shot in enumerate(all_shots, start=1):
        frames = FINAL_FRAMES if shot is FINAL_SHOT else SHOT_FRAMES
        text = build_prompt(shot, idx, with_dialogue=not args.no_dialogue)
        path = PROMPT_DIR / f"{shot['id']}.md"
        path.write_text(text, encoding="utf-8")
        manifest.append({
            "id": shot["id"],
            "no": idx,
            "act": shot["act"],
            "frames": frames,
            "seconds": round(frames / FPS, 3),
            "seed": 70000 + idx,
            "refs": [{"pic": r, "file": REF_FILES[r][0]} for r in shot["refs"]],
            "prompt": text,
            "dialogue": [{"speaker": s, "line": t} for s, t in shot["dial"]],
        })
    total_frames = sum(m["frames"] for m in manifest)
    (PROMPT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成 {len(manifest)} 镜提示词 -> {PROMPT_DIR}")
    print(f"总时长 {total_frames/FPS:.1f} 秒（{total_frames} 帧）")
    missing = [m["file"] for m in manifest for m in m["refs"]
               if not (ASSET_DIR / m["file"]).exists()]
    if missing:
        print("缺少参考图（先生成再编译）：", sorted(set(missing)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
