---
name: opusv3d
description: 用代码做 3D 短片：先选片种（角色出场、产品展示、建筑与空间、场景氛围、讲解可视化、微叙事），再选画质（写实 Cycles 或风格化 EEVEE），镜头技法可选（嵌套世界：穿屏、键帽、书页进入另一个世界）。参考图 → Tripo / Blender 建模 → 绑骨手 K → 灯光 → timeline.json → 合成、配乐、接缝检查。Use for 3D short film / 3D animation / character reveal / product showcase / architectural walkthrough / 3D explainer / nested-world 3D transitions; triggers: opusv3d、3D 视频、3D 短片、3D 动画、3D 宣传片、角色出场、产品片、建筑漫游、3D 科普、3D 转场、穿屏、嵌套世界、推入、拉出、破屏、虹膜、高保真 3D、Tripo、绑骨、3d-video-manual, leo114119 sample.
---

# opusv3d

本 skill 做 3D 短片。选型分三步：**片种 → 画质 → 镜头技法**。三者互相独立，可以任意组合。

### 选型 1：片种（主角是什么）

先问自己：片子的主角是角色、产品、建筑、场景、一个要讲清楚的原理，还是一个故事？

| 片种 | 主角 | 主要工作 | 验证状态 |
|---|---|---|---|
| **角色出场** | IP 或原创角色 | 绑骨、手 K 表演、道具互动 | 已验证（30 s 角色出场片，成片，seamcheck 通过） |
| **产品展示** | 刚体产品，可带角色 | 材质、微距运镜、影棚光；拆解用 `anim.key` 手 K 零件位移；卖点标注用 `overlays`（固定在屏幕位置，不跟踪 3D 物体） | 部分验证（BANDAI 刀片：草稿第 10 版跑通，未出成片；无拆解镜头） |
| **建筑与空间** | 建筑、街区外景 | `arch.py` 的住宅构件（墙、窗、门、百叶、栏杆、四坡屋顶）；室内、楼梯、家具要用 `box`/`cyl` 自己搭；漫游镜头 | 部分验证（只验证过住宅外景，无室内，无漫游） |
| **场景氛围** | 场景本身，无主角 | 层次（前、中、远、天边）、镜头缓移、粒子 | 未验证 |
| **讲解可视化** | 机制、数据、流程 | 用 `shapes` 基础形体做 3D 图解、`visible` 分步显现、标签用 `overlays` 透明 PNG（RGBA；固定屏幕位置；中文要先在 PNG 里画好，或给 `shapes.text` 传 `font=`）、镜头引导叙事 | 未验证 |
| **微叙事** | 两个以上角色 | 分镜、表演、剪辑、字幕 | 未验证 |

每个片种要做哪些阶段（P1–P9），见 hifi.md 开头的"片种与阶段"表。**未验证和部分验证的片种**：先出 1 个镜头的静帧给用户确认，再往下做；把遇到的问题写回 hifi.md 第 2 节。

### 选型 2：画质

| 画质 | 引擎与 look | 读 |
|---|---|---|
| **写实** | `'film'` look：Cycles、AgX、物理天空、PBR 材质、自适应采样、降噪 | hifi.md P5、P7、P8 |
| **风格化** | 8 种 look（黏土、体素、低多边形、玻璃、纸、卡通、霓虹、微缩）：EEVEE，关键镜头可用 Cycles（`toon` 只能用 EEVEE） | [`references/generalize.md`](references/generalize.md) 第 1 节 |

任何片种都能选任何画质。**风格化 look 只作用于 `shapes`、`arch` 生成的物体和灯光。** Tripo 或 ARP 导入的角色、资产保留自带的 PBR 贴图材质，不会变成黏土或卡通（`rig.py`、`assets.py` 不读 look）。所以"风格化 + 角色"实际是风格化场景 + 原贴图角色；要让角色也风格化，得自己给导入网格重新指定 `w.mat()`。绑骨流程本身同 P6，没有代码阻碍。这个组合还没跑过完整片，先出静帧确认。

### 选型 3：镜头技法（可选）

**嵌套世界**：镜头在世界之间穿越（屏幕里是一个世界，屏幕在桌上，键帽里又是一个世界），用转场生成器连接。
它是一种镜头技法，不是片种：任何片种的某个节拍都可以用它（例如产品片里镜头穿过屏幕进入产品内部）。
用到时读 [`references/grammar.md`](references/grammar.md)（怎样设计）、[`references/transitions.md`](references/transitions.md)（生成器参数）、generalize.md 第 2 节（内容题材 → 世界链）。
不用时，转场只用 `cut`，淡入淡出用 `fade_in` `fade_out`。写实画质（`'film'` look）下不要用传送门：传送门按 Khronos 视图变换，在 film 世界里会被调色两次。

