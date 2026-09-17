from datetime import UTC

from promptchived.importers.gemini import parse_gemini_file


def activity(prompt: str, answer: str, timestamp: str, conversation_id: str | None) -> str:
    link = f'<a href="https://gemini.google.com/app/{conversation_id}">Conversation</a>' if conversation_id else ""
    return f"""
    <div class="outer-cell mdl-cell">
      <div class="header-cell"><p>Gemini Apps</p></div>
      <div class="content-cell mdl-cell mdl-cell--6-col">
        Prompted<br>{prompt}<br>{timestamp}<br><p>{answer}</p>
      </div>
      <div class="content-cell mdl-cell mdl-cell--12-col mdl-typography--caption">{link}</div>
    </div>
    """


def test_gemini_groups_known_thread_and_isolates_unknown(tmp_path):
    html = "<html><body>" + activity("One", "First answer", "Sep 5, 2026, 12:10:17 PM WIB", "thread-1") + activity("Two", "Second answer", "Sep 5, 2026, 12:11:17 PM WIB", "thread-1") + activity("Without an ID", "Answer", "Sep 5, 2026, 12:12:17 PM WIB", None) + "</body></html>"
    path = tmp_path / "MyActivity.html"
    path.write_text(html, encoding="utf-8")

    conversations = parse_gemini_file(path, tmp_path)

    assert len(conversations) == 2
    threaded = next(item for item in conversations if item.source_id == "thread-1")
    assert [message.role for message in threaded.messages] == ["user", "assistant", "user", "assistant"]
    assert threaded.messages[0].body == "One"
    assert threaded.messages[0].created_at.tzinfo == UTC
    assert threaded.messages[0].created_at.hour == 5  # 12:10 WIB converted to UTC
