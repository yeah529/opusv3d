# 风格化 look 与嵌套世界的内容题材

第 1 节（8 种 look）适用于所有片种的风格化画质。第 2–4 节只适用于选了嵌套世界技法的片子。
样片是"程序员桌面"这一种题材。第 2 节说明怎样把嵌套世界手法用到别的题材上。
方法不变：世界链 + 唯一暖色主角 + 维度梯子 + 有来由的转场 + 音乐跟尺度走（见 grammar.md）。

## 1. 风格（look）

每个世界选一个 look：`film.world('NAME', look='clay')`。look 决定天空、灯光、材质、倒角和后期调色。
同一部片子里，不同世界用不同 look，观众更容易分清"现在在哪一层"。

| look | 画面 | 适合 | 已知限制 |
|---|---|---|---|
| `clay` | 哑光黏土，暖色日光，柔和阴影 | 桌面、室内、产品台 | 和 voxel、miniature 相邻时区别小，要靠场景内容区分 |
| `voxel` | 体素方块，蓝天，清晰阴影 | 游戏、像素主题 | 同上 |
| `lowpoly` | 平面着色，低面数 | 地图、风景、信息图 | 曲面物体（球、主角）会显出棱角，这是有意的 |
| `glass` | 深色背景，透明折射，强辉光 | 科技、芯片、数据 | `body` 也变透明：黄色主角变成暗色玻璃，失去唯一暖色。主角改用 `kind='emit'` 或放在别的世界；EEVEE 折射是近似效果，关键镜头改用 Cycles |
| `paper` | 哑光，无辉光，暖偏色 | 故事、儿童、手账 | 样张中纸张纹理几乎看不出；`glass` 类物体变形，看起来不对。这个世界里不用 `glass`，先出静帧确认 |
| `toon` | 卡通着色加描边 | 动画、IP、儿童 | 描边宽度 = 0.015 × 物体最大边长（最小按 0.2 计）；很小的物体描边偏粗 |
| `neon` | 黑底，霓虹自发光，强辉光 | 屏幕内、终端、赛博 | 画面暗，冷开场要在 timeline.json 写 `allow_dark` |
| `miniature` | 移轴模糊，高饱和 | 微缩世界、城市、岛屿 | 移轴在 compose 里做；画面中心要放主体 |

材质类型（`kind`）：`body` 主体、`ground` 地面、`accent` 强调、`glass` 玻璃、`emit` 发光、`screen` 屏幕、`dark` 深色、`metal` 金属。
一个世界可以用 `post={...}` 覆盖调色（`bloom` `thr` `vig` `con` `sat` `tilt` `warm`）。

## 2. 内容类型 → 世界链

每一行是一条起步方案。改名字、改物体，结构不改。

| 内容类型 | 世界链 | 主角 | 传送门表面 | 转场序列 | look |
|---|---|---|---|---|---|
| 产品发布 | `SCREEN`（官网页面）→ `STAGE`（产品在展台上）→ `INSIDE`（爆炸图，零件变城市）→ `STAGE` | 产品图标 | 屏幕 → 产品顶面 | pull_out → lens → push_in（顶面）→ iris close（微缩产品） | neon → clay → glass → clay |
| 知识科普 | `BOOK`（书页插图）→ `LAB`（桌上的模型）→ `MICRO`（细胞 / 芯片内部）→ `LAB` | 一个"粒子"角色 | 书页插图框 → 显微镜目镜 | pull_out（插图）→ push_in（目镜）→ grow（结构长出）→ iris close | paper → clay → glass → clay |
| 品牌 / IP | `LOGO`（像素 logo）→ `SHELF`（包装在货架上）→ `WORLD`（IP 世界）→ `SHELF` | 品牌吉祥物（自有版权） | 包装正面 | assemble（logo）→ lift → breach（冲出包装）→ push_in → iris close | neon → clay → toon → clay |
| 数据故事 | `CHART`（屏幕上的柱状图）→ `CITY`（柱子变高楼）→ `ROOM`（一扇窗里的人）→ `CHART` | 一个数据点（小球） | 屏幕 → 窗户 | grow（柱子）→ pull_out → push_in（窗）→ iris close | neon → lowpoly → clay → neon |
| 旅行 / 城市 | `MAP`（地图上的图钉）→ `TOWN`（微缩城市）→ `STREET`（街景）→ `MAP` | 图钉 / 小行李箱 | 地图格子 → 明信片 | push_in（地图格）→ lens → iris open（明信片）→ pull_out | paper → miniature → clay → paper |
| 游戏 / App | `PHONE`（App 图标）→ `LEVEL`（关卡）→ `BOSS`（巨型角色）→ `PHONE` | 游戏角色 | 手机屏幕 → 关卡里的传送门 | assemble（图标）→ lift → push_in → scatter + assemble（巨人）→ iris close | neon → voxel → voxel → clay |

## 3. 改编步骤

1. 选一行内容类型，写出世界链（3–5 层，至少回到一层旧世界）。
2. 给每个世界选 look，相邻世界的 look 要不同。
3. 给每次转场找"来由"：哪个表面、哪个动作。写进 timeline.json 的 `"in"`。
4. 决定主角：唯一暖色，每个世界一个实例（尺寸跟着世界尺度变）。
5. 列出维度梯子用到的生成器（assemble、lift、grow、scatter），每个世界内至少一个。
6. 写 mix.py 的 `SCORE`（每个世界一个音色）和 `QUIET`（大事件前的静音）。
7. 先出静帧（`stills --draft` + `compose --stills`），确认构图和 look，再渲染。

## 4. 不适合的题材

- 需要写实人物、写实表情的内容。嵌套世界样片的主角只能是简单几何角色；要角色表演，选"角色出场"或"微叙事"片种（hifi.md P6）。
- 需要真实品牌标识的内容。只用自有或已授权的素材。
- 需要真实地图数据、真实建筑的内容。引擎只做程序化的风格化物体。
- 时长超过 90 s。镜头和世界变多后，渲染时间和时间线复杂度都快速增长；建议拆成多部。
