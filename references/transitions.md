# 转场生成器目录

opusv3d 的转场分 3 层。每一层都是代码生成器：给参数，它生成动画、合成和声音事件。时间全部自由（秒、`bar:N`、`beat:N`、`@mark`，可加减秒）。

| 层 | 写在哪里 | 生成器 | 谁执行 |
|---|---|---|---|
| 世界内 | film.py（Python 调用） | `assemble` `scatter` `lift` `grow` `pop` `move`，表演 `hop` `hops` `drop` `blink` | Blender（几何节点 + 关键帧） |
| 穿越世界 | timeline.json 的 `"in"` | `push_in` `pull_out` | Blender（相机烘焙 + 传送门贴图） |
| 后期 | timeline.json 的 `"in"` | `cut` `fade` `iris` `lens` `breach` | compose.py（两个镜头的帧合成） |

## 1. timeline.json 里的转场

每个镜头（除第一个）有一个 `"in"`，说明"怎样进入这个镜头"。

```json
{"id": "s5", "world": "MEADOW",
 "in": {"type": "push_in", "t": "bar:7", "dur": 1.4, "surface": "kb.glass.top"}}
```

| 字段 | 默认 | 说明 |
|---|---|---|
| `type` | `cut` | 转场类型 |
| `t` | 必填 | 切换时刻。push_in：此刻表面充满画面。pull_out：此刻从表面开始拉出。后期类：窗口中心 |
| `dur` | push/pull 1.5，iris 0.5，lens/breach 0.8，fade 0.5，cut 0 | 时长（秒） |
| `anchor` | 两个镜头的 `anchor`（默认 `hero`） | 锚点物体名；字符串表示两边同名，或 `[A 边, B 边]` |
| `match` | iris/breach/lens 为 true | 锚点对位：转场窗口内平移 B 相机的镜头偏移。为 true 时两边的锚点物体必须存在，否则报错；为 false 时找不到锚点就用画面中心 |
| `settle` | 1.0 | 对位后 B 相机回到原构图用的秒数 |
| `surface` | push/pull 必填 | 传送门表面的物体名（外层世界内的短名） |
| `seam` | 2 | push/pull 切换点交叉淡化的帧数 |
| 其他键 | — | 传给该生成器的选项（下表） |

**窗口：** push_in 是 `[t−dur, t]`；pull_out 是 `[t, t+dur]`；后期类是 `[t−dur/2, t+dur/2]`。
窗口必须在相邻两个镜头内，两个窗口不能重叠。`plan` 命令会检查。

## 2. 穿越世界：push_in / pull_out

外层世界的相机沿"对数距离 + 方向球面插值"移动到表面的**覆盖位姿**：此时表面的 16:9 区域正好充满画面。表面上贴着内层镜头的实时帧，所以切换是无缝的。

| 选项 | 默认 | 说明 |
|---|---|---|
| `ease` | `inout` | 位置缓动。两端速度为 0，所以切换帧没有运动模糊 |
| `fade` | push_in 为 `0.45×dur`，pull_out 为 0 | push_in 开始时表面从透明淡入到内层画面的秒数；下潜结束后表面恢复透明 |

规则：
- 表面必须是平面网格，法线是局部 +Z，最好是 16:9（`shapes.plane`、`shapes.monitor` 的 `.screen`、`shapes.keyboard` 的 `.glass.top`）。不是平面网格（例如空物体、立方体）会报错。
- 表面的朝向：`shapes.plane(w, name, (宽, 高), loc)` 默认水平朝上，画面的上方是世界 +Y（用于键帽顶、桌面、水面）。竖立、面向 −Y 方向相机的屏幕写 `rot=(90, 0, 0)`，画面的上方是 +Z（`shapes.monitor` 就是这样做的）。
- 一个表面只显示一个镜头。要在别的时间也显示它，调用 `film.portal(surface, '镜头id', since=, until=)`。超出渲染范围时，表面停在首帧或末帧。
- 表面在转场期间不能移动。
- 相机景深用 `dof.focus_distance`（引擎会改写它）。用 `focus_object` 会报错。
- push_in 结束后，外层相机在覆盖位姿停 1 s。

