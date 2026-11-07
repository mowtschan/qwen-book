from __future__ import annotations

import pytest

from qwen_book.pipeline import compute_calibration, estimate_range


def test_compute_calibration_drops_first_chunk_warmup():
    metrics = compute_calibration(
        chars=[100, 200, 200],
        speech_seconds=[5.0, 10.0, 10.0],
        synth_seconds=[60.0, 12.0, 12.0],
    )

    assert metrics.chunks == 3
    assert metrics.chars == 500
    assert metrics.speech_seconds == 25.0
    assert metrics.chars_per_second == 20.0
    assert metrics.rtf == pytest.approx(1.2)
    assert metrics.warmup_seconds == pytest.approx(54.0)


def test_compute_calibration_keeps_normal_first_chunk():
    metrics = compute_calibration(
        chars=[100, 100],
        speech_seconds=[5.0, 5.0],
        synth_seconds=[6.0, 7.0],
    )

    assert metrics.rtf == pytest.approx(1.3)
    assert metrics.warmup_seconds == 0.0


def test_estimate_range_adds_pauses_and_warmup():
    metrics = compute_calibration(
        chars=[100, 200, 200],
        speech_seconds=[5.0, 10.0, 10.0],
        synth_seconds=[60.0, 12.0, 12.0],
    )
    estimate = estimate_range(total_chars=1000, pause_seconds=100.0, metrics=metrics)

    assert estimate.speech_seconds == 50.0
    assert estimate.pause_seconds == 100.0
    assert estimate.audio_seconds == 150.0
    assert estimate.synth_seconds == pytest.approx(114.0)


def test_compute_calibration_rejects_empty():
    with pytest.raises(ValueError):
        compute_calibration([], [], [])
