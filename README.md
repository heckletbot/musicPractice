# music-practice

MusicXML 单声部跟谱库：谱面导入、音高检测、开始点识别、节奏评测。无 HTTP 服务，通过 Python API 调用。

## 依赖

- Python >= 3.10
- `numpy` / `librosa` / `soundfile` / `scipy`（见本包与 `deps/music2seq` 的 `pyproject.toml`）

```bash
# 1) 安装内嵌 music2seq
cd deps/music2seq
pip install -e .

# 2) 安装本包
cd ../..
pip install -e ".[dev]"
```

## 用法

```python
from music_practice import utils

# 谱面
score = utils.import_score("path/to/score.musicxml", score_id="my_score")
summary = utils.score_summary(score)

# 音高
track = utils.analyze_pitch_track("query.wav", tempo=152)
estimate = utils.analyze_pitch_segment("query.wav", 0.0, 0.2)

# 开始点 / 节奏（需已安装 deps/music2seq，模板映射见 data/score_template_map.json）
# 见 music_practice.utils 公开 API
```

CLI 导入谱面：

```bash
python scripts/import_score.py path/to/score.musicxml --score-id my_score
```

输出：`data/scores/{score_id}/meta.json` + `notes.json`

## 包结构

```
deps/music2seq/  # 内嵌依赖（开始点识别）
src/music_practice/
  score/         # MusicXML 导入与持久化
  pitch/         # 音高检测
  start_detect/  # 开始点识别（依赖 music2seq）
  rhythm/        # 节奏 onset / duration / 判定
  utils/         # 统一公开 API
tests/           # 验证通过的用例与音频夹具
```

## 项目分析

模块数据流、输入与输出见 [ARCHITECTURE.md](ARCHITECTURE.md)。  
节奏窗模式 `anchored_grid`、空拍前后双校准（rest re-anchor）与 MusicXML 时间轴矫正见 [CHANGELOG_RHYTHM.md](CHANGELOG_RHYTHM.md) / [ARCHITECTURE.md §5.3](ARCHITECTURE.md)。

## 自测

交付用例与夹具用法见 [TESTING.md](TESTING.md)：

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v
```

Winter 全曲 `anchored_grid` 可选回归：

```bash
python scripts/eval_winter_full_anchored_grid.py
```

