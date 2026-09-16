from promptchived.services.search import _rrf


def row(message_id: str) -> dict:
    return {"message_id": message_id, "snippet": message_id, "score": 0.5}


def test_rrf_rewards_results_present_in_both_rankings():
    lexical = [row("both"), row("lexical")]
    semantic = [row("semantic"), row("both")]
    ranked = _rrf(lexical, semantic, k=60)
    assert ranked[0]["message_id"] == "both"
    assert len(ranked) == 3
