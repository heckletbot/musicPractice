# 如何用本包自带用例做功能验证

交付包内已附带**验证通过**的 pytest 用例与音频夹具（`tests/`），以及开始点识别依赖 `deps/music2seq/`。  
无需工作区其他目录即可安装与自测。

## 1. 环境准备

在交付包根目录：

```bash
# 安装内嵌 music2seq
cd deps/music2seq
pip install -e .

# 安装本包（含 pytest）
cd ../..
pip install -e ".[dev]"
```

需：Python >= 3.10，可 `import music2seq` 与 `import music_practice`。

## 2. 一键跑全部交付用例

```bash
python -m pytest tests/ -v
```

期望：全部 passed（约 60+ 条；具体以收集数为准；个别可选结果文件缺失时可能 skip）。

## 3. 按模块分跑


| 模块                    | 命令                                                                                                                                      | 说明                            |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------- |
| 节奏（合成，无 WAV）          | `python -m pytest tests/test_rhythm_judge.py tests/test_rhythm_duration.py tests/test_rhythm_onset.py tests/test_rhythm_pipeline.py -v` | 判定 / 时值 / onset / 链路          |
| 节奏（模板窗 winter）        | `python -m pytest tests/test_rhythm_template_winter.py -v`                                                                              | 需 `fixtures/rhythm_template/` |
| 节奏（流式 winter）         | `python -m pytest tests/test_rhythm_session_winter_stream.py -v`                                                                        | 需同上                           |
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
deps/
  music2seq/            # 内嵌依赖源码
```

夹具缺失时部分用例会 `skip` 或断言失败；交付包默认已带齐验证所需文件。



