from __future__ import annotations

import pytest

from qwen_book.cli import main


def test_cli_dry_run(sample_epub, capsys):
    code = main([str(sample_epub), "--dry-run", "--chapters", "2-2"])
    output = capsys.readouterr().out

    assert code == 0
    assert "Test Book" in output
    assert "Part A" in output
    assert "Part B" not in output
    assert "Estimate (heuristic):" in output


def test_cli_rejects_bad_chapter_range(sample_epub):
    code = main([str(sample_epub), "--dry-run", "--chapters", "9"])
    assert code == 1


def test_cli_calibrate_requires_dry_run(sample_epub):
    with pytest.raises(SystemExit):
        main([str(sample_epub), "--calibrate"])


def test_cli_dry_run_with_reference_json(sample_epub, tmp_path, capsys):
    wav = tmp_path / "narrator.wav"
    wav.write_bytes(b"RIFF")
    ref = tmp_path / "narrator.json"
    ref.write_text('{"text": "exact transcript"}', encoding="utf-8")

    code = main(
        [
            str(sample_epub),
            "--dry-run",
            "--ref-audio",
            str(wav),
            "--ref-text",
            str(ref),
            "--model",
            "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16",
        ]
    )
    output = capsys.readouterr().out

    assert code == 0
    assert "Test Book" in output
    assert "Estimate (heuristic):" in output
