from __future__ import annotations

import json

import pytest

from qwen_book.tts import load_ref_text


def test_load_ref_text_from_json(tmp_path):
    path = tmp_path / "narrator.json"
    path.write_text(
        json.dumps({"text": "  Сегодня тихое утро.  "}, ensure_ascii=False),
        encoding="utf-8",
    )
    assert load_ref_text(path) == "Сегодня тихое утро."


def test_load_ref_text_accepts_alternate_key(tmp_path):
    path = tmp_path / "narrator.json"
    path.write_text(json.dumps({"transcript": "Hello."}), encoding="utf-8")
    assert load_ref_text(path) == "Hello."


def test_load_ref_text_rejects_missing_field(tmp_path):
    path = tmp_path / "narrator.json"
    path.write_text(json.dumps({"audio": "narrator.wav"}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_ref_text(path)


def test_load_ref_text_rejects_invalid_json(tmp_path):
    path = tmp_path / "narrator.json"
    path.write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError):
        load_ref_text(path)
