---

## **name: minimax-h3-zh-promptdescription: >-Writes high-quality MiniMax H3 full-reference prompts in Simplified Chinesesix-section text for ZealmanH3Desktop. Use when the user asks for an H3prompt, MiniMax 多参提示词, 六段式提示词, 中文版提示词, subject_definitions,or to rewrite a video idea into the desktop prompt box. Narrative is Chinese;structural tags stay English.**

# **MiniMax H3 中文提示词**

把用户的视频想法写成可粘贴进 ZealmanH3Desktop 提示词框的六段明文。叙述用简体中文，信息量对齐英文规范约 350–500 词，不要写成梗概。

只输出提示词本身。不要 JSON、不要 markdown 围栏、不要解释。

## **标签类除外**

下面这些是结构标签，保持英文原样，不翻译、不改成散文、不在输出里解释：

- 段名：`subject_definitions` / `summary` / `retention_analysis` / `detailed_description` / `overall_soundscape` / `non_diegetic_music`
- 参考标签：`<Subject N>` `<Picture N>` `<Video N>` `<Audio N>`
- 任务类型：`[reference generation]` `[video editing]` `[video continuation]` `[audio reuse]` `[audio reference]`，多个用 `+` 连接。禁止 `[text to video]`，禁止自造 `first-frame-to-video`
- 保留关系：可见内容用 `fully_preserved` / `partially_preserved` / `attribute_transfer` / `weak_reference`；音频用 `fully_copy` / `partially_copy` / `reference` / `weak_reference`
- 分镜与说话人：`[Shot N]`、`At MM:SS.mmm`、`(S1)` `(S2)` `(S1,S2)`
- 台词包裹：`<d>[Language] 台词</d>`。Language 只用 `Chinese` / `English` / `Korean` / `Japanese` 等英文全称，禁止 `zh` `en` `ja` `ko`
- 跨切与截断：`<scenetrans>` `<cutoff>`
- 运镜枚举写在中文句里，不翻译：Push In / Pull Out、Zoom In / Zoom Out、Pan Left / Pan Right、Truck Left / Truck Right、Tilt Up / Tilt Down、Pedestal Up / Pedestal Down、Arc Shot、Tracking Shot、Static Shot、POV、Shake Slightly / Shake Strongly、Roll Clockwise / Counterclockwise。幅度 `with small / large amplitude`，速度 `at slow / fast speed`
- 音色参考句整句保持英文，单独成行：`<Audio N> is the voice-timbre reference for <Subject M> (Sx).` 以及句号后的英文音色特征

除上述标签外，定义句、summary、retention 说明、分镜正文、环境音、配乐全部用简体中文。

## **六段顺序**

```
subject_definitions:
<一行一条>

summary:
[reference generation] 一句中文成片目标。

retention_analysis:
<一行一条>

detailed_description:
一两句中文风格开场，必须写在 [Shot 1] 之前。
[Shot 1] …
[Shot 2] At 00:03.500, …

overall_soundscape:
全片环境音与现场物理声。

non_diegetic_music:
N/A
```

段与段之间空一行。定义句、保留关系各占一行。

## **硬约束**

动笔前从用户原文抽出：台词、已有标签、镜数、运镜/景别、风格、否定项、语气。写完逐条核对，缺一条就补到落位。

- 用户已写的 `<d>` 台词逐字保留：不润色、不翻译、不删重复、不拆句不并句。只可补句末 `.` `?` `!`，去掉波浪号和表情。
- 用户已写的 `<Subject N> (Sx)`、`[Shot N]`、`<scenetrans>` / `<cutoff>`、任务类型，原样保留、不改号。
- 「不要 / 禁止 / 别 / 无 / 不出现」照做：不要配乐 → `non_diegetic_music` 写 `N/A`；不要切镜 → 只写 `[Shot 1]`；不要字幕 → 不写画面文字；不要说话 → 不写 `<d>`。
- 画面可见文字用英文双引号照抄原文，例如霓虹灯写着 “营业中”。
- 图里没有的外貌不要编。没给参考图时，按用户描述锁定特征，不要虚构 `<Picture N>`。
- 只能引用用户实际提供的图、视频、音频序号。

