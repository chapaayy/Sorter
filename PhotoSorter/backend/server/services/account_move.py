"""Replayable, no-overwrite rename for a persisted ownership transfer plan."""
import os, stat


def fingerprint(st):
    return [st.st_dev, st.st_ino]


def _stat(path):
    try:
        return path.lstat()
    except FileNotFoundError:
        return None


def move(root, entry, parent_fd, owned_directory):
    src = owned_directory(root / entry['src'], root)
    dst = owned_directory(root / entry['dst'], root)
    s, d = _stat(src), _stat(dst)
    expected = entry['inode']
    mode = stat.S_ISDIR if entry['kind'] == 'directory' else stat.S_ISREG
    if s is None and d is not None and mode(d.st_mode) and fingerprint(d) == expected:
        return
    if s is None or not mode(s.st_mode) or fingerprint(s) != expected or d is not None:
        raise ValueError('Transfer source or destination changed')
    with parent_fd(root, entry['src']) as (sf, sn), parent_fd(root, entry['dst'], create=True) as (df, dn):
        if fingerprint(os.stat(sn, dir_fd=sf, follow_symlinks=False)) != expected:
            raise ValueError('Transfer source changed')
        try:
            os.stat(dn, dir_fd=df, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ValueError('Transfer destination already exists')
        os.rename(sn, dn, src_dir_fd=sf, dst_dir_fd=df)
        os.fsync(sf)
        os.fsync(df)


def rewrite(value, old, new):
    if isinstance(value, str):
        return new + value[len(old):] if value == old or value.startswith(old + '/') else value
    if isinstance(value, list):
        return [rewrite(x, old, new) for x in value]
    if isinstance(value, dict):
        return {k: rewrite(v, old, new) for k, v in value.items()}
    return value
