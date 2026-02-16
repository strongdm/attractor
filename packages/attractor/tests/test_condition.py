from attractor.condition import evaluate_condition
from attractor.context import Context
from attractor.outcome import Outcome, StageStatus


def test_condition_supports_context_outcome_and_preferred_label():
    context = Context({"approved": "yes"})
    outcome = Outcome(status=StageStatus.SUCCESS, preferred_label="next")

    assert evaluate_condition("context.approved = yes", context, outcome, preferred_label=None)
    assert evaluate_condition("outcome = success", context, outcome, preferred_label=None)
    assert evaluate_condition("preferred_label = next", context, outcome, preferred_label="next")
    assert evaluate_condition(
        "context.approved = yes && outcome != failure",
        context,
        outcome,
        preferred_label="next",
    )
    assert not evaluate_condition(
        "context.approved != yes", context, outcome, preferred_label=None
    )
