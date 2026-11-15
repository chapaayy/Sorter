"""Inspect local media bytes and select a no-op or an output normalization."""
from dataclasses import dataclass
from pathlib import Path
import json
import math
import subprocess

from PIL import Image, ImageOps
from ..storage.thumbnail_cache import PIXEL_LIMIT

# Disallow playlist/network demuxers for uploaded, untrusted data.
VIDEO_CONTAINERS = 'mov,mp4,m4a,3gp,3g2,mj2,matroska,webm,avi,mpeg,mpegts,flv,asf,ogg,mxf,rm,dv'
PHOTO_FORMATS = {'jpg': 'JPEG', 'png': 'PNG'}
# Encoder names and accepted input formats are distinct. A JPG can contain
# an MPF index and extra JPEG images, so Pillow may report MPO for it.
PHOTO_PASSTHROUGH = {
    'jpg': (('.jpg', '.jpeg'), ('JPEG', 'MPO')),
    'png': (('.png',), ('PNG',)),
}
VIDEO_CODECS = {'mp4': ('h264', 'aac'), 'webm': ('vp9', 'opus')}


@dataclass(frozen=True)
class Video:
    container: str
    brand: str
    codec: str
    pixel_format: str
    audio: str | None
    duration: float | None
    pixels: int = 2073600
    fps: float = 30.0


def _time(value, default=None):
    try:
        seconds = float(value)
        return seconds if math.isfinite(seconds) else default
    except (TypeError, ValueError):
        return default


def probe(path: Path) -> Video:
    result = subprocess.run(['ffprobe', '-v', 'error', '-protocol_whitelist', 'file',
        '-format_whitelist', VIDEO_CONTAINERS,
        '-show_entries', 'format=format_name,duration:format_tags=major_brand:stream=codec_type,codec_name,pix_fmt,width,height,duration,avg_frame_rate:stream_disposition=attached_pic',
        '-of', 'json', str(path)], capture_output=True, check=True, timeout=15)
    data = json.loads(result.stdout)
    streams = data.get('streams', [])
    video = next((s for s in streams if s.get('codec_type') == 'video'
                  and not s.get('disposition', {}).get('attached_pic')), None)
    if not video or not video.get('width') or not video.get('height'):
        raise ValueError('Не найден видеопоток')
    if video['width'] * video['height'] > PIXEL_LIMIT:
        raise ValueError('Слишком большое разрешение видео')
    audio = next((s for s in streams if s.get('codec_type') == 'audio'), None)
    fmt = data.get('format', {})
    duration = _time(video.get('duration'), _time(fmt.get('duration')))
    try:
        n,d=video.get("avg_frame_rate","0/0").split("/")
        fps=float(n)/float(d)
        if not math.isfinite(fps) or fps<=0:fps=30.0
    except (ValueError,ZeroDivisionError):fps=30.0
    return Video(fmt.get('format_name', ''), fmt.get('tags', {}).get('major_brand', '').strip(),
                 video.get('codec_name', ''), video.get('pix_fmt', ''), audio.get('codec_name', '') if audio else None,
                 duration if duration and duration > 0 else None,video["width"]*video["height"],fps)


def compatible_streams(video: Video, target: str):
    codec, audio = VIDEO_CODECS[target]
    return video.codec == codec and video.pixel_format in ('yuv420p', 'yuvj420p'), video.audio in (None, audio)


def _webm(path):
    # EBML DocType distinguishes WebM from MKV; ffprobe reports both as matroska,webm.
    with path.open('rb') as stream:
        head = stream.read(4096)
    return head.startswith(b'\x1a\x45\xdf\xa3') and b'\x42\x82\x84webm' in head


def ready_video(path, name, video, target):
    suffix = Path(name).suffix.lower()
    if target == 'webm':
        container = suffix == '.webm' and 'webm' in video.container and _webm(path)
    else:
        container = suffix == '.mp4' and 'mp4' in video.container and video.brand in {
            'isom', 'iso2', 'iso4', 'iso5', 'iso6', 'mp41', 'mp42', 'avc1', 'M4V',
        }
    return container and all(compatible_streams(video, target))


def register_heif():
    try:
        from pillow_heif import register_heif_opener
    except ImportError:
        return
    register_heif_opener(thumbnails=False)


def inspect(path, name, media_type, image_target, video_target):
    if media_type and media_type.startswith('video/'):
        video = probe(path)
        return ('keep' if ready_video(path, name, video, video_target) else 'prepare', video.duration)
    suffixes, formats = PHOTO_PASSTHROUGH[image_target]
    if Path(name).suffix.lower() in suffixes:
        with Image.open(path) as img:
            if img.format in formats:
                return 'keep', None
    return 'prepare', None


def output_name(name, target):
    suffix = Path(name).suffix
    if suffix.lower() == '.' + target:
        return name
    return (name[:-len(suffix)] if suffix else name) + '.' + target


def normalized_image(source, destination, target):
    register_heif()
    with Image.open(source) as original:
        if original.width * original.height > PIXEL_LIMIT:
            raise ValueError('Слишком большое разрешение изображения')
        # Animated photos export their first frame. Prevent silent rotation changes.
        image = ImageOps.exif_transpose(original)
        icc = image.info.get('icc_profile')
        options = {'icc_profile': icc} if icc and len(icc) <= 131072 and image.mode == 'RGB' else {}
        if target == 'jpg':
            if image.mode in ('RGBA', 'LA') or 'transparency' in image.info:
                alpha = image.convert('RGBA')
                image = Image.new('RGB', alpha.size, 'white')
                image.paste(alpha, mask=alpha.getchannel('A'))
            else:
                image = image.convert('RGB')
            options.update(quality=95, subsampling=0)
        elif image.mode not in ('RGB', 'RGBA', 'L', 'LA', 'P', 'I;16'):
            image = image.convert('RGB')
        image.save(destination, format=PHOTO_FORMATS[target], **options)
