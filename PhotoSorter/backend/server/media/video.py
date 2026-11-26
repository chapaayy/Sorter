"""CPU-bounded local FFmpeg normalization and time-based frame sampling."""
import os
from pathlib import Path
import subprocess
import sys,resource
from contextlib import nullcontext
from fastapi import HTTPException
from app.storage.temporary import temporary_file
import time

from .formats import VIDEO_CONTAINERS, compatible_streams, probe


def thread_budget(cpus):
    cpus=max(1,int(cpus))
    decode=1 if cpus<4 else min(4,max(2,cpus//3))
    return decode,max(1,cpus-decode)


FRAME_LIMIT=4*1024**2
INDEX_LIMIT=16*1024**2

def _limited(args,limit):
    # Apply a kernel limit before exec, without preexec_fn in threaded workers.
    if limit is None:return args
    code=("import os,resource,sys,ctypes,signal;limit=int(sys.argv[1]);"
          "assert ctypes.CDLL(None,use_errno=True).prctl(1,signal.SIGKILL,0,0,0)==0;"
          "os.getppid()==int(sys.argv[2]) or os._exit(125);"
          "resource.setrlimit(resource.RLIMIT_FSIZE,(limit,resource.getrlimit(resource.RLIMIT_FSIZE)[1]));"
          "os.execvp(sys.argv[3],sys.argv[3:])")
    return [sys.executable,"-c",code,str(limit),str(os.getpid()),*args]

def _read_progress(stream,partial,callback):
    while True:
        try:data=os.read(stream.fileno(),65536)
        except BlockingIOError:break
        if not data:break
        lines=(partial+data).split(b'\n')
        for line in lines[:-1]:
            if line.startswith(b'out_time_us='):
                try:seconds=int(line[len(b'out_time_us='):])/1_000_000
                except ValueError:continue
                if seconds>=0:callback(seconds)
        partial=lines[-1]
    return partial

def _run(args, *, stop=None, timeout=120, progress=None, limit=None,budget=None,destination=None):
    # Error output was never consumed. Stream progress via a nonblocking pipe;
    # no uncontrolled stdout/stderr scratch files.
    cap=budget.limit if budget is not None else limit
    partial=b''
    with subprocess.Popen(_limited(args,cap),stdin=subprocess.DEVNULL,
                          stdout=subprocess.PIPE if progress else subprocess.DEVNULL,stderr=subprocess.DEVNULL) as process:
        if progress:os.set_blocking(process.stdout.fileno(),False)
        deadline=time.monotonic()+timeout
        try:
            while process.poll() is None:
                if stop and stop():raise InterruptedError('Обработка видео остановлена')
                if time.monotonic()>deadline:raise TimeoutError('Превышено время обработки видео')
                if progress:partial=_read_progress(process.stdout,partial,progress)
                if budget is not None and destination is not None and destination.exists():
                    size=destination.stat().st_size
                    if size*4>=cap*3:
                        growth=max(8*1024**2,cap//2)
                        budget.grow(growth,personal=growth)
                        cap=budget.limit
                        try:
                            _,hard=resource.prlimit(process.pid,resource.RLIMIT_FSIZE)
                            resource.prlimit(process.pid,resource.RLIMIT_FSIZE,(cap,hard))
                        except ProcessLookupError:pass
                time.sleep(.05)
            if progress:_read_progress(process.stdout,partial,progress)
            if process.returncode:
                if destination is not None and destination.exists() and cap is not None and destination.stat().st_size>=cap:
                    raise HTTPException(507,'Недостаточно зарезервированного места для перекодирования')
                raise ValueError('FFmpeg не смог прочитать или обработать видео')
        finally:
            if process.poll() is None:
                process.kill();process.wait()

def _base(decode_threads=1):
    return ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error', '-y',
            '-protocol_whitelist', 'file', '-format_whitelist', VIDEO_CONTAINERS,
            '-filter_threads', '1', '-threads', str(decode_threads)]


def encode(source, out, target, *, stop=None, progress=None, meta=None, cpus=2,budget=None):
    meta = meta or probe(source)
    decode_threads,encode_threads=thread_budget(cpus)
    copy_video, copy_audio = compatible_streams(meta, target)
    args = [*_base(decode_threads), '-i', str(source), '-map', '0:V:0', '-map', '0:a:0?',
            '-map_metadata', '-1', '-map_chapters', '-1']
    if copy_video:
        args += ['-c:v', 'copy']
    elif target == 'mp4':
        args += ['-c:v', 'libx264', '-preset', 'fast', '-crf', '20', '-pix_fmt', 'yuv420p',
                 '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2', '-threads:v', str(encode_threads)]
    else:
        args += ['-c:v', 'libvpx-vp9', '-crf', '30', '-b:v', '0', '-deadline', 'good',
                 '-cpu-used', '4', '-pix_fmt', 'yuv420p', '-threads:v', str(encode_threads)]
    args += ['-c:a', 'copy' if copy_audio else 'aac' if target == 'mp4' else 'libopus']
    if meta.audio and not copy_audio:
        args += ['-ac', '2', '-b:a', '160k']
    if target == 'mp4':
        args += ['-movflags', '+faststart']
    if progress:args[1:1]=['-progress','pipe:1','-nostats','-stats_period','0.5']
    _run([*args, str(out)], timeout=3600, stop=stop, progress=progress,budget=budget,destination=Path(out))
    return probe(out)


def _index(source, *, stop, managed=False):
    # ffprobe emits decoded video frame timestamps in presentation order. Stream
    # to a bounded temporary index instead of holding frames or JSON in RAM.
    from ..storage.reservations import reservation
    reserve=reservation('frame_index',INDEX_LIMIT) if managed else nullcontext()
    with reserve, temporary_file() as index:
        args = ['ffprobe', '-v', 'error', '-protocol_whitelist', 'file',
                '-format_whitelist', VIDEO_CONTAINERS, '-threads', '1',
                '-select_streams', 'V:0', '-show_frames', '-show_entries',
                'frame=best_effort_timestamp_time', '-of', 'compact=p=1:nk=0', str(source)]
        with subprocess.Popen(_limited(args,INDEX_LIMIT), stdin=subprocess.DEVNULL, stdout=index, stderr=subprocess.DEVNULL) as proc:
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


def extract_frames(source, directory, *, stop=None,managed=False):
    indices = _index(source, stop=stop,managed=managed)
    select = '+'.join(f'eq(n\\,{n})' for n in indices)
    _run([*_base(), '-i', str(source), '-map', '0:V:0',
          '-vf', 'select=' + select + ",scale='min(1280,iw)':'min(1280,ih)':force_original_aspect_ratio=decrease",
          '-fps_mode', 'vfr', '-frames:v', str(len(indices)), '-threads:v', '1',
          '-q:v', '2', str(directory / '%02d.jpg')], timeout=900, stop=stop,limit=FRAME_LIMIT)
    frames = sorted(directory.glob('*.jpg'))
    if not frames:
        raise ValueError('Не удалось извлечь кадры видео')
    return frames


def poster(source: Path, destination: Path):
    _run([*_base(), '-i', str(source), '-map', '0:V:0',
        '-vf', "scale='min(480,iw)':'min(480,ih)':force_original_aspect_ratio=decrease",
        '-frames:v', '1', '-threads:v', '1', str(destination)], timeout=30,limit=FRAME_LIMIT)
