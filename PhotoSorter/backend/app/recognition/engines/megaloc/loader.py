"""Load an offline MegaLoc checkpoint without downloading during recognition."""
import importlib.util
import sys

from ....system.model_store import configure_model_environment, checkpoint, repo_folder, files_present

def load_megaloc():
    configure_model_environment()
    if not files_present():
        raise FileNotFoundError('MegaLoc: не найдены локальные веса или исходный код модели')
    repo = repo_folder()
    weight = checkpoint()
    spec = importlib.util.spec_from_file_location('_photosorter_megaloc_model', str(repo / 'megaloc_model.py'))
    if spec is None or spec.loader is None:
        raise RuntimeError('Не удалось открыть исходный код MegaLoc')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    from safetensors.torch import load_file
    model = module.MegaLoc()
    model.load_state_dict(load_file(str(weight), device='cpu'), strict=True)
    return model.eval()
