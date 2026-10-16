import pytest

from shant.evaluation import TagScore, macro_f1, score_tags
from shant.tags import Tag

A, D = Tag.APOLOGISED, Tag.DISMISSIVE


def test_perfect_predictions_score_1() -> None:
    labels = [frozenset({A}), frozenset({D}), frozenset()]
    scores = score_tags(labels, labels)
    assert scores[A] == TagScore(precision=1.0, recall=1.0, f1=1.0, support=1)
    assert macro_f1(scores) == 1.0


def test_precision_recall_and_f1_from_counts() -> None:
    expected = [frozenset({A}), frozenset({A}), frozenset(), frozenset()]
    predicted = [frozenset({A}), frozenset(), frozenset({A}), frozenset()]
    score = score_tags(expected, predicted)[A]
    assert (score.precision, score.recall, score.f1, score.support) == (0.5, 0.5, 0.5, 2)


def test_a_tag_never_predicted_scores_zero_without_dividing_by_zero() -> None:
    score = score_tags([frozenset({A})], [frozenset()])[A]
    assert score == TagScore(precision=0.0, recall=0.0, f1=0.0, support=1)


def test_macro_f1_ignores_tags_that_never_appear_in_the_labels() -> None:
    expected = [frozenset({A}), frozenset()]
    predicted = [frozenset({A}), frozenset({D})]
    scores = score_tags(expected, predicted)
    assert scores[D].support == 0
    assert macro_f1(scores) == 1.0


def test_mismatched_lengths_are_an_error() -> None:
    with pytest.raises(ValueError):
        score_tags([frozenset()], [])
