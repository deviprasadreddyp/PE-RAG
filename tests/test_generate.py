"""Stage 14 tests: single-call generation via an injected fake Generator (no network/key)."""

from src.generation.generate import generate
from src.schemas import AnswerBody, PromptBundle


class FakeGenerator:
    """Records the prompt it was given and returns a canned structured AnswerBody. ONE call."""

    def __init__(self):
        self.calls = 0
        self.seen: PromptBundle | None = None

    def generate(self, prompt):
        self.calls += 1
        self.seen = prompt
        return AnswerBody(
            executive_summary="Apple's net sales rose.",
            supporting_evidence="Net sales were $391,035 million [E1].",
            citations=["E1"],
            confidence="High",
        )


def _prompt():
    return PromptBundle(system="SYS", user="<context>\nE1: [t]\nbody\n</context>\n\nQuestion: q",
                        prompt_version="v1")


def test_generate_delegates_and_returns_answerbody():
    fake = FakeGenerator()
    out = generate(_prompt(), generator=fake)
    assert isinstance(out, AnswerBody)
    assert out.citations == ["E1"] and out.confidence == "High"


def test_exactly_one_call():
    fake = FakeGenerator()
    generate(_prompt(), generator=fake)
    assert fake.calls == 1                      # the one-LLM-call constraint


def test_generator_receives_full_prompt():
    fake = FakeGenerator()
    generate(_prompt(), generator=fake)
    assert fake.seen.system == "SYS" and "Question: q" in fake.seen.user
