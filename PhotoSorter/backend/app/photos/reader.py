"""Image decoding as used by the original MegaLoc path."""
from pathlib import Path
from PIL import Image, ImageOps

EXTS = {'.jpg', '.jpeg', '.png', '.bmp', '.webp', '.tif', '.tiff'}

def pil_image(path: Path) -> Image.Image:
    with Image.open(path) as src:
        image = ImageOps.exif_transpose(src).convert('RGB')
        image.load()
        return image
