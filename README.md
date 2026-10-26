# 《身高差》— MiniMax H3 竖屏短片生成管线

用 3090 服务器上的 ComfyUI + **MiniMax H3（Ref2VA 全参考模式）**，把 `剧本.md` 做成一支
**9:16 竖屏、10 分钟**的写实短片：两位身高悬殊的女生（2.2 米 / 1.4 米）在同一间公寓客厅里
比身高、比手脚大小，随后进入一连串亲密暧昧的相处段落。

全程在远端服务器出片，本地只做「提示词编译 → 提交 → 下载 → 质检 → 合成」。

---

## 〇、本次交付结果（2026-10-27）

| 项目 | 结果 |
| --- | --- |
| 成片 | `video/身高差_10分钟成片.mp4`，**599.999 秒（整 10 分钟）**，1080×1920 / 24fps / H.264 / AAC 立体声 48kHz，228.9MB，响度已标准化到 -16 LUFS |
| 分镜 | 47 镜（46 镜 × 12.96 秒 + 片尾 5.17 秒），全部 432×768 生成，成片阶段统一上采样到 1080×1920 |
| 镜头内容 | 第一幕比身高/比手脚（12 镜）→ 第二幕亲密段落（18 镜，含剧本指定的从身后抱住、抱住大腿、俯身亲吻、公主抱）→ 第三幕自由发挥相处（15 镜）→ 片尾收束（2 镜） |
| 人物一致性 | 全片两张脸、发型、服装、身高比（2.2m / 1.4m）稳定，场景始终是同一间客厅（见 `video/_qc/总览拼图.jpg`） |
| 画面质检 | `qc_shots.py` 47/47 通过（时长、9:16 画幅、音轨齐全），全程无字幕/水印 |
| 对白质检 | `qc_asr.py` 45 镜有台词，平均相似度 0.61；8 镜偏差较大（S09/S10/S13/S15/S25/S26/S38/S40），均为「哇——」「……嗯。」「痒。」这类短促语气词的模型自由发挥 |
| 声音 | H3 原生音轨（对白+环境音同一前向生成），无外挂配音，跨镜房间底噪由成片阶段叠加的连续底噪统一 |
| 生成耗时 | 单卡 3090，47 镜共约 5.5 小时（平均 5.9 分钟/镜） |

## 一、目录结构

```
trae-剪辑-autodl-skill/
├── 剧本.md                # 原始剧本（设定来源：身高、服装、亲密度段落）
├── skill.md               # H3 六段式中文提示词规范（本项目提示词的编写依据）
├── examples.md            # 六段式提示词范例
├── .env / .env.example    # 服务器地址、模型文件名等（.env 不入库）
├── asset/                 # 参考资产：角色定妆图与场景图（H3 的 <Picture 1..6>）
│   ├── ref_tall_master.png    # 高个子母版（脸+服装）
│   ├── ref_short_master.png   # 低个子母版（脸+服装）
│   ├── ref_tall_full.png      # 高个子全身像（<Picture 1>）
│   ├── ref_short_full.png     # 低个子全身像（<Picture 2>）
│   ├── ref_room.png           # 客厅场景（<Picture 3>）
│   └── ref_both_full.png      # 两人同框比例参照（<Picture 6>）
├── prompts/               # 编译产物：每镜一份六段式提示词 + manifest.json
│   ├── S01.md … S47.md
│   └── manifest.json     # 批量生成清单（时长/帧数/参考图/seed/提示词）
├── scripts/
│   ├── shots.py           # 分镜表（数据层）：47 镜的动作/景别/运镜/台词
│   ├── build_prompts.py   # 分镜表 → 六段式提示词 + manifest
│   ├── comfy_client.py    # ComfyUI HTTP 客户端（上传/提交/轮询/下载）
│   ├── gen_ref_images.py  # FLUX2 生成 asset/ 参考图
│   ├── gen_shots.py       # H3 Ref2VA 批量出分镜视频
│   ├── gen_tts.py         # 备用配音（edge-tts），H3 原生对白不可用时启用
│   ├── qc_shots.py        # 分镜质检：时长/画幅/音轨 + 抽帧拼图
│   ├── qc_asr.py          # 对白质检：本地 ASR 转写音轨，与提示词台词逐镜比对
│   └── build_final.py     # ffmpeg 合成 10 分钟成片
├── video/                 # 成片与中间产物
│   ├── shots/S01.mp4 …    # 单镜视频
│   ├── _qc/               # 质检抽帧与报告
│   └── 身高差_10分钟成片.mp4
└── logs/                  # 运行日志
```

