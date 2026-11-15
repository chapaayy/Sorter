"""CPU-bounded local FFmpeg normalization and time-based frame sampling."""
from pathlib import Path
import subprocess
import tempfile
import time

from .formats import VIDEO_CONTAINERS, compatible_streams, probe


def _run(args, *, stop=None, timeout=120):
    with tempfile.TemporaryFile() as errors:
        with subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=errors) as process:
            deadline = time.monotonic() + timeout
            try:
                while process.poll() is None:
                    if stop and stop():
                        raise InterruptedError('Обработка видео остановлена')
                    if time.monotonic() > deadline:
                        raise TimeoutError('Превышено время обработки видео')
                    time.sleep(.1)
                if process.returncode:
                    raise ValueError('FFmpeg не смог прочитать или обработать видео')
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()


def _base():
    return ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
            '-protocol_whitelist', 'file', '-format_whitelist', VIDEO_CONTAINERS,
            '-filter_threads', '1', '-threads', '1']


def encode(source, out, target, *, stop=None):
    meta = probe(source)
    copy_video, copy_audio = compatible_streams(meta, target)
    args = [*_base(), '-i', str(source), '-map', '0:V:0', '-map', '0:a:0?',
            '-map_metadata', '-1', '-map_chapters', '-1']
    if copy_video:
        args += ['-c:v', 'copy']
    elif target == 'mp4':
        args += ['-c:v', 'libx264', '-preset', 'fast', '-crf', '20', '-pix_fmt', 'yuv420p',
                 '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-threads:v', '2']
    else:
        args += ['-c:v', 'libvpx-vp9', '-crf', '30', '-b:v', '0', '-deadline', 'good',
                 '-cpu-used', '4', '-pix_fmt', 'yuv420p', '-threads:v', '2']
    args += ['-c:a', 'copy' if copy_audio else 'aac' if target == 'mp4' else 'libopus']
    if meta.audio and not copy_audio:
        args += ['-ac', '2', '-b:a', '160k']
    if target == 'mp4':
        args += ['-movflags', '+faststart']
    _run([*args, str(out)], timeout=3600, stop=stop)
    return probe(out)


def _index(source, *, stop):
    # ffprobe emits decoded video frame timestamps in presentation order. Stream
    # to a bounded temporary index instead of holding frames or JSON in RAM.
    with tempfile.TemporaryFile() as index:
        args = ['ffprobe', '-v', 'error', '-protocol_whitelist', 'file',
                '-format_whitelist', VIDEO_CONTAINERS, '-threads', '1',
                '-select_streams', 'V:0', '-show_frames', '-show_entries',
                'frame=best_effort_timestamp_time', '-of', 'compact=p=1:nk=0', str(source)]
        with subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=index, stderr=subprocess.DEVNULL) as proc:
            deadline = time.monotonic() + 900
            try:
                while proc.poll() is None:
                    if stop and stop():
                        raise InterruptedError('Извлечение кадров остановлено')
                    if time.monotonic() > deadline or index.tell() > 16 * 1024 * 1024:
                        raise ValueError('Видео слишком длинное для анализа кадров')
                    time.sleep(.1)
                if proc.returncode:
                    raise ValueError('Не удалось прочитать кадры видео')
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()
        index.seek(0)
        return _pick_indices(index)


def _timestamps(index):
    for line in index:
        if not line.startswith(b'frame|'):continue
        try:
            yield float(line.split(b'|',2)[1].split(b'=',1)[1])
        except (ValueError,IndexError):
            yield None


def _pick_indices(index):
    first = last = None
    count = 0
    for t in _timestamps(index):
        if t is not None:
            if first is None:
                first = t
            last = t
        count += 1
    if not count:
        raise ValueError('Нет читаемых видеокадров')
    if count == 1:
        return [0]
    if first is None or first==last:
        return sorted({round((count-1)*i/7) for i in range(8)})
    targets = [first + (last - first) * i / 7 for i in range(1, 7)]
    best = [(float('inf'), 0) for _ in targets]
    index.seek(0)
    for n, t in enumerate(_timestamps(index)):
        if t is None:continue
        for i, target in enumerate(targets):
            best[i] = min(best[i], (abs(t - target), n))
    return sorted({0, count - 1, *(n for _, n in best)})


def extract_frames(source, directory, *, stop=None):
    indices = _index(source, stop=stop)
    select = '+'.join(f'eq(n\\,{n})' for n in indices)
    _run([*_base(), '-i', str(source), '-map', '0:V:0',
          '-vf', 'select=' + select + ",scale='min(1280,iw)':'min(1280,ih)':force_original_aspect_ratio=decrease",
          '-fps_mode', 'vfr', '-frames:v', str(len(indices)), '-threads:v', '1',
          '-q:v', '2', str(directory / '%02d.jpg')], timeout=900, stop=stop)
    frames = sorted(directory.glob('*.jpg'))
    if not frames:
        raise ValueError('Не удалось извлечь кадры видео')
    return frames


def poster(source: Path, destination: Path):
    _run([*_base(), '-i', str(source), '-map', '0:V:0',
        '-vf', "scale='min(480,iw)':'min(480,ih)':force_original_aspect_ratio=decrease",
        '-frames:v', '1', '-threads:v', '1', str(destination)], timeout=30)
