import json

from promptchived.importers.chatgpt import parse_chatgpt_file


def test_chatgpt_parser_preserves_branches_and_attachment(tmp_path):
    asset = tmp_path / "image.png"
    asset.write_bytes(b"png")
    (tmp_path / "conversation_asset_file_names.json").write_text(
        json.dumps({"file-1.dat": "image.png"}), encoding="utf-8"
    )
    export = [
        {
            "id": "conversation-1",
            "title": "Branched conversation",
            "create_time": 1_700_000_000,
            "update_time": 1_700_000_010,
            "current_node": "answer-b",
            "mapping": {
                "root": {"id": "root", "parent": None, "message": None},
                "question": {
                    "id": "question", "parent": "root",
                    "message": {"id": "message-q", "author": {"role": "user"}, "create_time": 1_700_000_001, "content": {"content_type": "text", "parts": ["Question"]}, "metadata": {}},
                },
                "answer-a": {
                    "id": "answer-a", "parent": "question",
                    "message": {"id": "message-a", "author": {"role": "assistant"}, "create_time": 1_700_000_002, "content": {"content_type": "text", "parts": ["Previous answer"]}, "metadata": {}},
                },
                "answer-b": {
                    "id": "answer-b", "parent": "question",
                    "message": {"id": "message-b", "author": {"role": "assistant"}, "create_time": 1_700_000_003, "content": {"content_type": "multimodal_text", "parts": ["Active answer", {"asset_pointer": "file-service://file-1.dat", "mime_type": "image/png"}]}, "metadata": {}},
                },
            },
        }
    ]
    path = tmp_path / "conversations-000.json"
    path.write_text(json.dumps(export), encoding="utf-8")

    conversation = parse_chatgpt_file(path, tmp_path)[0]

    assert conversation.source_id == "conversation-1"
    assert len(conversation.messages) == 3
    assert next(m for m in conversation.messages if m.source_id == "message-a").is_current_path is False
    active = next(m for m in conversation.messages if m.source_id == "message-b")
    assert active.is_current_path is True
    assert active.attachments[0].relative_path == "image.png"


def test_chatgpt_parser_extracts_audio_attachment_from_object_pointer(tmp_path):
    audio = tmp_path / "recording.wav"
    audio.write_bytes(b"wav")
    (tmp_path / "conversation_asset_file_names.json").write_text(
        json.dumps({"file-audio.dat": "recording.wav"}), encoding="utf-8"
    )
    export = [
        {
            "id": "conversation-audio",
            "title": "Audio conversation",
            "mapping": {
                "audio": {
                    "id": "audio",
                    "parent": None,
                    "message": {
                        "id": "message-audio",
                        "author": {"role": "user"},
                        "content": {
                            "content_type": "multimodal_text",
                            "parts": [
                                {
                                    "audio_asset_pointer": {
                                        "asset_pointer": "file-service://file-audio.dat",
                                        "content_type": "audio_asset_pointer",
                                        "metadata": {"transcription": None},
                                    }
                                }
                            ],
                        },
                        "metadata": {},
                    },
                }
            },
        }
    ]
    path = tmp_path / "conversations-004.json"
    path.write_text(json.dumps(export), encoding="utf-8")

    conversation = parse_chatgpt_file(path, tmp_path)[0]

    assert conversation.messages[0].attachments[0].relative_path == "recording.wav"
