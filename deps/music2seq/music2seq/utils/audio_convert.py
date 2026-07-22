"""Audio format conversion utilities."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import librosa
import soundfile as sf


def find_ffmpeg() -> str:
    """Return ffmpeg executable path, or raise RuntimeError if missing."""
    path = shutil.which("ffmpeg")
    if path is None:
        raise RuntimeError(
            "未找到 ffmpeg。请先安装："
            " Ubuntu/Debian: apt install ffmpeg；"
            " macOS: brew install ffmpeg"
        )
    return path


def m4a_to_mp3(
    input_path: str | Path,
    output_path: str | Path | None = None,
    *,
    overwrite: bool = False,
    bitrate: str = "192k",
) -> Path:
    """
    Convert a single M4A file to MP3 via ffmpeg.

    Args:
        input_path: Source .m4a (or other ffmpeg-readable) file.
        output_path: Destination .mp3; default: same stem as input.
        overwrite: Replace existing output file.
        bitrate: MP3 bitrate passed to ffmpeg (-b:a).

    Returns:
        Path to the written MP3 file.
    """
    src = Path(input_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"源文件不存在: {src}")

    dst = Path(output_path).resolve() if output_path is not None else src.with_suffix(".mp3")
    if dst.exists() and not overwrite:
        raise FileExistsError(f"目标已存在: {dst}（使用 overwrite=True 覆盖）")

    dst.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = find_ffmpeg()
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y" if overwrite else "-n",
        "-i",
        str(src),
        "-codec:a",
        "libmp3lame",
        "-b:a",
        bitrate,
        str(dst),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg 转换失败 ({src.name}): {result.stderr.strip() or result.stdout.strip()}"
        )
    if not dst.exists():
        raise RuntimeError(f"ffmpeg 未生成输出文件: {dst}")
    return dst


def convert_m4a_dir(
    input_dir: str | Path,
    output_dir: str | Path | None = None,
    *,
    overwrite: bool = False,
    bitrate: str = "192k",
    recursive: bool = False,
) -> list[Path]:
    """
    Batch-convert .m4a files in a directory to .mp3.

    Args:
        input_dir: Directory containing .m4a files.
        output_dir: Output directory; default: same as input_dir.
        overwrite: Replace existing MP3 files.
        bitrate: MP3 bitrate for ffmpeg.
        recursive: Also search subdirectories.

    Returns:
        List of written MP3 paths.
    """
    root = Path(input_dir).resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"不是目录: {root}")

    out_root = Path(output_dir).resolve() if output_dir is not None else root
    out_root.mkdir(parents=True, exist_ok=True)

    pattern = "**/*.m4a" if recursive else "*.m4a"
    sources = sorted(root.glob(pattern))
    if not sources:
        raise FileNotFoundError(f"目录中未找到 .m4a 文件: {root}")

    written: list[Path] = []
    for src in sources:
        rel = src.relative_to(root)
        dst = out_root / rel.with_suffix(".mp3")
        dst.parent.mkdir(parents=True, exist_ok=True)
        written.append(
            m4a_to_mp3(src, dst, overwrite=overwrite, bitrate=bitrate)
        )
    return written


def audio_to_raw_wav(
    input_path: str | Path,
    output_path: str | Path | None = None,
    *,
    sample_rate: int = 22050,
    overwrite: bool = False,
) -> Path:
    """
    Convert audio to mono WAV with target sample rate only (no DSP preprocess).

    Uses librosa load + soundfile write; supports mp3/m4a/flac/wav etc.
    Default output name: <stem>_raw.wav beside input, or explicit output_path.
    """
    src = Path(input_path).resolve()
    if not src.exists():
        raise FileNotFoundError(f"源文件不存在: {src}")

    if output_path is None:
        dst = src.with_name(f"{src.stem}_raw.wav")
    else:
        dst = Path(output_path).resolve()

    if dst.exists() and not overwrite:
        raise FileExistsError(f"目标已存在: {dst}（使用 overwrite=True 覆盖）")

    dst.parent.mkdir(parents=True, exist_ok=True)
    audio, _ = librosa.load(str(src), sr=sample_rate, mono=True)
    sf.write(str(dst), audio.astype("float32"), sample_rate)
    if not dst.exists():
        raise RuntimeError(f"未生成 WAV: {dst}")
    return dst
