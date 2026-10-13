"""Chat prompt assembly.

The model call needs the network, so it is verified live. These guard the part
that must be right for citations to be checkable: the token the model is told to
cite, and the message shape it receives.
"""

from llm.generation import Source, Turn, build_context, build_messages


def _source(slug: str = "ds", start: int = 0, end: int = 4) -> Source:
    return Source(
        slug=slug,
        title="Do Things that Don't Scale",
        start_paragraph=start,
        end_paragraph=end,
        text="One of the most common types of advice we give at Y Combinator...",
    )


def test_citation_token_is_slug_and_paragraph_range() -> None:
    assert _source(slug="ds", start=0, end=4).citation == "ds#0-4"


def test_context_labels_each_source_with_its_token() -> None:
    context = build_context([_source(slug="ds", start=0, end=4)])
    assert "[ds#0-4] Do Things that Don't Scale" in context
    assert "Y Combinator" in context


def test_messages_start_with_the_system_prompt() -> None:
    messages = build_messages("How do I find users?", [], [_source()])
    assert messages[0]["role"] == "system"
    assert "only tokens that appear in the sources" in messages[0]["content"]


def test_question_and_sources_are_the_final_user_turn() -> None:
    messages = build_messages("How do I find users?", [], [_source()])
    final = messages[-1]
    assert final["role"] == "user"
    assert "Sources:" in final["content"]
    assert "Question: How do I find users?" in final["content"]


def test_history_is_echoed_between_system_and_question() -> None:
    history = [
        Turn("user", "What is ramen profitable?"),
        Turn("assistant", "It means breaking even enough to cover founders."),
    ]
    messages = build_messages("What about picking ideas?", history, [_source()])
    roles = [m["role"] for m in messages]
    assert roles == ["system", "user", "assistant", "user"]
    assert messages[1]["content"] == "What is ramen profitable?"


def test_blank_history_turns_are_dropped() -> None:
    messages = build_messages("q", [Turn("user", "   ")], [_source()])
    assert [m["role"] for m in messages] == ["system", "user"]
