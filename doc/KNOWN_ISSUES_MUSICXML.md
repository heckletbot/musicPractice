# MusicXML 转换 — 已知遗留问题

范围：`music_practice.score`（`convert_musicxml` / `parse_musicxml`）。  
已处理项（和弦同起音、去掉调用方 tempo 参数、multiple-rest 按「小节时长 × N」）见 [GUIDE_MUSICXML.md](./GUIDE_MUSICXML.md)。

---

## 遗留：速度记号的 `<offset>`（待评估）

### 现状

解析到 `<direction>` 中的 metronome / `sound/@tempo` 时，**立即**更新当前 BPM，用于后续音符与休止的秒轴累加。

### 问题

MusicXML 允许在 `direction` 上写 `<offset>`（单位：divisions）。部分导出软件（常见于 Sibelius）会：

- 把速度记号的 XML **写在小节开头**；
- 同时带上接近整小节的 `offset`，表示「发声/生效点在**该小节靠后**」。

若忽略 `offset`、一见到记号就改速，可能把该小节前半段（含休止）错误地按新速度换算，时间轴被拉偏。

### 产品侧假设（当前）

跟谱曲库通常可视为：**出现速度记号的小节起即按新速度**；不依赖 `offset`。在未验证导出是否含非零 `offset` 前，**主转换不实现延迟改速**。

### 建议后续

1. 抽查交付/曲库 MusicXML：是否存在非零 `<offset>` 的 tempo `direction`。
2. 若有：在解析侧按「当前 divisions 游标 + offset」处再生效（可参考 `start_match.score.parser` 的 pending tempo 思路），并补单测。
3. 若无：将本条标为「不适用」并关闭。

### 涉及代码

- [`src/music_practice/score/parser.py`](../src/music_practice/score/parser.py) — `direction` 分支立刻 `ctx.tempo_bpm = tempo`
- 对照（已实现 offset）：[`src/music_practice/start_match/score/parser.py`](../src/music_practice/start_match/score/parser.py)

---

## 暂不处理：`backup` / `forward` 与秒游标不同步

### 现状

`<backup>` / `<forward>` 只移动 `current_div`（拍位游标），**不**同步调整 `current_time`（绝对秒）。

### 影响

多声部、对位或「写完再回退写另一声部」的谱面，可能出现 `beat` 与 `onset` 不一致，或秒轴被重复累加。

### 为何暂不修

交付约定为**单声部、线性写出**的跟谱谱面，一般不出现 backup。在扩大多声部支持前不做改动。

### 若以后要修

`backup`/`forward` 应按 divisions 与当前 `sec_per_quarter` 同时回退/前进秒游标（注意中途变速时的分段）。

---

## 修订记录

| 日期 | 说明 |
|------|------|
| 2026-08-02 | 初版：登记 tempo `<offset>` 为遗留；`backup`/`forward` 暂不处理 |
