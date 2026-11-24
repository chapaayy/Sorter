"""Private process-owned scratch; crash GC and durable leases are stage 5."""
from contextlib import contextmanager
import os
from pathlib import Path
import shutil
import uuid
from .categories import Category
from .paths import app_key
from .filesystem import parent_fd

@contextmanager
def temporary_operation(root, service):
    key = app_key(Category.SCRATCH, service=service, operation_id=uuid.uuid4()).relative
    with parent_fd(root, key, create=True) as (fd, name):
        os.mkdir(name, mode=0o700, dir_fd=fd)
        try:
            yield Path(root) / key
        finally:
            # Linux shutil.rmtree is fd-relative and resists symlink attacks.
            shutil.rmtree(name, dir_fd=fd)