## 二、使用方法

### 0. 前置条件

- 本机已配置到 3090 服务器的 SSH 公钥登录（`ssh x3090` 可用），ComfyUI 监听 `8188`；
- 服务器已安装 FLUX.2 Klein 9B 与 MiniMax H3 的全部权重（见下表）；
- 本机安装 `requests`、`edge-tts`、`Pillow`，以及 ffmpeg（脚本内硬编码 `/usr/local/bin/ffmpeg`）。

| 用途 | 服务器模型文件 |
| --- | --- |
| H3 参考生视频（Ref2VA） | `models/diffusion_models/minimax_h3_ref2va_pruned_int8_convrot.safetensors` |
| H3 文本/多模态编码器 | `models/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` |
| H3 视频 VAE / 音频 VAE | `models/vae/minimax_h3_video_vae_fp16.safetensors` / `minimax_h3_audio_vae_fp32.safetensors` |
| 参考图生成（文生图/图生图） | `models/diffusion_models/flux-2-klein-base-9b-fp8.safetensors` + `qwen_3_8b_fp8mixed.safetensors` + `full_encoder_small_decoder.safetensors` |

### 1. 生成参考图（一次即可，约 10 分钟）

```bash
python3 scripts/gen_ref_images.py            # 断点续跑，已存在的会跳过
```

产出 `asset/` 六张参考图。高个子/低个子先用文生图出「母版」，再用母版做图生图得到全身像，
保证同一人；双人合影用两张母版同时做参考。

### 2. 编译六段式提示词

```bash
python3 scripts/build_prompts.py             # 输出 prompts/*.md 与 manifest.json
python3 scripts/build_prompts.py --no-dialogue   # 不写台词（外挂配音时用）
```

提示词严格按 `skill.md` 的六段结构：`subject_definitions / summary / retention_analysis /
detailed_description / overall_soundscape / non_diegetic_music`，叙述用简体中文，
结构标签、`<Subject N>`、`<Picture N>`、`[Shot N]`、`(S1)`、`<d>[Chinese]…</d>` 保持英文原样。

### 3. 批量生成分镜

```bash
# 单镜试跑（先看效果再批量）
python3 scripts/gen_shots.py --only S01 --steps 8 --width 432 --height 768

# 全量（本项目定稿参数）
python3 scripts/gen_shots.py --steps 8 --width 432 --height 768 --free-each \
    --deadline 2026-10-27T08:25:00 --order "$(cat logs/order.txt)"

# 设置早班截止时间，到点自动收工
python3 scripts/gen_shots.py --deadline 2026-10-27T07:30:00
```

单镜参数：

| 参数 | 说明 |
| --- | --- |
| `--steps` | 采样步数。官方模板 20 步；本项目定稿 8 步（蒸馏 int8 模型，8 步画质可用且提速 2.5 倍） |
| `--width/--height` | 画布。H3 原生短边 768、上限 768×1344；本项目定稿 432×768（严格 9:16，成片阶段再上采样到 1080×1920） |
| `--ref-size` | 参考图策略：`match`（快，默认）/ `max`（身份保真更好但慢数倍） |
| `--free-each` | 每镜前调 `/free` 清空显存（见「显存与速度」一节） |
| `--order` | 生成优先顺序（逗号分隔镜头 id）。时间不够时先出剧本重点镜头，合成时仍按片号排序 |
| `--frames` / `--tag` | 覆盖帧长与输出文件名后缀，用于测速探针 |
| `--force` | 已存在的分镜也重跑 |
| `--no-audio` | 不生成音轨（用于验证画面） |
| `--deadline` | 截止时间，之后不再提交新镜头（已提交的那一镜仍会跑完） |

### 4. 显存与速度（实测，重要）

H3 在 24GB 单卡上的瓶颈不是算力而是**显存驻留与注意力长度**，两条实测结论：

1. **不要用 `--lowvram` 启动 ComfyUI。** 20GB 的 int8 DiT 在该模式下按层 offload，
   单步多耗 7%–40%，且每个新任务要额外 ~200s 重新加载。默认启动即可。