声音：push_in 发 `riser`（全程）和 `whoosh`（切换点）；pull_out 发 `whoosh` 和 `swell`。

## 3. 后期转场

| 类型 | 选项（默认） | 画面 | 声音事件 |
|---|---|---|---|
| `cut` | — | 在 `t` 硬切 | `hit` |
| `fade` | — | 交叉淡化 | `swell` |
| `iris` | `mode` open/close（open，其他值报错）；`feather` 0.006；`rim` 0.35 | open：B 从锚点处的圆里长出来；close：A 缩进锚点处的圆，外面是 B | `iris` |
| `lens` | `radius` 0.75（×画面高）；`mag` 0.3；`dir` ltr/rtl（ltr，其他值报错） | 折射透镜泡横扫，泡后留下 B；带色散和亮边 | `lens` |
| `breach` | `wavelength` 0.07；`amp` 0.014（×画面高） | 从锚点扩散的涟漪环，环内是 B | `ripple` |

- 圆心和涟漪中心取锚点：从 A 边的位置插值到 B 边的位置（对位后两者相同）。
- 锚点数据写在 `out/<q>/anchors.json`。seamcheck 检查对位误差 ≤ 0.01（NDC）。

## 4. 世界内生成器（film.py）

所有生成器都返回 Blender 物体（`lift` 返回两个）。位置是世界坐标。`piece` 是隐藏集合里的零件（`shapes.cube_piece`、`shapes.hero_piece` 或任何网格）。`colors` 是 `'#rrggbb'` 列表（每个零件一个）；零件材质必须读实例属性 `col` 才会按零件着色（`cube_piece`、`hero_piece` 已经这样做）。`shapes.blade_piece` 是给 `geo.scatter` 铺草用的单色零件，不读 `col`。

### assemble — 零件飞进目标格子
```python
assemble(w, name, piece, cells, t0, dur, colors=None, start='scatter', spread=4.0, point=None,
         stagger=0.6, order='random', arc=0.0, spin=1.0, scale=1.0, start_scale=None,
         ease='smoother', seed=0, until=None, sound='sparkle')
```
- `start`：`scatter`（随机偏移 `spread`）、`point`（全部从 `point` 长出）、`below` / `above`、或一个起点列表（例如分身落地的位置）。
- `stagger`：起飞时间铺开到 `dur` 的多少比例。`order`：`random`、`x`/`-x`/`y`/`z`/`-z`、`dist`（离 `point` 或中心的距离）、或 0..1 列表。
- `arc`：飞行弧高。`scale` 可以是 `(x, y, z)`（像素平板用 `(cell, 0.12*cell, cell)`）。`until`：此后隐藏。
- 声音：`whoosh` + 一串 `sparkle` + 结尾 `click`。

### scatter — 零件离开格子
```python
scatter(w, name, piece, cells, t0, dur, colors=None, to='fall', ground=0.0, spread=3.0, targets=None,
        stagger=0.4, order='random', scale=1.0, end_scale=None, spin=1.0, seed=0, since=None, until=None,
        sound='thump', ease=None)
```
- `to`：`fall`（重力落到 `ground`）、`burst`（从中心炸开并缩小）；或给 `targets` 列表（缓动默认 `smoother`，落地用 `ease='gravity'`）。
- 声音：落地处的 `thump`（最多 8 个）。

### lift — 维度梯子：像素 → 体素 → 平滑
```python
vox, melt = lift(w, name, piece, cells, t0, dur, colors=None, cell=1.0, plate=0.12, axis=(0, -1, 0),
                 then=None, melt=0.35, order='dist', seed=0, since=None, sound='riser')
```
- `cells` 是平板中心（和前面 `assemble` 的目标相同）。平板沿 `axis` 挤出成立方体，背面不动。
- 给了 `then`（一个物体）：最后 `melt` 比例的时间里体素缩没，`then` 带回弹地弹出。
- 声音：`riser`，融化时 `pop`。

