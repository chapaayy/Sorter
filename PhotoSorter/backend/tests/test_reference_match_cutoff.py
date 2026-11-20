"""Minimum reference-match similarity is a post-grouping, per-photo cutoff."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.recognition.pipeline import match_grouped_megaloc
from app.results.match_filter import apply_min_match_score
from server.api.routes.processing_settings import ProcessingSettings
from server.services import auto_processing
from server.database import connect
from .test_unified_queue_stage3 import system,add_published_reference,add_fo


def test_cutoff_individual_photo_not_group_mean():
    original = [
        {"query":"good.jpg", "top":[{"label":"SAM 0001","score":.480}],
         "group_id":"G0001","assigned_sam_score":.800,"individual_top":[{"score":.800}]},
        {"query":"blocked.jpg", "top":[{"label":"SAM 0001","score":.480}],
         "group_id":"G0001","assigned_sam_score":.160,"individual_top":[{"score":.160}]},
    ]
    filtered = apply_min_match_score(original, .200)
    assert filtered[0]["top"] == original[0]["top"]
    assert filtered[0]["match_score"] == .800
    assert filtered[1]["top"] == []
    assert filtered[1]["match_rejected"]
    assert filtered[1]["match_score"] == .160
    assert "0.200" in filtered[1]["reason"]
    assert filtered[1]["individual_top"] == original[1]["individual_top"]
    assert all("match_rejected" not in row for row in original)
    # Repeating with OFF does not write or mutate anything.
    assert apply_min_match_score(original,0) is original


def test_boundary_group_conflicts_and_video_scores():
    rows = [
        {"query":"exact.jpg","top":[{"label":"SAM 1","score":.7}],
         "assigned_sam_score":.200},
        {"query":"video.mp4","top":[{"label":"SAM 2","score":.199}]},
        {"query":"already_unknown.jpg","top":[],"reason":"Конфликт группировки"},
        {"query":"broken.jpg","top":[{"label":"SAM 3","score":.50}],
         "assigned_sam_score":float("nan")},
    ]
    result = apply_min_match_score(rows,.200)
    assert result[0]["top"]  # >= threshold is accepted
    assert result[0]["match_score"] == .200
    assert result[1]["top"] == [] and result[1]["match_score"] == .199
    assert result[2] is rows[2] and result[2]["reason"] == "Конфликт группировки"
    assert result[3]["top"] == [] and result[3]["match_rejected"]
    assert result[3]["match_score"] is None


@pytest.mark.parametrize("value",[-0.01,1.01,float("nan"),float("inf")])
def test_invalid_cutoff_is_never_applied(value):
    with pytest.raises(ValueError):
        apply_min_match_score([],value)
    with pytest.raises(ValidationError):
        ProcessingSettings(auto_process_new_batches=False,grouping_threshold=.5,
                           min_match_score=value)


def test_pipeline_group_math_and_candidates_untouched(tmp_path):
    # Two FO form one group; group mean is .765, but the weaker FO is .530.
    # A .600 minimum must reject only that photo.
    def vector(degrees):
        r=np.deg2rad(degrees)
        return np.array([np.cos(r),np.sin(r)],dtype=np.float32)
    photos=[tmp_path/"good.jpg",tmp_path/"weak.jpg"]
    ref=tmp_path/"ref.jpg"
    vectors={str(photos[0]):vector(0),str(photos[1]):vector(58),
             str(ref):vector(0)}
    class Engine:
        def extract(self,path):
            return vectors[str(path)]
    original=match_grouped_megaloc(Engine(),[(ref,"SAM 0001")],photos)
    assert [row["group_id"] for row in original]==["G0001","G0001"]
    assert all(row["top"] for row in original)
    assert original[0]["top"][0]["score"]==original[1]["top"][0]["score"]
    assert original[0]["assigned_sam_score"]>original[1]["assigned_sam_score"]
    filtered=apply_min_match_score(original,.600)
    assert filtered[0]["top"]
    assert not filtered[1]["top"]
    assert filtered[1]["group_candidates"]==original[1]["group_candidates"]
    assert filtered[0]["group_peers"]==original[0]["group_peers"]


def test_setting_persisted_and_frozen_for_new_runs_only(system):
    add_published_reference(system)
    defaults=auto_processing.settings()
    assert defaults["min_match_score"] == 0.0
    auto_processing.update_settings(enabled=False,threshold=.50,min_match_score=.20)
    assert auto_processing.settings()["min_match_score"]==.20
    # Old clients saving auto/grouping fields must preserve the new setting.
    auto_processing.update_settings(enabled=True,threshold=.75)
    assert auto_processing.settings()["min_match_score"]==.20
    run=add_fo()
    with connect() as db:
        first=db.execute("SELECT snapshot FROM jobs WHERE id=%s",(run,)).fetchone()["snapshot"]
    assert first["min_match_score"]==.20
    assert first["grouping_threshold"]==.50  # manual run's explicit threshold
    auto_processing.update_settings(enabled=False,threshold=.50,min_match_score=.35)
    with connect() as db:
        again=db.execute("SELECT snapshot FROM jobs WHERE id=%s",(run,)).fetchone()["snapshot"]
    assert again["min_match_score"]==.20
    another=add_fo()
    with connect() as db:
        latest=db.execute("SELECT snapshot FROM jobs WHERE id=%s",(another,)).fetchone()["snapshot"]
    assert latest["min_match_score"]==.35
