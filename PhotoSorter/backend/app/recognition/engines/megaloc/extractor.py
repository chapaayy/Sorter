"""CPU-only MegaLoc inference, preserving the Stage 2.6.1 preprocessing and math.

Batching avoids thousands of small network calls. A bounded prefetch queue
prepares upcoming images while the CPU evaluates the preceding batch.
All features remain in RAM only for the current run.
"""
from __future__ import annotations
from concurrent.futures import Future, ThreadPoolExecutor
from collections import deque
from pathlib import Path
from typing import Callable, Iterable, Iterator

import numpy as np

from ...math import l2
from ...errors import JobCancelled
from ....photos.reader import pil_image
from ....system.performance import cpu_performance
from .loader import load_megaloc


class MegaLocEngine:
    name = 'megaloc'
    device = 'cpu'

    def __init__(self):
        import torch
        from torchvision import transforms as T

        self.torch = torch
        self.performance = cpu_performance()
        torch.set_num_threads(self.performance.threads)
        self.net = load_megaloc().to('cpu')
        # DO NOT change preprocessing values, resize order, colors or interpolation.
        self.transform = T.Compose([
            T.ToTensor(),
            T.Normalize([.485, .456, .406], [.229, .224, .225]),
            T.Resize([322, 322], antialias=True),
        ])

    def _prepare(self, path: Path):
        image = pil_image(Path(path).resolve())
        try:
            return self.transform(image)
        finally:
            image.close()

    def _forward(self, tensors: list) -> list[np.ndarray]:
        with self.torch.inference_mode():
            result = self.net(self.torch.stack(tensors, dim=0))
            if isinstance(result, (tuple, list)):
                result = result[0]
            if hasattr(result, 'pooler_output'):
                result = result.pooler_output
            values = result.detach().float().cpu().numpy()
        if values.shape[0] != len(tensors):
            raise ValueError('MegaLoc вернула неверное число эмбеддингов для пакета')
        # l2() is deliberately applied to each image, not to the whole batch.
        return [l2(values[i]) for i in range(len(tensors))]

    def extract(self, path: Path) -> np.ndarray:
        """Original one-image API for compatibility and baseline comparisons."""
        return self._forward([self._prepare(path)])[0]

    def extract_many(self, paths: Iterable[Path], *, stop: Callable[[], bool] | None = None
                     ) -> Iterator[tuple[Path, np.ndarray | None, Exception | None]]:
        """Yield one success/error per input in original order, with bounded memory.

        A single corrupt file does not poison its whole batch. If batched
        inference itself fails, retry each valid image independently so that
        existing per-photo failure behavior is preserved.
        """
        batch_size = self.performance.batch_size
        prefetch = self.performance.prefetch_workers
        source = iter(paths)

        def cancelled():
            if stop is not None and stop():
                raise JobCancelled('Остановлено пользователем')

        def prepare_catching(path: Path):
            try:
                cancelled()
                return self._prepare(path), None
            except JobCancelled:
                raise
            except Exception as exc:
                return None, exc

        # Zero workers: deterministic synchronous baseline, no prefetch threads.
        if prefetch == 0:
            while True:
                batch = []
                for _ in range(batch_size):
                    try: path = Path(next(source))
                    except StopIteration: break
                    cancelled()
                    tensor, error = prepare_catching(path)
                    batch.append((path, tensor, error))
                if not batch: break
                yield from self._infer_batch(batch, cancelled)
            return

        # At most two batches of prepared tensors live in memory at any time;
        # the next batch can decode while the model runs on the current one.
        with ThreadPoolExecutor(max_workers=prefetch, thread_name_prefix='photosorter-photo') as pool:
            queue: deque[tuple[Path, Future]] = deque()

            def replenish():
                while len(queue) < batch_size * 2:
                    try: path = Path(next(source))
                    except StopIteration: break
                    cancelled()
                    queue.append((path, pool.submit(prepare_catching, path)))

            replenish()
            while queue:
                cancelled()
                batch = []
                for _ in range(min(batch_size, len(queue))):
                    path, future = queue.popleft()
                    tensor, error = future.result()
                    batch.append((path, tensor, error))
                replenish()
                yield from self._infer_batch(batch, cancelled)

    def _infer_batch(self, batch, cancelled):
        valid = [(i, tensor) for i, (_, tensor, error) in enumerate(batch) if error is None]
        results = [None] * len(batch)
        if valid:
            cancelled()
            try:
                vectors = self._forward([tensor for _, tensor in valid])
                for (idx, _), vector in zip(valid, vectors, strict=True):
                    results[idx] = (vector, None)
            except JobCancelled:
                raise
            except Exception:
                # Isolate a faulty image or input shape. If the whole model is
                # broken, each image reports the original error independently.
                for idx, tensor in valid:
                    cancelled()
                    try:
                        results[idx] = (self._forward([tensor])[0], None)
                    except Exception as exc:
                        results[idx] = (None, exc)
        for i, (path, _tensor, error) in enumerate(batch):
            vector, inference_error = results[i] if results[i] is not None else (None, error)
            yield path, vector, inference_error

    def similarity(self, a, b) -> float:
        return float(np.dot(l2(a), l2(b)))

    def unload(self) -> None:
        self.net = None
