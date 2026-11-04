"""SAM identifiers: preserve LAB 3.7's panel and side parsing."""
import re

_SAM_NUMBER = re.compile(r'^SAM-\d{4}(?!\d)', re.I)
_SAM_SIDE = re.compile(r'^-([ABCDАБВГ]\d{0,2})(?=$|[-\s,;.(])', re.I)
_SAM_PANEL = re.compile(r'^-([PР]\d{1,2})(?=$|[-\s,;.(])', re.I)

def _extract_sam_identifier(raw: str) -> str | None:
    """Normalize a SAM folder name without interpreting a street as a side.

    Unknown extra suffixes are treated as a description, not a valid ID.
    A path separator is never accepted as a description boundary.
    """
    base = _SAM_NUMBER.match(raw)
    if base is None:
        return None
    tail = raw[base.end():]
    if tail and tail[0] not in '- ,;\t\r\n(':
        return None
    result = base.group(0).upper()
    side = _SAM_SIDE.match(tail)
    if side is not None:
        result += '-' + side.group(1).upper()
        tail = tail[side.end():]
    panel = _SAM_PANEL.match(tail)
    if panel is not None:
        result += '-' + panel.group(1).upper()
    return result


_LABEL_PATTERN=re.compile(r'^[\w][\w .-]{0,79}$',re.UNICODE)
_RESERVED={'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}

def check_label(label):
    label=str(label).strip()
    canonical=_extract_sam_identifier(label)
    if canonical is not None: label=canonical
    if not _LABEL_PATTERN.fullmatch(label) or label.endswith(('.',' ')):
        raise ValueError(f'Некорректный номер конструкции: {label!r}')
    if label.split('.')[0].upper() in _RESERVED:
        raise ValueError(f'Зарезервированное Windows-имя: {label}')
    return label
