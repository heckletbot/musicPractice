# music-practice

MusicXML 单声部跟谱库：谱面导入、音高检测、开始点识别、节奏评测。无 HTTP 服务，通过 Python API 调用。

**MusicXML 转换** 与 **音频识别** 已解耦：二者只通过固定 `ScoreData` 契约交换数据，可单独安装、单独工作。接口见 [doc/SCORE_INTERFACE.md](doc/SCORE_INTERFACE.md)。

## 依赖与安装

- Python >= 3.10
- 默认安装：**契约 + MusicXML 转换**（标准库，无 numpy/librosa）
- 音频识别：额外安装 `[audio]`

```bash
# 仅转换 / 契约
pip install -e .

# 识别（音高 / 节奏 / recognize）
pip install -e ".[audio]"

# 开发回归
pip install -e ".[dev]"

# 开始点模板匹配（可选）
cd deps/music2seq && pip install -e . && cd ../..
```

## 推荐用法（解耦接口）

```python
# 侧 A：仅 MusicXML → ScoreData（App 也可自己构造同结构 dict）
from music_practice.score import convert_musicxml

score_data = convert_musicxml("path/to/score.musicxml", score_id="my_score")

# 侧 B：仅识别（不解析 XML）
from music_practice.recognize import recognize
import numpy as np

audio = np.zeros(22050, dtype=np.float32)  # 示例
result = recognize(
    score_data,
    audio.tobytes(),
    sample_rate=22050,
    start_from={"measure": 1, "note_index": 1},
    config={"duration_window_mode": "anchored_grid"},
)
# result["summary"] / result["notes"][*].overall_correct ...
```

兼容旧入口：`from music_practice import utils`（需 `[audio]`）。

CLI 导入谱面：

```bash
python scripts/import_score.py path/to/score.musicxml --score-id my_score
```

输出：`data/scores/{score_id}/meta.json` + `notes.json`

## 包结构

```
doc/             # 项目文档（仅 README 留在根目录）
  SCORE_INTERFACE.md
  ARCHITECTURE.md
  TESTING.md
  CHANGELOG_RHYTHM.md
deps/music2seq/  # 内嵌依赖（开始点识别）
src/music_practice/
  contract/      # ScoreData 校验 / 桥接（无音频依赖）
  score/         # MusicXML → ScoreData
  recognize/     # recognize(score_data, audio, ...)
  pitch/         # 音高检测
  start_detect/  # 开始点识别（依赖 music2seq）
  rhythm/        # 节奏 onset / duration / 判定
  utils/         # 统一公开 API（需 audio）
tests/
```

## 项目分析

模块数据流、输入与输出见 [doc/ARCHITECTURE.md](doc/ARCHITECTURE.md)。  
节奏窗模式 `anchored_grid`、空拍前后双校准见 [doc/CHANGELOG_RHYTHM.md](doc/CHANGELOG_RHYTHM.md)。

## 自测

```bash
pip install -e ".[dev]"
python -m pytest tests/test_contract_interface.py tests/test_score_convert_standalone.py tests/test_recognize_decoupled.py -v
python -m pytest tests/ -v
```

交付用例说明见 [doc/TESTING.md](doc/TESTING.md)。