### 怎样选

1. 用户说了主角是什么 → 片种。没说清：问上面那一个问题。
2. 用户给了参考图或指定了质感 → 画质。没给：产品、建筑默认写实；讲解、场景氛围、微叙事默认风格化；角色出场：有 IP 官方资料或已有参考图时写实，否则风格化。
3. 用户提到"穿越""穿屏""转场"或要世界之间的连接 → 加嵌套世界技法。否则不加。
4. 选完把"片种 + 画质 + 技法"写在 PLAN.md（或 `01_ref/shotlist.md`）第一行，给用户确认。

目标：动作自然，画面有层次，每个关键节拍有记忆点，没有穿帮，没有多余镜头。**判定靠截图，不靠数字**（第 6 节）。

所有片种共用 timeline.json、film.py 命令、合成、混音、检查。嵌套世界的手法来自样片 `leo114119_video.mp4` 的反向拆解（[`references/teardown.md`](references/teardown.md)）。

分工：
- **Blender**（无头）建模、动画、渲染每个镜头。
- **timeline.json** 是唯一的时间来源：镜头、转场、节拍、标记。
- **compose.py** 合成后期转场和调色。**mix.py** 把声音事件变成音效和配乐。**seamcheck.py** 检查成片。

不修改 lemo-opuscar 的任何文件。只借用它的 Python 环境、`sfx.py`、`sheet.py` 和 `mux.sh`。

## 0. 准备

| 需要 | 检查 | 缺少时 |
|---|---|---|
| Blender 5.x（已测 5.2.1；引擎用 5.x 的几何节点接口，4.x 不能用） | `/Applications/Blender.app/Contents/MacOS/Blender --version` | 请用户安装；不要自己装系统软件。路径不同就设 `BLENDER=...` |
| lemo-opuscar 库和它的 `.venv`（numpy、scipy、pillow、soundfile） | `ls ~/lemo-opuscar/.venv/bin/python` | 用 Skill 调用 `lemo-opuscar:lemo-opuscar`，只做它的第 1、2 步（取库、`setup.sh deps`）。库不在默认位置就设 `LEMO_OPUSCAR_HOME=...` |
| ffmpeg | `ffmpeg -version` | 请用户安装 |
| 需要参考图的片种（除讲解可视化外基本都要）：Codex CLI（出参考图，对话模型 `gpt-6.1-sol`、推理 `high`，出图模型 `gpt-image-2`；`gptimg.sh` 默认就用它们） | `command -v codex` | 请用户安装并登录；或请用户在 ChatGPT 里出图，放进 `01_ref/p2/` |
| 角色出场、微叙事、带角色的产品片：Auto-Rig Pro 插件（只有绑骨那一步要） | `B -b --python-expr "import addon_utils; print([m.__name__ for m in addon_utils.modules() if 'auto_rig' in m.__name__])"` | 用 Mixamo（hifi.md P6） |
| 需要 Tripo 资产的片种（角色出场、微叙事、产品展示、场景氛围；建筑视情况）：Tripo 账号 | 问用户 | 多视角生成要付费订阅；免费版输出不能商用 |

开工前按选型读：所有片种读 [`references/hifi.md`](references/hifi.md) 的"片种与阶段"表和对应阶段；选了嵌套世界技法再读 grammar.md、transitions.md；风格化画质读 generalize.md 第 1 节。

## 1. 流程

嵌套世界技法的片子按下面第 1–8 步走。其他片种按 hifi.md 的 P1–P9 走（第 1 步换成 P1，第 4 步换成 P5–P7），第 2、3、5–8 步同下面。starter 是嵌套世界示例；其他片种用 `new.sh --blank`。

1. **定方案。** 按 grammar.md 写出世界链、主角、维度梯子、转场序列和音乐起伏。题材对照 generalize.md 的表。
   方案写在项目的 `PLAN.md` 里（10–20 行），给用户确认后再建模。进度写在 `PROGRESS.md` 里（第 5 节规则 11）。
