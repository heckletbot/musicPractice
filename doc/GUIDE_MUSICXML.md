# MusicXML 转换使用指南

本模块**单独使用**：把 MusicXML 转成固定格式的 `ScoreData`（JSON 可序列化 `dict`），不读音频、不调用识别。

安装（无第三方依赖）：

```bash
pip install -e .
# 或显式：pip install -e ".[score]"
```

---

## 1. 推荐入口

```python
from music_practice.score import convert_musicxml
from music_practice.contract import dump_score_data, load_score_data, validate_score_data

score_data = convert_musicxml(
    "path/to/piece.musicxml",
    *,
    score_id="winter_1973",       # 可选；默认由文件名生成
    interval_measures=4,          # 练习分段：每段小节数
    default_tempo_bpm=120.0,      # 谱面无速度记号时的默认 BPM
    part_id=None,                 # 多声部时指定 part id；None = 取第一个 part
)

# 可选：校验 / 落盘 / 再加载
validate_score_data(score_data)
dump_score_data(score_data, "out/piece.score_data.json")
score_data = load_score_data("out/piece.score_data.json")
```

| 项 | 说明 |
|----|------|
| **函数** | `music_practice.score.convert_musicxml` |
| **输入** | MusicXML 文件路径 + 可选参数（见下） |
| **输出** | `ScoreData`：`dict[str, Any]` |

App 也可**自己构造**同结构的 `ScoreData`，跳过本库转换，只要通过 `validate_score_data`。

---

## 2. 输入

### 2.1 位置参数

| 名称 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `musicxml_path` | `str` \| `Path` | 是 | MusicXML / `.xml` 文件路径；不存在则 `FileNotFoundError` |

### 2.2 关键字参数

| 名称 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `score_id` | `str` \| `None` | `None` | 谱面 ID；`None` 时由文件名 slug 生成 |
| `interval_measures` | `int` | `4` | 练习段长度（小节数） |
| `default_tempo_bpm` | `float` | `120.0` | 无 metronome / `sound/@tempo` 时的默认四分音符 BPM |
| `part_id` | `str` \| `None` | `None` | 指定 `<score-part>` / `<part>` id；`None` 取第一个 |

**约定（当前实现）**

- 单声部跟谱；多声部需显式 `part_id`。
- 速度：`sound/@tempo` 优先（视为四分 BPM）；否则 metronome（含附点拍号单位）换算为四分 BPM。
- 输出 `notes` 为**发音音**序列（休止不进主列表或按契约标记；当前以发音音为主）。

---

## 3. 输出：`ScoreData`

返回已校验的 `dict`，可直接 `json.dump`。

### 3.1 顶层字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `schema` | `str` | 是 | 固定 `"music_practice.score_data"` |
| `schema_version` | `str` | 是 | 当前 `"1.0"` |
| `score_id` | `str` | 是 | 谱面 ID |
| `title` | `str` | 是 | 曲名（可空串） |
| `tempo` | `float` | 是 | BPM，必须 > 0 |
| `time_signature` | `str` | 是 | 如 `"4/4"`、`"6/8"` |
| `key` | `str` | 是 | 调号描述，如 `"F major"` |
| `total_measures` | `int` | 是 | 总小节数 |
| `interval_measures` | `int` | 是 | 每段小节数 |
| `intervals` | `list[dict]` | 是 | 练习段列表（可空列表） |
| `notes` | `list[dict]` | 是 | 发音音有序序列（按 `onset` 升序） |
| `source_path` | `str` | 否 | 源 MusicXML 绝对路径 |
| `source_sha256` | `str` | 否 | 源文件哈希 |
| `created_at` | `str` | 否 | UTC 时间戳字符串 |

### 3.2 `intervals[]` 元素

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | `int` | 段 ID，从 0 |
| `start_measure` | `int` | 起始小节（含），从 1 |
| `end_measure` | `int` | 结束小节（含） |
| `note_count` | `int` | 该段音符数 |

### 3.3 `notes[]` 元素

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `pitch` | `str` | 是 | 音名，如 `"C4"` |
| `pitch_midi` | `float` \| `None` | 建议 | MIDI 音高；识别侧需要时必填 |
| `measure` | `int` | 是 | 小节号，从 1 |
| `note_index_in_measure` | `int` | 是 | 小节内序号，从 1 |
| `beat` | `float` | 是 | 小节内拍位 |
| `onset` | `float` | 是 | 相对**曲首**的期望起音（秒） |
| `duration` | `float` | 是 | 时值（秒），必须 > 0 |
| `interval_id` | `int` | 是 | 所属练习段 id |
| `is_rest` | `bool` | 否 | 默认 `false` |

### 3.4 示例

```json
{
  "schema": "music_practice.score_data",
  "schema_version": "1.0",
  "score_id": "winter_1973",
  "title": "IN THE WINTER OF 1730",
  "tempo": 72.0,
  "time_signature": "4/4",
  "key": "F major",
  "total_measures": 141,
  "interval_measures": 4,
  "intervals": [
    {"id": 0, "start_measure": 1, "end_measure": 4, "note_count": 3}
  ],
  "notes": [
    {
      "pitch": "C4",
      "pitch_midi": 58,
      "measure": 4,
      "note_index_in_measure": 1,
      "beat": 3.5,
      "onset": 8.5,
      "duration": 0.5,
      "interval_id": 0,
      "is_rest": false
    }
  ],
  "source_path": "D:/scores/winter.musicxml",
  "source_sha256": "…",
  "created_at": "2026-07-30T12:00:00+00:00"
}
```

---

## 4. 契约工具（可选）

```python
from music_practice.contract import (
    SCORE_DATA_SCHEMA,
    SCORE_DATA_VERSION,
    ScoreDataError,
    validate_score_data,
    dump_score_data,
    load_score_data,
)
```

| 函数 | 输入 | 输出 |
|------|------|------|
| `validate_score_data(data)` | 任意 mapping | 校验后的 `ScoreData` dict；失败抛 `ScoreDataError` |
| `dump_score_data(data, path)` | ScoreData + 路径 | 写入 JSON，返回 `Path` |
| `load_score_data(path)` | JSON 路径 | 校验后的 ScoreData |

零音频依赖，可与转换模块一起在无 `[audio]` 环境使用。

---

## 5. 其他入口（兼容 / 落盘）

| 函数 | 用途 | 输出 |
|------|------|------|
| `import_musicxml(...)` | 解析并写入 `data/scores/{score_id}/` | 内部 `Score` 对象 |
| `load_score_from_musicxml(...)` | 仅内存解析 | 内部 `Score` |
| `parse_musicxml(...)` | 底层解析 | 音符列表等 |

新集成优先使用 `convert_musicxml` → `ScoreData`。

架构总览见 [ARCHITECTURE.md](./ARCHITECTURE.md)。
