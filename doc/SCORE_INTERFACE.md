# 谱面 ↔ 识别：固定接口约定

本文定义 **MusicXML 转换** 与 **音频识别** 之间的唯一契约。两端通过固定函数交换数据，**互不依赖实现**，可单独安装、单独工作。

依据：`music-practice` 需求 [`audio_recognition.md`](../../music-practice/docs/audio_recognition.md)（识别侧不解析 XML，只消费已解析谱面）。

---

## 1. 职责划分

```text
┌─────────────────────┐         ScoreData          ┌─────────────────────┐
│  MusicXML 转换       │  ───────────────────────►  │  音频识别            │
│  convert_musicxml   │         (JSON/dict)         │  recognize           │
│  可单独工作          │  ◄── 不回调、不共享内部类型 ──│  可单独工作          │
└─────────────────────┘                             └─────────────────────┘
```

| 侧 | 做什么 | 不做什么 |
|----|--------|----------|
| **转换** | MusicXML → `ScoreData`；可选落盘 | 不读音频、不调用识别 |
| **识别** | `ScoreData` + 音频 → 逐音判定 | 不解析 MusicXML、不依赖转换模块实现 |

App 也可**自己**产出符合本契约的 `ScoreData`，跳过本库转换模块。

---

## 2. 固定接口函数

### 2.1 转换侧

```python
from music_practice.score import convert_musicxml

score_data: dict = convert_musicxml(
    "piece.musicxml",
    *,
    score_id="winter_1973",          # 可选
    interval_measures=4,
    default_tempo_bpm=120.0,
    part_id=None,
)
# 返回值 = ScoreData（见 §3），可 json.dump
```

仅内存 / 仅落盘仍可用原有 `import_musicxml` / `parse_musicxml`；新代码优先 `convert_musicxml`。

### 2.2 识别侧

```python
from music_practice.recognize import recognize

result: dict = recognize(
    score_data,                 # ScoreData dict 或同结构 JSON 对象
    audio_data,                 # bytes：float32 PCM 的 tobytes()；或 np.ndarray float32
    sample_rate,                # int，建议 22050
    start_from=None,            # 见 §4；None = 从谱面第一个音开始
    config=None,                # 见 §5；None = 默认
)
# 返回值 = RecognizeResult（见 §6）
```

识别侧**只**通过 `score_data` 读谱，不 import MusicXML 解析器。

### 2.3 契约工具（两端共用，零音频依赖）

```python
from music_practice.contract import (
    SCORE_DATA_SCHEMA,
    SCORE_DATA_VERSION,
    validate_score_data,
    dump_score_data,
    load_score_data,
)
```

---

## 3. ScoreData（谱面传递格式）

JSON 可序列化 `dict`。`schema` + `schema_version` 用于演进校验。

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
    {
      "id": 0,
      "start_measure": 1,
      "end_measure": 4,
      "note_count": 3
    }
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
  ]
}
```

### 3.1 顶层字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `schema` | string | 是 | 固定 `"music_practice.score_data"` |
| `schema_version` | string | 是 | 当前 `"1.0"` |
| `score_id` | string | 是 | 谱面 ID |
| `title` | string | 是 | 曲名（可空串） |
| `tempo` | number | 是 | BPM，> 0 |
| `time_signature` | string | 是 | 如 `"4/4"` |
| `key` | string | 是 | 调号描述 |
| `total_measures` | int | 是 | 总小节数 ≥ 0 |
| `interval_measures` | int | 是 | 每段小节数，默认 4 |
| `intervals` | array | 是 | 练习段列表（可空） |
| `notes` | array | 是 | **发音音**有序序列（按 onset 升序） |

可选元数据（转换侧可写，识别侧可忽略）：`source_path`、`source_sha256`、`created_at`。

### 3.2 `intervals[]`

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | int | 段 ID，从 0 |
| `start_measure` | int | 起始小节（含），从 1 |
| `end_measure` | int | 结束小节（含） |
| `note_count` | int | 该段音符数 |

### 3.3 `notes[]`（核心）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `pitch` | string | 是 | 音名，如 `C4`；休止可用 `"rest"` |
| `pitch_midi` | number\|null | 建议 | MIDI 音高；休止为 `null` |
| `measure` | int | 是 | 小节号，从 1 |
| `note_index_in_measure` | int | 是 | **小节内序号，从 1**（与 `start_from` 对齐） |
| `beat` | number | 是 | 小节内拍位 |
| `onset` | number | 是 | 相对**曲首**的期望起音（秒） |
| `duration` | number | 是 | 时值（秒）> 0 |
| `interval_id` | int | 是 | 所属段落 |
| `is_rest` | bool | 否 | 默认 `false`；当前契约以发音音为主 |

**规则**

- `note_index_in_measure` 按该小节内 `notes` 出现顺序从 1 编号。
- `onset` 为全曲绝对时间；识别在应用 `start_from` 后会把选中起点 rebase 为练习时间轴 0。
- 单声部；和弦不展开为先后音（由转换侧保证）。

---

## 4. StartFrom（对齐起点）

```json
{ "measure": 4, "note_index": 1 }
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `measure` | int | 小节号，从 1 |
| `note_index` | int | 小节内音符序号，从 1（= `note_index_in_measure`） |