2. **建项目。** `sh <本 skill 目录>/scripts/new.sh [--blank] <项目目录>`。默认复制 starter（一部 22 s 的嵌套世界示例片）和一份冻结的引擎。**非嵌套世界片种加 `--blank`**：film.py、timeline.json 换成空骨架（一个世界、一个镜头、一个方块，24 fps），其余文件相同。mix.py 仍是 starter 的，里面的 SCORE、QUIET 是示例，按片子改。
   项目目录默认放在用户当前目录下，名字用小写字母、数字和连字符。
3. **写 timeline.json。** 镜头、转场、标记、节拍。然后运行 `plan`，它检查时间线并打印每个镜头的渲染范围。
4. **写 film.py。** 每个世界一段：物体、生成器、主角表演、相机。starter 的 film.py 是完整示例，在它上面改。
5. **出静帧。** `stills --draft`，再 `compose.py . --draft --stills` 生成调色后的联系表 `out/draft/stills/sheet.jpg`。按第 6.1 节审阅：构图、look、层次；嵌套世界：主角是否是唯一暖色；其他片种：是否贴合参考图配色。
6. **草稿成片。** `sh build.sh --draft`（960×540，8 采样，约 0.1 s/帧）。看 seamcheck 结果，再按第 6.1 节审阅：关键帧、快速动作的连续帧条、转场前中后。
7. **改到通过。** 改 timeline.json / film.py / mix.py，重复第 6 步。渲染可续跑；改了 film.py、引擎或 timeline.json 里影响画面的字段会整片重渲（见第 3 节末尾）。
8. **正式成片。** 先渲 3–5 张成片质量的关键帧，主动发给用户，用户确认后再跑 `sh build.sh`（1920×1080，EEVEE 64 采样，约 1.2–1.3 s/帧；写实画质用 Cycles，每帧 10–25 s，估时见 hifi.md P8）。按第 6 节验收。

## 2. 命令

在项目目录里运行。`B` = Blender 路径，`PY` = `$LIB/.venv/bin/python`。

| 命令 | 作用 |
|---|---|
| `B -b --factory-startup --python-exit-code 1 -P film.py -- plan` | 检查时间线，打印镜头、渲染范围、渲染顺序、帧数。不渲染 |
| `... -- stills [--draft] [--shots s1,s4] [--at 1.5,bar:3]` | 每个镜头渲几张静帧（或指定时刻）到 `out/<q>/stills/` |
| `... -- render [--draft] [--shots ...]` | 渲染镜头帧到 `out/<q>/shots/<id>/#####.jpg`，可续跑 |
| `... -- export [--draft]` | 只写 `render.json`、`anchors.json`、`out/events.json` |
| `... -- blend [--draft]` | 保存 `out/<q>/film.blend`，用 Blender 界面检查 |
| `PY engine/compose.py . [--draft] [--stills]` | 合成成片 `out/<q>/video.mp4`（无声）；`--stills` 只做静帧联系表 |
| `PY mix.py .` | 声音事件 + 配乐 → `out/mix.wav` |
| `PY engine/seamcheck.py . out/<q>/film.mp4 [--draft]` | 检查成片，失败时退出码 1 |
| `sh build.sh [--draft]` | 以上全部：渲染 → 合成 → 混音 → 封装（−14 LUFS）→ 检查 |
| `PY engine/review.py strip <film.mp4 或帧目录> out.jpg <起> <止> [--box x,y,w,h]` | 连续帧条：每帧一格，标帧号和秒数，可裁到主体 |
| `PY engine/review.py pick <film.mp4 或帧目录> out.jpg f362,14.6,@jump` | 指定帧的联系表：关键姿势、数值检查报出的帧 |
| `B -b out/<q>/film.blend --python-exit-code 1 -P engine/motioncheck.py -- <起> <止> <部位> ...` | 速度曲线：报急停、匀速、抖动、同时达峰（hifi.md P6） |
| `PY engine/review.py curves out/<q>/motion.json out.png` | 把速度曲线画成图 |
| `PY $LIB/core/render/sheet.py out.jpg a.jpg b.jpg ... --cols 3 --w 480` | 任意图片拼成联系表 |

**`--python-exit-code 1` 必须写。** 没有它，Python 报错时 Blender 仍然返回 0，脚本会继续往下跑。

## 3. timeline.json