### grow — 从种子长出来
```python
grow(w, name, piece, cells, t0, dur, colors=None, seed_point=None, order='z', stagger=0.85, scale=1.0,
     rise=0.0, sound='pop', seed=0)
```
树（`shapes.tree_cells`）、城市、晶体。`order='z'` 从下往上，`'dist'` 从 `seed_point` 向外。

### pop / move
- `pop(ob, t, dur=0.35, start=0.0, sound=None)`：物体带回弹放大出现（之前隐藏）。
- `move(w, name, piece, pa, pb, t0s, durs, colors, sa, sb, ra, rb, arc, ease, show)`：最底层，逐个零件给起点和终点。

### 表演
- `hop(ob, t0, t1, p0, p1, height=0.6, squash=0.18)`：蓄力、腾空拉伸、落地压扁（0.1 s 起压，不会一帧跳变）、回弹。
- `hops(ob, t0, points, dt=0.45, gap=0.12, height=0.5, sound='step')`：连跳，每次落地发 `step`。返回最后落地时刻。
- `drop(ob, t0, t1, p0, p1, squash=0.22, sound='thump')`：重力下落加落地压扁。
- `blink([eyeL, eyeR], t)`：眨眼。
- `key(ob, path, [(t, value[, ease])])`、`bake(ob, path, t0, t1, fn)`：任何属性的逐帧关键帧。
- `visible(ob, [(t0, t1), ...])`：只在这些窗口内渲染（只控制 `hide_render`；视口里仍可见，这样位置测量不失效）。
- `emit(t, kind, gain=1.0, pan=0.0, dur=0.0)`：自己加声音事件。

### 辅助
- `film.through(surface, '镜头id', 物体或点, t)`：内层物体在 t 时刻出现在外层表面上的世界坐标。用来放 breach 的锚点。
- `World.instance(name, collection, loc, scale)`：在一个世界里放另一个世界的集合（微缩版）。动画、几何节点照常工作。
- `shapes.pixels(rows, palette, cell)`：ASCII 像素画 → 格子。`shapes.voxelize(w, ob, step)`：封闭网格 → 体素格子。

## 5. 常用配方

| 想要 | 写法 |
|---|---|
| 光标吐出图标 | `assemble(start='point', point=光标位置, order='dist', scale=平板)` → `lift(then=主角)` |
| Logo 拼出来 | `shapes.voxelize` 或 `shapes.pixels` 得到格子 → `assemble(start='scatter', order='random')` |
| 数据柱长出来 | 每根柱子一列格子 → `grow(order='z')` |
| 分身变巨人 | `scatter(targets=地面点, ease='gravity')` → `assemble(start=地面点列表, order='z', arc=1.5)` |
| 结尾回到微缩版 | 外层 `World.instance(内层集合)` + 空物体锚点 → `iris` `mode: close` |
| 主角穿出屏幕 | `film.through(screen, 内层镜头, 内层主角, t)` → 外层空物体 `screen_hero` → `breach` `anchor: screen_hero` |

## 6. 常见坑

- 生成器的物体放在世界的根集合。要被另一个世界实例化，自己把它们移进子集合（starter 的 `into()`）。
- `lift` 的 `cells` 要和前一步 `assemble` 的目标完全相同，`scale` 用 `(cell, plate*cell, cell)`，否则交接时会跳一下。
- 两个世界转场时，锚点在画面上相距太远，B 相机偏移很大，回位时像摇镜。改构图，或设 `"match": false`。
- seamcheck 的 `glitch` 检查会跳过后期转场窗口（扫过的边缘本来就是跳变）。这些窗口要用眼睛看帧条。