`null` / 省略：从 `notes[0]` 开始。

语义：音频与谱面从该音对齐；谱面在该音之前的音不参与判定；音频超出谱面尾部的部分忽略（左对齐）。

---

## 5. Config（识别可选配置）

全部可选；未给字段用默认值。

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `pitch_tolerance_semitones` | number | `1.0` | 音高容差（半音） |
| `duration_window_mode` | string | `"anchored_grid"` | `detected_onset` / `score_grid` / `anchored_grid` |
| `onset_tolerance_beat` | number | `0.35` | 起音容差（拍） |
| `onset_tolerance_sec_cap` | number | `0.25` | 起音容差上限（秒） |
| `sample_rate` | int | 与入参一致 | 可覆盖提示用 |

---

## 6. RecognizeResult（识别返回）

```json
{
  "schema": "music_practice.recognize_result",
  "schema_version": "1.0",
  "summary": {
    "total_notes": 17,
    "correct_count": 15,
    "onset_error_count": 1,
    "duration_error_count": 1,
    "pitch_error_count": 2,
    "missed_count": 0,
    "accuracy": 0.8824
  },
  "notes": [
    {
      "measure": 4,
      "note_index_in_measure": 1,
      "onset_expected_sec": 0.0,
      "onset_detected_sec": 0.02,
      "onset_ok": true,
      "duration_expected_sec": 0.5,
      "duration_detected_sec": 0.48,
      "duration_ok": true,
      "pitch_expected_midi": 58.0,
      "pitch_detected_midi": 58.1,
      "pitch_ok": true,
      "rhythm_ok": true,
      "overall_correct": true,
      "error_dims": []
    }
  ],
  "start_from": { "measure": 4, "note_index": 1 }
}
```

### 6.1 `summary`

| 字段 | 说明 |
|------|------|
| `total_notes` | 参与判定的期望音数 |
| `correct_count` | `overall_correct == true` 的数量 |
| `onset_error_count` | `onset_ok == false` |
| `duration_error_count` | `duration_ok == false` |
| `pitch_error_count` | `pitch_ok == false` |
| `missed_count` | 未演奏到（检测起音缺失且无有效音高帧） |
| `accuracy` | `correct_count / total_notes`（total=0 时为 0） |

### 6.2 `notes[]` 单音

| 字段 | 说明 |
|------|------|
| `measure` / `note_index_in_measure` | 定位 |
| `onset_*` / `duration_*` / `pitch_*` | 期望 / 检测 / 分项 ok |
| `rhythm_ok` | 产品节奏通过：`⟺ duration_ok` |
| `overall_correct` | `pitch_ok ∧ rhythm_ok` |
| `error_dims` | 失败维度列表：`"onset"` / `"duration"` / `"pitch"` / `"missed"`（可多项） |

时间字段：相对 **练习轴**（`start_from` 对应音为 0 秒），不是曲首绝对秒。

---

## 7. 音频约定

| 项 | 约定 |
|----|------|
| 布局 | mono |
| 采样率 | 调用方传入；建议 **22050** |
| `audio_data` | `float32` 小端 PCM 的 `bytes`（`np.ndarray.astype(np.float32).tobytes()`），或直接传 `float32` `ndarray` |
| 对齐 | 音频 `t=0` 对准 `start_from` 对应音的期望起音 |

---

## 8. 构建与安装解耦

| 安装 | 能力 |
|------|------|
| `pip install -e .` | 契约 + MusicXML 转换（标准库 XML，无 librosa） |
| `pip install -e ".[audio]"` | 上述 + 音高 / 节奏 / `recognize` |
| `pip install -e ".[dev]"` | audio + pytest |
| `pip install -e ".[start]"` | 开始点模板匹配（`start_match`） |

验证：

```bash
# 契约 + 转换（不依赖音频栈）
python -m pytest tests/test_contract_interface.py -v

# 识别（需 [audio]）
python -m pytest tests/test_recognize_decoupled.py -v
```

---

## 9. 版本演进

- 增字段：优先可选，旧识别端忽略未知键。
- 改语义 / 删必填：升 `schema_version`（如 `1.1`），并在 `validate_score_data` 中声明兼容范围。
