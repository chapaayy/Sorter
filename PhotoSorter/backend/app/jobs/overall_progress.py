"""Run-wide progress and evidence-based ETA from measured stage throughput.

No fabricated fixed stage percentages or persisted performance cache. Before
sufficient samples, the UI receives no percentage/ETA; completed runs reach 100%.
Estimates adapt as the FO/reference/GPU/copy speeds are observed this run.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

STAGE_LABELS = {
    'validate_references': 'Проверка Образцов',
    'validate_queries': 'Проверка входящих ФО',
    'loading': 'Загрузка модели',
    'queries': 'MegaLoc — вычисление признаков ФО',
    'grouping': 'MegaLoc — сравнение ФО между собой',
    'grouping_merge': 'MegaLoc — формирование групп ФО',
    'grouping_diagnostics': 'MegaLoc — проверка групп ФО',
    'references': 'MegaLoc — вычисление признаков Образцов',
    'matching': 'MegaLoc — сравнение групп с Образцами',
    'saving': 'Сохранение Готовых фоток',
    'export': 'Запись результатов',
    'archive': 'Подготовка архива',
}

@dataclass
class Phase:
    model: str | None
    stage: str
    total: int
    current: int = 0
    started_at: float | None = None
    end_at: float | None = None

    def seconds_per_unit(self, now):
        if self.started_at is None or self.current < 2:
            return None
        elapsed = max(0.0, (self.end_at or now) - self.started_at)
        if elapsed < 0.05:
            return None
        return elapsed / self.current

    def expected_duration(self, now, rate):
        if self.end_at is not None and self.started_at is not None:
            return max(0.0, self.end_at - self.started_at)
        if self.stage == 'loading' and self.end_at is None:
            return None  # model startup can take arbitrarily long
        if rate is None:
            return None
        if self.started_at is not None:
            observed = max(0.0, now - self.started_at)
            return max(observed, rate * self.total)
        return rate * self.total


class OverallProgress:
    def __init__(self):
        self.phases: list[Phase] = []
        self.last_percent: float | None = None
        self.started = None
        self.configured = False

    def configure(self, ref_count: int, fo_count: int, selected_models: list[str], started: float):
        self.started = started
        self.last_percent = None
        self.phases = [Phase(None,'validate_queries',max(1,fo_count)),
                       Phase('megaloc','loading',1)]
        for stage,count in [('queries',fo_count),('grouping',fo_count),
                            ('grouping_merge',1),('grouping_diagnostics',fo_count),
                            ('references',ref_count),('matching',fo_count),
                            ('saving',fo_count),('export',1),('archive',fo_count)]:
            self.phases.append(Phase('megaloc',stage,max(1,count)))
        self.configured = True

    def update(self, model: str | None, stage: str, current: int, total: int, now: float):
        if not self.configured:
            return
        for phase in self.phases:
            if phase.model == model and phase.stage == stage:
                if phase.started_at is None:
                    phase.started_at = now
                phase.total = max(1, int(total))
                phase.current = min(phase.total, max(phase.current, max(0,int(current))))
                if phase.current == phase.total and phase.end_at is None:
                    phase.end_at = now
                return

    def _rate(self, phase: Phase, now: float):
        own = phase.seconds_per_unit(now)
        if own is not None:
            return own
        # Estimate from work with comparable cost measured in the SAME run.
        def rates(stage_names, model=None):
            found = [p.seconds_per_unit(now) for p in self.phases
                     if p.stage in stage_names and (model is None or p.model == model)]
            return [v for v in found if v is not None and math.isfinite(v) and v > 0]
        if phase.stage in ('queries','references'):
            items = rates(('queries','references'),phase.model)
            if not items:
                items = rates(('queries','references'))
        elif phase.stage in ('validate_references','validate_queries','saving'):
            items = rates(('validate_references','validate_queries','saving'))
        elif phase.stage in ('grouping','grouping_merge','grouping_diagnostics','matching'):
            items = rates(('grouping','grouping_merge','grouping_diagnostics','matching'),phase.model)
            if not items:
                items = rates(('validate_references','validate_queries'))
        elif phase.stage == 'archive':
            items = rates(('archive',))
        elif phase.stage == 'export':
            items = rates(('saving','validate_queries','validate_references'))
        else:
            items = []
        return sum(items)/len(items) if items else None

    def calculate(self, now: float, *, finished: bool = False) -> dict:
        if finished:
            self.last_percent = 100.0
            return {'overall_percent':100.0,'estimated_remaining_seconds':0.0,
                    'eta_status':'completed'}
        if not self.configured:
            return {'overall_percent':None,'estimated_remaining_seconds':None,
                    'eta_status':'collecting'}
        # Only show an overall estimate when some actual neural extraction
        # throughput has been measured. Validation speed cannot predict CUDA.
        neural_sampled = any(p.current >= min(5,p.total) and p.seconds_per_unit(now) is not None
                             for p in self.phases if p.stage in ('queries','references'))
        if not neural_sampled:
            return {'overall_percent':None,'estimated_remaining_seconds':None,
                    'eta_status':'collecting'}
        elapsed = max(0.0, now-(self.started if self.started is not None else now))
        predicted = []
        unestimated = False
        for phase in self.phases:
            if phase.started_at is not None and phase.end_at is not None:
                predicted.append(phase.expected_duration(now, None))
            elif phase.stage == 'loading':
                # Unknown future model initialization can take arbitrarily long.
                unestimated = True
            else:
                estimate = phase.expected_duration(now, self._rate(phase,now))
                if estimate is None:
                    unestimated = True
                else:
                    predicted.append(estimate)
        if not predicted:
            return {'overall_percent':None,'estimated_remaining_seconds':None,
                    'eta_status':'collecting'}
        estimated_total = max(sum(predicted), elapsed)
        # Unmeasured loading/export is not counted as completed. Stay below
        # 99% until the worker marks the run finished.
        raw = min(99.0, (elapsed / estimated_total) * 100.0) if estimated_total > 0 else 0.0
        self.last_percent = max(self.last_percent or 0.0, raw)
        eta = None if unestimated else max(0.0, estimated_total - elapsed)
        return {'overall_percent':round(self.last_percent,1),
                'estimated_remaining_seconds':round(eta,1) if eta is not None else None,
                'eta_status':'measured' if eta is not None else 'partial'}
