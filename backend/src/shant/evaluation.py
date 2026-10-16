"""Scoring the Judge: per-tag precision, recall and F1 against hand labels."""

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import mean

from shant.tags import Tag


@dataclass(frozen=True)
class TagScore:
    precision: float
    recall: float
    f1: float
    support: int  # lines whose hand label includes this tag


def score_tags(
    expected: Sequence[frozenset[Tag]], predicted: Sequence[frozenset[Tag]]
) -> dict[Tag, TagScore]:
    pairs = list(zip(expected, predicted, strict=True))
    scores = {}
    for tag in Tag:
        true_pos = sum(tag in want and tag in got for want, got in pairs)
        false_pos = sum(tag not in want and tag in got for want, got in pairs)
        false_neg = sum(tag in want and tag not in got for want, got in pairs)
        precision = true_pos / (true_pos + false_pos) if true_pos + false_pos else 0.0
        recall = true_pos / (true_pos + false_neg) if true_pos + false_neg else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        scores[tag] = TagScore(precision, recall, f1, true_pos + false_neg)
    return scores


def macro_f1(scores: dict[Tag, TagScore]) -> float:
    """Mean F1 over the tags that appear in the hand labels."""
    labelled = [score.f1 for score in scores.values() if score.support]
    return mean(labelled) if labelled else 0.0
