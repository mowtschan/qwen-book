from __future__ import annotations

import json

from qwen_book.cli import main
from qwen_book.tts import model_voices


def _local_model(tmp_path):
    model = tmp_path / "model"
    model.mkdir()
    (model / "config.json").write_text(
        json.dumps(
            {
                "tts_model_type": "custom_voice",
                "talker_config": {
                    "spk_id": {"ryan": 1, "vivian": 2},
                    "codec_language_id": {
                        "english": 10,
                        "russian": 11,
                        "beijing_dialect": 12,
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    return model


def test_model_voices_reads_local_config(tmp_path):
    voices, languages, model_type = model_voices(str(_local_model(tmp_path)))
    assert voices == ["ryan", "vivian"]
    assert languages == ["english", "russian"]
    assert model_type == "custom_voice"


def test_cli_list_voices(tmp_path, capsys):
    code = main(["--list-voices", "--model", str(_local_model(tmp_path))])
    output = capsys.readouterr().out

    assert code == 0
    assert "ryan" in output
    assert "english" in output