## **各段怎么写**

**subject_definitions** 一行一句，锁身份，不写动作、运镜、对白。中文句式必须是：

`<Subject 1> 是 <Picture 1> 中的年轻女子，深色长发披在一侧肩上，肤色偏白，蓝色针织开衫内搭白衬衫，戴细银项链。`

人物通常写 5–8 项可见特征：年龄感、发型发色与盘法、五官与妆容、肤色、服装款式/颜色/面料、配饰、体态。场景写空间、陈设、材质、主色、标志物、光线与天气，不要只写「雪景」「房间」。

用户已经写了规范定义句时，保留身份名，只在逗号后补图中可见、用户没写的特征。不要把「蓝衣女孩」改成「年轻女子」。

- 场景拼图：按方位拆（左上 / 右上 / 左下 / 右下），每格写看见的空间。不要收成一句「一座寺庙」。
- 角色设集：整张图合成一条，标明多视图角色设定；调用侧面或背面时写「调用 `<Subject N>` 的侧面 / 背面 / 特写」，不要按格子拆成多人或多场景。
- 只用来定义人物的图不要再单独立一个 `<Picture N>` 主体。多素材同一主体合并成一句，写明哪份提供外观、动作或音色。

**summary** 只写成片目标：类型、核心事件、时长、要达成的效果。不复述素材清单，不新开参考标签。有参考素材时任务类型从上面五个里选。只有用户明确要求剪辑、转场、特效、字幕、画中画、变速、混音、配乐替换时，才用 `[video editing]` / `[audio reuse]`。

**retention_analysis** 只评已定义内容有没有保住，不把新动作、新剧情、新运镜当成损失。每个标签一行，点名保留了哪些特征。本段不写 `(Sx)`。

`<Subject 1> (appears in [Shot 1], [Shot 3]): fully_preserved - 深色长发、蓝色开衫、细银项链保持不变，只有表情和朝向改变。`

`appears in` 里的镜头必须和正文实际写出的 `[Shot N]` 一致。`<Picture N>` 写它担任的角色，不写 appears in，例如 `<Picture 2> ([Shot 1] 首帧): fully_preserved - …`

**detailed_description** 才是成片正文。风格开场写画质、色调、镜头语言。用户给了风格（水墨、赛博朋克、定格动画）就用用户的，不要改成默认的电影写实。「电影感、戏剧性、杰作、8K、氛围感」没有信息，改成能看见的灯、位置和结束姿态。

每个镜头写清七件事，但七件事只服务一个动作：景别与构图、主体外观和画面位置、环境与光线、一个主要动作及其结束姿态、一个运镜（类型、幅度、速度；没有就写 Static Shot）、当前声音、参考内容在这一镜哪里生效。重要主体第一次清楚出场时，把定义段的外观落到可见画面；之后只用同一标签，不要重新定义。同一场的光源方向每镜重说一次，不要越写越平。

一镜的运动预算是三样：一个主要身体动作、一个运镜、一个环境响应（雪、布料、呼吸、光斑）。走路、开门、转身、对白再推近，要拆到下一镜，不要堆在同一镜。

先定人站在哪，再放镜头。写开始位置和结束位置，距离要能看见：隔着桌子、相距约一臂、从门口走到对方身侧。不要只写「靠近」。谁动、谁不动，决定谁在求谁。情绪写成身体，不写心理词：不写「他很害怕」，写「他后退半步，肩抵上门框，目光躲开对方」。

光写来源和相对镜头的方向，不写心情。例如「窗光从镜头左侧打来，脸的右侧留着仍能看清的阴影，发缘有一圈轮廓光」。同一场不换光源方向，除非人走到了另一处光里。背光或轮廓光不写，人脸容易糊进背景。

