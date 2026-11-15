"""Raw formats eligible for inline playback in the authenticated FO gallery.

The MIME must come from the server's upload inspection, not filename or request
headers. In particular, do not expose SVG or other active content inline.
"""

INLINE_TYPES = frozenset({
    "image/jpeg", "image/png", "image/webp", "image/gif", "image/avif", "image/bmp",
    "video/mp4", "video/webm", "video/quicktime", "video/x-m4v", "video/ogg",
})
