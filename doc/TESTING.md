# 如何用本包自带用例做功能验证

交付包内已附带**验证通过**的 pytest 用例与音频夹具（`tests/`）。开始点引擎已内化为 `music_practice.start_match`，无需另装 `deps/`。

## 1. 环境准备

在交付包根目录：

```bash
pip install -e ".[dev]"
```

需：Python >= 3.10，可 `import music_practice`（含 `music_practice.start_match`）。

## 2. 一键跑全部交付用例

```bash
python -m pytest tests/ -v
```

期望：全部 passed（约 60+ 条；具体以收集数为准；个别可选结果文件缺失时可能 skip）。

## 3. 按模块分跑


| 模块                    | 命令                                                                                                                                      | 说明                            |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------- |
| 契约解耦（ScoreData / PitchTrackData / convert / recognize） | `python -m pytest tests/test_contract_interface.py tests/test_pitch_track_contract.py tests/test_score_convert_standalone.py tests/test_recognize_decoupled.py -v` | 固定接口；见 [SCORE_INTERFACE.md](./SCORE_INTERFACE.md)、[PITCH_INTERFACE.md](./PITCH_INTERFACE.md) |
| 节奏（合成，无 WAV）          | `python -m pytest tests/test_rhythm_judge.py tests/test_rhythm_duration.py tests/test_rhythm_onset.py tests/test_rhythm_pipeline.py tests/test_rhythm_reanchor.py -v` | 判定 / 时值 / onset / 链路（含 `anchored_grid`）/ 空拍双校准 |
| 节奏（模板窗 winter）        | `python -m pytest tests/test_rhythm_template_winter.py -v`                                                                              | 需 `fixtures/rhythm_template/` |
| 节奏（流式 winter）         | `python -m pytest tests/test_rhythm_session_winter_stream.py -v`                                                                        | 需同上                           |
| MusicXML 附点节拍器 → 四分 BPM | `python -m pytest tests/test_score_tempo_metronome.py -q` | 六八拍 `附点四分=N` |
| start_match 解析（和弦/速度 offset） | `python -m pytest tests/test_start_match_score_locator.py -v`                                                                     | 原 music2seq 解析用例                    |
| 开始点夹具结构               | `python -m pytest tests/test_start_detect_dataset.py -v`                                                                                | 检查 manifest / 文件是否齐全          |
| 开始点模板（meili + viktor） | `python -m pytest tests/test_start_detect.py -v`                                                                                        |                               |
| 开始点真吹曲首               | `python -m pytest tests/test_start_detect_played_clips.py -v`                                                                           |                               |
| 开始点 Session 推流        | `python -m pytest tests/test_start_detect_stream.py -v`                                                                                 | meili 逐块 push                 |


## 4. 位置

```
tests/
  conftest.py
  fixtures/
    start_detect/       # 模板开始点：manifest、queries、templates、scores、source
    played_anchors/     # 真吹曲首 clips / generated
    rhythm_template/    # 节奏模板窗（winter）
    rhythm_played/      # 真吹节奏窗（可选参考）
  test_*.py
src/music_practice/start_match/   # 模板匹配引擎（原 deps/music2seq）
```

夹具缺失时部分用例会 `skip` 或断言失败；交付包默认已带齐验证所需文件。

## 5. winter 全曲 `anchored_grid`（完备性门禁）

夹具：`tests/fixtures/rhythm_template/winter_1973_full/`（矫正后的谱面时间 + 模板窗音频）。

```bash
python -m pytest tests/test_rhythm_template_winter.py tests/test_rhythm_session_winter_stream.py -v
python scripts/eval_winter_full_anchored_grid.py
```

参考结果（已附）：

- `tests/results/winter_1973_full_by_measure_anchored_grid.md`
- `tests/results/rhythm_template_winter_full_anchored_grid.json`

说明见 [ARCHITECTURE.md §5.1](./ARCHITECTURE.md)（`anchored_grid` 窗模式）。

## 6. 空拍前后双校准（单元）

```bash
python -m pytest tests/test_rhythm_reanchor.py -v
```

说明见 [CHANGELOG_RHYTHM.md](./CHANGELOG_RHYTHM.md)。
