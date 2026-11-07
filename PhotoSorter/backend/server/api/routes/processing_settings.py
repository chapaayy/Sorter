"""Server-persisted default preferences for future automatic MegaLoc runs."""
from fastapi import APIRouter
from pydantic import BaseModel,Field
from ...services import auto_processing

router=APIRouter(prefix="/api/processing-settings",tags=["processing"])

class ProcessingSettings(BaseModel):
    auto_process_new_batches:bool
    grouping_threshold:float=Field(ge=.50,le=.99,allow_inf_nan=False)

@router.get("")
def read_settings():
    return auto_processing.settings()

@router.patch("")
def save_settings(payload:ProcessingSettings):
    return auto_processing.update_settings(
        enabled=payload.auto_process_new_batches,threshold=payload.grouping_threshold)

class CpuSettings(BaseModel):
    threads:int=Field(ge=1,le=32)

@router.get("/cpu")
def cpu_settings():
    from ...services import compute_settings
    return compute_settings.read()

@router.patch("/cpu")
def update_cpu_settings(payload:CpuSettings):
    from ...services import compute_settings
    return compute_settings.update(payload.threads)

class WorkloadSettings(BaseModel):
    mode:str
    fo_threads:int=Field(ge=1,le=32)
    reference_threads:int=Field(ge=1,le=32)

@router.get("/workloads")
def workload_settings():
    from ...services import compute_settings
    return compute_settings.workload_settings()

@router.patch("/workloads")
def update_workloads(payload:WorkloadSettings):
    from ...services import compute_settings
    return compute_settings.update_workloads(payload.mode,payload.fo_threads,payload.reference_threads)
