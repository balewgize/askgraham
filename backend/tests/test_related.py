"""Related-essays retrieval: the centroid arithmetic and the route contract.

The live query needs Postgres and a built index, so it is exercised through the
API rather than here. What is pinned is the part that must be right for the
ranking to mean anything: the centroid, and that the route is served.
"""

import pytest
from fastapi import FastAPI

from rag.related import RelatedEssay, centroid

from .conftest import served_paths


def test_centroid_is_the_element_wise_mean() -> None:
    assert centroid([[1.0, 2.0], [3.0, 4.0]]) == [2.0, 3.0]


def test_centroid_of_one_vector_is_itself() -> None:
    assert centroid([[0.5, -1.0, 2.0]]) == [0.5, -1.0, 2.0]


def test_centroid_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="no vectors"):
        centroid([])


def test_centroid_rejects_ragged_vectors() -> None:
    """A mismatch means two models' vectors share the index; do not paper over it."""
    with pytest.raises(ValueError, match="mismatched"):
        centroid([[1.0, 2.0], [1.0]])


def test_related_essay_rounds_similarity() -> None:
    essay = RelatedEssay(
        slug="ds",
        title="Do Things that Don't Scale",
        date="July 2013",
        reading_time_min=19,
        similarity=0.91234567,
        start_paragraph=0,
        end_paragraph=4,
    )
    assert essay.as_dict()["similarity"] == 0.9123


def test_related_route_is_in_the_api_contract(app: FastAPI) -> None:
    assert "/api/v1/essays/{slug}/related" in served_paths(app)