2. **单步耗时随帧数超线性增长**（注意力在所有潜帧上展开），单镜越短越划算：

   | 画布 | 帧数 | 步数 | 单步耗时 | 每帧·步 |
   | --- | --- | --- | --- | --- |
   | 480×832 | 124 | 12 | 8.9s | 0.072s |
   | 480×832 | 311 | 12 | 38.1s | 0.123s |
   | 432×768 | 311 | 8 | 29.7s | 0.119s |
   | 320×576 | 311 | 8 | 11.4s | 0.046s |

   也就是说 311 帧的每帧成本约为 124 帧的 **1.7 倍**。要同样的总时长，
   应优先「多镜短片」而不是「少镜长片」。本项目 47 镜 × 311 帧（12.96s）是折中点。

3. **文本编码器与 DiT 无法同时常驻**（15.7GB + 20GB > 24GB），`--free-each` 让每个任务
   从干净显存开始，采样时 DiT 才能完整驻留。单镜实测 167–205s（含加载与解码）。

### 5. 质检

```bash
# 画面与音轨质检：逐镜查时长/画幅/音轨，并抽首中尾三帧到 video/_qc
python3 scripts/qc_shots.py

# 对白质检：用本地 ASR 把 H3 原生音轨转写，和提示词里的台词逐镜对照
python3 -m venv .venv-asr && .venv-asr/bin/pip install faster-whisper
HF_ENDPOINT=https://hf-mirror.com .venv-asr/bin/python scripts/qc_asr.py
```

`qc_asr.py` 是「声音一致性」的验收关：H3 的对白是原生生成的，只有把音轨转写出来
和台词比对，才能确认不是「有声音但没说对」的哑片。实测 tiny 模型也能把
「两米二整，一分不差」转成「良米二整 一分補插」这类同音字，说明人耳听到的是对的台词。

评分已做三重容错：繁转简（`我飛起來啦` = `我飞起来了`）、阿拉伯数字转中文
（`2.2.2` = `两米二`）、Jaccard 与包含度取大值。剩余被判为「差异」的 8 镜，
都是「哇——」「……嗯。」「痒。」这类短促语气词，模型会自由发挥，属于 H3 的固有随机性：
需要严格对齐时，用 `scripts/gen_tts.py`（edge-tts）外挂配音，
并用 `build_prompts.py --no-dialogue` 重编译提示词去掉原生对白。

### 6. 合成成片

```bash
python3 scripts/build_final.py --out video/身高差_10分钟成片.mp4 --target 600
```

合成分三步（`scripts/build_final.py`）：

1. **统一画幅**：统计各分镜分辨率，把不一致的（测速镜可能是 480×832 / 432×768）
   统一转成主流分辨率，参数一致后才能安全拼接（concat 解复用器要求流参数相同）；
2. **拼接**：concat 解复用器 + 流拷贝，不重编码；
3. **成片输出**：上采样到 1080×1920 / 24fps / yuv420p，叠一条极低的粉红噪房间底噪
   （让切点之间的房间声不断）；音频再走一遍 `loudnorm=I=-16:TP=-1.5:LRA=11`
   （H3 原生音轨整体偏轻，标准化后对白才够响），最后 3 秒音频淡出、视频 2 秒淡出，
   总时长精确对齐 `--target`（默认 600 秒）。

常用参数：`--target`（目标秒数）、`--no-ambience`（不叠底噪）、`--crf`（画质，默认 18）。

## 三、注意事项

1. **ComfyUI 的图片列表有缓存**：`LoadImage` 只能看见 `/upload/image` 接口登记过的文件，
   `scp` 直写 `input/` 不会被识别。所有参考图必须走 `comfy_client.upload_image()`。
2. **`SaveVideo` 必须显式传 `format` 与 `codec`**（本项目固定 `auto`/`auto`），
   否则采样跑完十几分钟后才报错。
3. **H3 帧长必须吸附到 `17k+5` 网格**：311 帧 = 12.96 秒，124 帧 = 5.17 秒，
   传其它值会被自动向上吸附。
4. **显存**：H3 int8 + qwen3vl-nvfp4 在 24GB 卡上靠按层 offload 跑，
   不要在同一张卡上同时开 FLUX2 出图任务；切管线前调用 `--free-memory`。
5. **时长是硬约束**：14400 帧 ÷ 24fps = 600 秒。帧数 × 步数 × 像素决定 GPU 时间，
   改分辨率或步数前先跑一镜测速，再决定批量参数。
6. **人物一致性靠参考图**：`<Picture 1>/<Picture 2>` 必须始终传同一组参考图；
   近景镜头追加 `<Picture 4>/<Picture 5>` 母版补面部细节。