每个镜头要有一个任务：交代空间、关系、反应、细节或揭示。没有任务的镜头删掉。景别优先中景到近景；大远景容易多出人和糊脸，极特写容易坏掉五官和手指，真要用时把动作减到最少。人出画或被挡住时，写清出画方向和留下的结果，道具不要凭空消失。

`[Shot 1]` 不写时间。之后 `[Shot N] At MM:SS.mmm,`，切点必须小于总时长。

镜数：

| **时长** | **镜数** |
| --- | --- |
| 4.0–6.0 秒 | 1 或 2 |
| 7.0–10.0 秒 | 2 或 3 |
| 11.0–15.0 秒 | 3 到 5 |

每镜留 2.5–4.0 秒，禁止 1 秒碎切，禁止一参考一镜。4–6 秒的多主体用前景 / 中景 / 后景放进同一画面。

用户已经给了 N 个分镜时，从 `[Shot 1]` 写到 `[Shot N]`，禁止删镜、并镜、跳号。按镜数反推时长，不要死守 5 秒：1 镜 4–6 秒，2 镜 5–6 秒（对白密可到 7–10 秒），3 镜 7–10 秒（对白密可到 11–12 秒），4 镜必须 12–15 秒，5 镜必须 13–15 秒。用户没给分镜时，再按页面时长卡镜数。

切镜后先写 0.3–0.5 秒微动作（转头、停顿、对视、换气、落步），再出对白。禁止一镜开头就是 `<d>`。上一镜的动作或视线落点作为下一镜起幅。台词前先写脚步、开门、风雪、布料等物理声。一句台词跨切时，两镜衔接处都写 `<scenetrans>`，并写明这句台词无缝跨过切点；被结尾截断时在句尾写 `<cutoff>`。

**对白** 结构是：主体标签 + 说话人编号 + 中文发声动词 + `<d>[Language] 台词</d>`。画面内默认开口。`(Sx)` 按发声顺序从 `(S1)` 起编，同一人全程复用。

`<Subject 1> (S1) 低声说出，<d>[Chinese] 师姐，我们就快要到了。</d>`

语气写在 `<d>` 外面：低声说出、提高声音说出、颤抖着说出、带着笑意说出。用户明确写喊或吼时用「喊出」。不要把普通对白写成画外音或闭口。只有用户写了画外音 / 旁白 / 解说 / 内心独白，或说话人不在画面里，或台词是说书，才标 `off-screen`。齐声用一个复合编号，不要并排两个编号：

`<Subject 1> 和 <Subject 2> (S1,S2) 齐声说出，<d>[Chinese] 师姐我们一起去吧！</d>`

对不上已定义主体的旁白：`一名男声旁白 (S4) 以画外音说出，<d>[Chinese] 故事就从这里开始。</d>`。只有直接复用的完整音轨唱词才用 `<Audio N>` 当声源，不再编 `(Sx)`。

**overall_soundscape** 只写全片环境音和现场物理声，包括对白前的铺垫声。不写配乐，不重复整句台词。先写这个空间自己的房间底噪，再写窗外或门外持续的环境声，最后写跟可见动作同步的拟音。换镜头时底噪不断，除非人真的换了地方。沉默是一种选择，要写出来，不要留空。

**non_diegetic_music** 只写观众听得见、角色听不见的配乐：乐器、速度、动态。没有就写 `N/A`。

## **写完再查**

- 六段顺序齐全，叙述是中文，标签仍是英文
- 中文定义句是「`<Subject N>` 是 `<Picture N>` 中的…」
- 用户的台词、镜数、运镜、风格、否定项都在
- `appears in` 与正文镜头一致，切点小于总时长
- 切镜后有垫字，对白不是一开镜就出现
- 没有无故的画外音，齐声是 `(S1,S2)` 而不是两个编号并排
- 每镜只有一个主要动作、一个运镜、一个能拍照的结束姿态
- 光写了来源和镜头左右，情绪写成了身体动作
- 环境音是同一地点的连续底噪，不是每镜换一个房间

完整短例见 examples.md。