```json
{"name": "my-film", "fps": 30, "size": [1920, 1080], "bpm": 120, "dur": 22.0,
 "fade_in": 0, "fade_out": 0.8, "allow_dark": [[0, 1.0]],
 "marks": {"out": "beat:10", "breach": "beat:18"},
 "shots": [
   {"id": "s1", "world": "SCREEN"},
   {"id": "s2", "world": "DESK", "in": {"type": "pull_out", "t": "@out", "dur": 1.5, "surface": "mon.screen"}},
   {"id": "s3", "world": "DESK", "in": {"type": "breach", "t": "@breach", "anchor": "screen_hero"}}]}
```

| 字段 | 默认 | 说明 |
|---|---|---|
| `fps` | 30 | 交付要 60 fps 时改成 60（渲染时间翻倍） |
| `size` | [1920, 1080] | 必须是偶数 |
| `bpm` `meter` `music_offset` | — / 4 / 0 | 用 `bar:N`、`beat:N` 时必填 `bpm` |
| `dur` | 必填 | 全片秒数 |
| `fade_in` `fade_out` | 0 | 开头、结尾黑场渐变秒数 |
| `allow_dark` | [] | 允许暗画面的时间段（冷开场）；seamcheck 不在这里报黑帧和冻结 |
| `post` | {} | 全片调色覆盖（`bloom` `thr` `vig` `con` `sat` `tilt` `warm`） |
| `marks` | {} | 命名时刻，后面可用 `@名字`；可以引用前面的标记 |
| `shots[].id` `world` | 必填 | 镜头 id（只用字母、数字、`_`、`-`，它是输出目录名）；世界名（film.py 里 `film.world('名字')`） |
| `shots[].engine` | look 的引擎 | `"cycles"`：这个镜头用 Cycles（关键镜头） |
| `shots[].anchor` | `hero` | 这个镜头的锚点物体 |
| `shots[].in` | 第一个镜头不能有；其余必填 | 转场，字段见 transitions.md §1。写错的选项名、不在范围内的值会直接报错 |
| `overlays` | [] | 片名、字幕图片：`[{"image": "01_ref/title.png", "t": "@title", "until": 29, "x": 0.5, "y": 0.15, "w": 0.56, "in": 1.6, "reveal": "write", "sfx": "..."}]`。`image`（RGBA PNG，相对项目目录；没有透明通道会变成不透明方块；位置固定在屏幕上，不跟踪 3D 物体）和 `t`（开始时刻）必填；`until` 默认到片尾；`x` `y` 是图片中心、`w` 是宽度，都是画面的比例（0–1）；`in` 是出现用的秒数（0–60）；`reveal` 是 `write`（从左到右写出）、`stamp`（盖章）或 `fade`（默认）；`sfx` 由 mix.py 读取。`plan` 时检查字段，写错直接报错 |

时间写法：`12.5`、`"bar:5"`、`"beat:9.5"`、`"@mark"`，都可以加减秒（`"bar:5-0.25"`）。
每个镜头从它的 `in.t` 开始，到下一个镜头的 `in.t` 结束。

只影响合成和检查的字段（`name` `post` `fade_in` `fade_out` `allow_dark` `overlays`，以及 iris / lens / breach 的画面选项）改了不会重渲镜头；
`sh build.sh` 会跳过已渲染的帧，只重新合成。

## 4. film.py 骨架

```python
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'engine'))
from v3d import *
from v3d import shapes as S

film = Film(__file__)
T = film.T                                   # 时间写法 -> 秒

W = film.world('DESK', look='clay')          # 一个世界 = 一个 Blender 场景
mon, scr = S.monitor(W, 'mon', width=1.0)    # 物体全名 DESK.mon、DESK.mon.screen
H = S.hero(W, 'hero', size=0.1)
hops(H, 3.0, [(0, 0, 0), (0.2, 0, 0)])
c = W.camera('s2', lens=35)                  # 镜头 s2 的相机：DESK.cam.s2
camera.path(c, [(0, (1, -2, 1), (0, 0, .4)), (4, (.6, -1.5, .8), (0, 0, .4), 'smooth')])
film.portal(scr, 's1', since=0, until=6)     # 屏幕显示镜头 s1 的画面

film.run()
```

- 物体命名 `<世界>.<名字>`。timeline.json 和生成器参数里只写世界内的短名（`mon.screen`）。
- 现成形体（`shapes`）：`box` `sphere` `cyl` `plane` `disc` `text` `monitor` `keyboard` `hero` `hero_piece` `cube_piece` `blade_piece` `pixels` `tree_cells` `voxelize`。
- 生成器和表演函数的参数见 transitions.md §4。

## 5. 规则