7. **画面不得出现文字**：提示词里已写死「不得出现任何字幕、文字、标题、贴条或水印」，
   QC 时要专门抽帧检查有没有被烧进画面的字。
8. **`.env` 不要提交**（含服务器地址与模型名），`.env.example` 是模板。

## 四、常见问题与解决办法

**Q1：提交后立刻报 `HTTP 400 / prompt validation failed`？**
多半是工作流输入格式错了。本项目最容易踩的是 `MiniMaxH3ReferenceToVideo` 的
`ref_images`：它是 Autogrow 输入，API 里必须写成字典
`{"ref_image_0": ["10_0", 0], "ref_image_1": ["10_1", 0]}`，键名是「前缀_序号」。

**Q2：`LoadImage` 报找不到文件？**
参考图没走 `/upload/image`（见注意事项 1），或者文件名拼错。日志会打印「上传参考图 xxx」，
对照一下服务器 `input/ref/` 目录。

**Q3：生成出来的视频没有声音 / 对白糊成一团？**
H3 是原生音视频联合生成，对白在提示词的 `<d>[Chinese]…</d>` 里。跑一镜后用
`ffprobe` 看有没有音轨、用 `video/_qc/` 的抽帧看口型；如果原生对白不可用，
改用外挂配音：`python3 scripts/gen_tts.py` 生成台词，`build_prompts.py --no-dialogue`
重编译提示词后再重跑分镜。

**Q4：一镜太慢，来不及出 10 分钟？**
先测速（`--only S01`），再按「总帧数 × 步数 × 像素」估算。提速顺序：
降步数 12→8 → 降分辨率 432×768→320×576 → 减镜数。每镜约 40–110 秒的固定开销
（模型加载 + 解码），镜数越少越省。

**Q5：成片比 10 分钟短/长？**
`build_final.py --target 600` 会按目标时长裁切或补齐；分镜总时长由
`prompts/manifest.json` 里的帧数决定，改 `scripts/shots.py` 的 `SHOT_FRAMES` 后
重新编译即可。

**Q6：画面里出现了字幕或乱码文字？**
H3 有时会自己加字幕。在提示词里加「画面中不得出现任何字幕、文字、标题、贴条或水印」
（本项目已包含），仍出现时用 `--force` 换 seed 重跑该镜。

**Q7：两张脸不像同一个人？**
确认该镜确实传了 `<Picture 1>/<Picture 2>`；近景加母版 `<Picture 4>/<Picture 5>`；
必要时把 `--ref-size` 换成 `max`（更慢但身份保真更好）。

**Q8：Mac 上 ffmpeg 版本不同导致滤镜报错？**
本项目用 `scale/crop/fps/format/aresample/aformat/volume/amix/anoisesrc/fade`，
ffmpeg 5+ 通用。若本机 ffmpeg 路径不同，改 `scripts/build_final.py` 与
`scripts/qc_shots.py` 顶部的 `FFMPEG` / `FFPROBE` 常量。

**Q9：一镜要 3 分钟，怎么压到 10 分钟成片？**
按优先级依次调：① `--steps` 8→6；② `--width/--height` 432×768→320×576；
③ 缩短单镜帧数（`--frames`，但注意每帧成本会随帧数超线性上升）；
④ 减少镜数（每镜固定开销约 40–80s：模型加载 + VAE 解码）。
先跑 `--only S01 --frames 124 --tag probe` 测速，再按「总帧数 × 步数 × 像素」估算总时长。

**Q10：时间不够，如何先出重点镜头？**
`--order "S01,S02,...,S16,S46,S47"` 让生成顺序与片号顺序解耦：合成时仍按
`prompts/manifest.json` 的片号排序，所以时间不够时也是一部完整有头有尾的片子。

**Q11：合成时报错 / 成片花屏？**
多半是分镜分辨率或帧率不一致。`build_final.py` 会自动把分辨率不一致的分镜统一转码；
若是帧率不同，把 `scripts/build_final.py` 里的 `FPS` 与分镜保持一致即可。

**Q12：怎样确认 ComfyUI 启动参数是对的？**
`curl -s http://x3090:8188/system_stats` 看版本；启动日志里
`Set vram state to: NORMAL_VRAM` 且**没有** `--lowvram`。启动命令：
`python main.py --listen 0.0.0.0 --port 8188`。
