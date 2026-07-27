# 节奏 / 谱面时间轴 — 交付更新说明

## `anchored_grid` 时长窗模式

- 配置：`RhythmJudgeConfig.duration_window_mode = "anchored_grid"`
- 行为：以开始点锁定后的**谱面期望 onset** 为锚；搜索窗  
  `[期望 − pre, 期望 + 时值 + post]`（默认 0.2 / 0.35 拍）；  
  检出起音若在容差内则作局部参考，避免整窗跟着错峰漂。
- 产品规则不变：`rhythm_ok ⟺ duration_ok`。

涉及文件：

- `src/music_practice/rhythm/config.py`
- `src/music_practice/rhythm/judge.py`
- `src/music_practice/rhythm/duration.py`
- `tests/test_rhythm_judge.py` / `tests/test_rhythm_duration.py`

## MusicXML 期望时间矫正（`deps/music2seq`）

- 和弦 `<chord/>` 与主音**同起音**
- 速度记号尊重 `<offset>`（如小节末改速，不提前改变整小节休止速度）

涉及文件：

- `deps/music2seq/music2seq/score/parser.py`
- `deps/music2seq/tests/test_score_locator.py`

## Winter 全曲回归

- 夹具：`tests/fixtures/rhythm_template/winter_1973_full/`
- 脚本：`scripts/eval_winter_full_anchored_grid.py`
- 参考结果：`tests/results/winter_1973_full_by_measure_anchored_grid.md`  
  （模板全曲约 **491/503 ≈ 97.6%** `rhythm_ok`；剩余失败多为同起音多音/和弦）

## 空拍前后双校准（rest re-anchor）

长段跟谱时，空拍后演奏易整体漂移。新增在**谱面空拍间隙**上的局部重锁（复用已有 pitch 轨，代价低）：

1. **校准前一音结束**：在目标音高轨上找释放点  
2. **空拍开始** = 该结束时刻  
3. **再校准下一音起音**：仅在空拍开始之后搜索新音；将后续期望 onset 整体平移  

触发条件：相邻发音音之间谱面间隙 ≥ `min_rest_beat`（默认 0.5 拍）。  
前音结束搜索不会越过下一音的期望起音，避免误锁。

API：

```python
from music_practice.rhythm import (
    RestReanchorConfig,
    apply_rest_reanchors,
)

adjusted, events = apply_rest_reanchors(
    expected_notes,
    pitch_track,
    tempo_bpm=82.0,
    config=RestReanchorConfig(enabled=True, min_rest_beat=0.5),
)
# 再用 adjusted 调用 evaluate_rhythm / evaluate_rhythm_from_track
```

`RestReanchorEvent` 字段：`prev_note_end_*`、`rest_start_sec`、`expected_sec_before`、`detected_sec`、`shift_sec`。

涉及文件：

- `src/music_practice/rhythm/reanchor.py`（新建）
- `src/music_practice/rhythm/__init__.py`（导出）
- `tests/test_rhythm_reanchor.py`（合成 pitch 轨单测，无外部录音）

**交付范围说明**：本包只合入上述库代码与单元测试。离线 Tp / 小幸运等实验录音、按小节结果表、实验脚本产出物**不在**交付包内。