规则 1、2、5、9 只在用嵌套世界技法（传送门、转场生成器）时适用；规则 3 的前半句（push_in / pull_out 相机）同理，后半句（`focus_object` 跟住头部）通用。规则 6 的"唯一暖色"只属于嵌套世界样片；其他片种的配色由参考图决定。其余规则所有片种通用。

1. **传送门表面是平面**，法线是局部 +Z，最好是 16:9。不是平面会报错。表面在转场期间不能移动。
2. **一个表面只显示一个镜头。** 别的时间段也要显示时，调用 `film.portal(surface, shot, since, until)`。
3. **相机只用 `w.camera(...)` 创建，不设父物体。** 做 `push_in` / `pull_out` 转场的相机，景深用 `dof.focus_distance`，不用 `focus_object`（会报错）；其他镜头可以用 `focus_object` 跟住角色头部（hifi.md P7）。
4. **同一个项目不要同时跑两个渲染。** 两个进程会写同一批帧文件。
5. **静帧里传送门显示品红色**，表示源镜头还没渲染。先渲染源镜头（`plan` 打印的顺序），或者不管它。
6. **不用真实品牌的吉祥物和标识**（所有片种；IP 角色见 hifi.md 第 3 节授权）。嵌套世界样片另有约定：主角是唯一暖色，默认主角是黄色圆角方块加两个点状眼睛。
7. **每个可见动作都有声音。** 生成器自动发声音事件。自己加的动作调用 `emit(t, 'kind')`。mix.py 对没有音效的事件种类会打印警告，不会静默丢掉。
8. **时间只写在 timeline.json 的标记里，或者用 `T('@mark')` 引用。** 改节奏时只改一个地方。
9. **锚点对位（`match` 为 true，iris / lens / breach 的默认值）时，两边的锚点物体必须存在，否则报错。** 想用画面中心，就写 `"match": false`；seamcheck 会给出 `WARN anchor_missing`。
10. **`visible()` 只控制渲染可见性。** 物体在视口里保持可见，这样锚点测量和 `film.through()` 能拿到正确位置。不要自己关 `hide_viewport`。
11. **状态写在项目目录里。** 会话会被压缩，临时目录会被清理。`PROGRESS.md` 记：当前阶段、用户的决定（原话）、已知问题、下一步。
    检查脚本放项目的 `checks/`，不放临时目录。每次用户做了决定、每个阶段结束，都更新 PROGRESS.md。
12. **用完的物件要隐藏。** 道具、特效、碎片等物件在剧情里用完后，用 `visible(obj, [(t0, t1)])` 只在需要的时间段显示。
    画面里只能出现方案列出的物件（有分镜表的片种：分镜表；嵌套世界：PLAN.md）。

## 6. 审阅与验收

数字检查是必要条件，不是充分条件。数字合理的画面，可能看起来很怪。实测（第一部实片）：
- 数值最优的道具角度，用户一看就说"很奇怪"。
- 检测报了手臂穿进身体，被判为噪声；成片里手臂断在身体里。
- 每 30 帧抽一张的联系表，漏掉了一个用完后悬在空中的物件。
- 11 个画面问题都是用户先发现的。

**画面是最后的判定。** 数字和画面冲突时，以画面为准。数字报了问题，必须看那一帧的成片画面。

### 6.1 截图审阅

| 什么时候 | 做什么 |
|---|---|
| 改了影响画面的东西 | 渲受影响的关键帧，自己先看 |
| 预计超过 10 分钟的渲染之前（正式渲染；长片的整片草稿） | 先把截图发给用户，用户确认后再跑 |
| 每个阶段结束 | 主动发联系表和一句结论，不等用户问 |

看哪些帧：
- 关键姿势帧：接触、起跳、最高点、落地、握住、亮相、片名。
- 快速动作：`review.py strip` 每帧一格。不能抽样，问题常在两个关键帧之间。
- 数值检查报出的每一帧：`review.py pick`。
- 转场的前、中、后。
- 参考图对应的画面，和参考图并排。

怎样看：
- 用镜头相机和成片的 look（`stills`、草稿或成片）。工作台渲染、点图只用来找原因，不用来判定。
- 裁到主体（`--box`）：主体至少占格子高度的一半。一张联系表不超过 2000 px（review.py 自动分页），否则看图工具会缩小它。
- 每格先写一句"看到了什么"，再写判断。不能只写"正常"。
- 用两种眼光各看一遍：
  - **缺陷**：穿模、断肢、翻面、悬空、出画、多余物件、闪烁、品红。
  - **观感**：动作自然吗、僵吗、节奏对吗、画面有层次吗、这个节拍有记忆点吗（hifi.md P5–P7 的清单，grammar.md 第 8 节）。
