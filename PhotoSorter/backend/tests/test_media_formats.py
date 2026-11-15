"""Format compatibility uses both the bytes and the named delivery format."""
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest

from PIL import Image

from app.photos.reader import pil_image
from server.media.formats import inspect, normalized_image


class PhotoPassthroughTest(unittest.TestCase):
    def test_matching_container_is_preserved_and_mismatches_are_normalized(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            photo = Image.new("RGB", (32, 24), "red")
            for detected in ("JPEG", "MPO", "PNG", "WEBP"):
                source = root / (detected + ".part")
                options = (
                    {"save_all": True, "append_images": [Image.new("RGB", photo.size, "blue")]}
                    if detected == "MPO" else {}
                )
                photo.save(source, format=detected, **options)
                with Image.open(source) as image:
                    self.assertEqual(image.format, detected)
                for name, output in (("file.JPG", "jpg"), ("file.JPEG", "jpg"),
                                     ("file.PNG", "png"), ("file.JPG", "png"),
                                     ("file.PNG", "jpg"), ("file.mpo", "jpg"),
                                     ("file.webp", "jpg")):
                    with self.subTest(detected=detected, name=name, output=output):
                        expected = (
                            (name.endswith((".JPG", ".JPEG")) and output == "jpg" and detected in ("JPEG", "MPO"))
                            or (name.endswith(".PNG") and output == "png" and detected == "PNG")
                        )
                        self.assertEqual(
                            inspect(source, name, None, output, "mp4"),
                            ("keep" if expected else "prepare", None),
                        )

    def test_animated_png_already_matches_png_and_keeps_both_frames(self):
        with TemporaryDirectory() as folder:
            source = Path(folder) / "animated.PNG"
            Image.new("RGBA", (32, 24), "red").save(source, format="PNG", save_all=True,
                append_images=[Image.new("RGBA", (32, 24), "blue")])
            with Image.open(source) as image:
                self.assertEqual(image.format, "PNG")
                self.assertEqual(image.n_frames, 2)
            self.assertEqual(inspect(source, source.name, None, "png", "mp4"), ("keep", None))
            self.assertEqual(inspect(source, source.name, None, "jpg", "mp4"), ("prepare", None))

    def test_mpo_primary_photo_remains_readable_and_png_output_stays_png(self):
        with TemporaryDirectory() as folder:
            source = Path(folder) / "IMG_2940.JPG"
            Image.new("RGB", (32, 24), "red").save(source, format="MPO", save_all=True,
                append_images=[Image.new("RGB", (32, 24), "blue")])
            original = source.read_bytes()
            primary = pil_image(source)
            self.assertGreater(primary.getpixel((0, 0))[0], 240)
            target = Path(folder) / "output.png"
            normalized_image(source, target, "png")
            with Image.open(target) as image:
                self.assertEqual(image.format, "PNG")
                self.assertEqual(image.getpixel((0, 0)), primary.getpixel((0, 0)))
            self.assertEqual(source.read_bytes(), original)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "Requires FFmpeg")
class VideoPassthroughTest(unittest.TestCase):
    def test_compatible_video_formats_are_kept_but_extension_is_not_enough(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            for target, codec, mime in (("mp4", "libx264", "video/mp4"),
                                         ("webm", "libvpx-vp9", "video/webm")):
                actual_path = root / ("sample." + target)
                subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=s=32x24:r=5",
                                "-frames:v", "5", "-threads", "1", "-c:v", codec, str(actual_path)],
                               check=True)
                other = "webm" if target == "mp4" else "mp4"
                self.assertEqual(inspect(actual_path, "video." + target.upper(), mime, "jpg", target)[0], "keep")
                self.assertEqual(inspect(actual_path, "video." + other.upper(), mime, "jpg", other)[0], "prepare")
            incompatible = root / "mpeg4.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=s=32x24:r=5",
                            "-frames:v", "5", "-threads", "1", "-c:v", "mpeg4", str(incompatible)],
                           check=True)
            self.assertEqual(inspect(incompatible, incompatible.name, "video/mp4", "jpg", "mp4")[0],
                             "prepare")