- 静帧看不出僵硬和节奏。动作段另看速度曲线（`motioncheck.py`），曲线报的帧再用连续帧条看。

**盲审**：每个出图的阶段结束时（P2、P5–P8；嵌套世界技法：第 5、6、8 步），派一个独立子 Agent 审图。
- 输入：参考图、分镜表、联系表、连续帧条。不给数字，不给设计意图，不给搭建过程。
- 输出：每条写帧号、位置、问题、严重度（高/中/低）。只列问题，不写评价。
- 通过：高级问题 = 0。中级问题逐条修复，或向用户说明为什么不修。最多 5 轮；5 轮后还有高级问题，交给用户决定。

### 6.2 验收

宣称完成之前，下面每一项都要实际运行并附上输出：

| 项 | 方法 | 通过标准 |
|---|---|---|
| 接缝与锚点 | `seamcheck.py`（build.sh 最后一步） | 0 failure：帧数、push/pull 接缝、单帧跳变、锚点误差 ≤ 0.01、黑帧 |
| 响度 | mux.sh 输出 | I ≈ −14 LUFS，峰值 < −1 dBFS |
| 转场画面（用了转场时） | 用 ffmpeg 抽每个转场前、中、后的帧，`sheet.py` 拼联系表，用眼睛看 | 主角大小、位置在转场两边连续；没有穿模、品红传送门、空白帧 |
| 整片节奏 | 每秒抽 1 帧的联系表 | 每个镜头都能读懂；嵌套世界：维度梯子走回去一次 |
| 动作段 | `review.py strip` 每帧一格 + `motioncheck.py` | 每个 jolt、jitter、glide、sync 都看过连续帧条，有结论 |
| 盲审 | 第 6.1 节 | 高级问题 = 0 |

seamcheck 跳过后期转场窗口内的单帧跳变检查（扫过的边缘本来就是跳变）。这些窗口必须用联系表看。
单帧跳变检查只抓“和前后两帧都不像”的帧（静止画面里的跳帧、闪白）。快速但平滑的镜头运动不报。
它抓不到运动中的跳帧、漏帧和“定格后突然跳走”。所以快速运动段也要用联系表看。

## 7. 文件

| 路径 | 内容 |
|---|---|
| `scripts/new.sh` | 新建项目（`--blank`：空骨架） |
| `scripts/gptimg.sh` | 用 Codex CLI 出一张参考图到 `01_ref/p2/`（高保真 P2） |
| `templates/blank/` | 空骨架：film.py、timeline.json（`new.sh --blank` 用） |
| `templates/starter/` | 示例片：timeline.json、film.py、mix.py、build.sh。用到 assemble、scatter、lift、grow、hop、hops、drop、blink 和 6 种转场（cut、pull_out、push_in、breach、lens、iris）；没有用 fade、pop、move |
| `engine/v3d/` | 引擎：`core`（Film、World、渲染）、`timeline`、`transitions`（生成器）、`anim`（关键帧、表演）、`camera`、`shapes`、`geo`（几何节点）、`looks`（含高保真 `'film'`）、`arch`（建筑）、`materials`（程序化 PBR）、`assets`（Tripo 资产）、`rig`（ARP 角色的姿势、动作、插座） |
| `engine/compose.py` `engine/seamcheck.py` | 合成（含 `overlays` 片名）、检查 |
| `engine/review.py` `engine/motioncheck.py` | 截图审阅：连续帧条、指定帧、速度曲线（都不进渲染签名） |
| `templates/starter/PROGRESS.md` | 进度文件模板（new.sh 复制） |
| `engine/assettool.py` `engine/arptool.py` | 资产检查、Mixamo 上传准备；ARP 绑骨和姿势测试（都不进渲染签名） |
| `references/hifi.md` | 阶段手册 P1–P9（所有片种共用）：片种与阶段表、出图 brief、Tripo 设置、绑骨、道具互动、最坏情况 |
| `references/teardown.md` | 样片拆解（证据） |
| `references/grammar.md` | 嵌套世界技法的设计语法（节拍与记忆点清单第 8 节所有片种通用） |
| `references/transitions.md` | 生成器目录与参数 |
| `references/generalize.md` | 8 种风格化 look；嵌套世界技法的 6 类题材世界链 |
