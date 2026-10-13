"""Snapshot export.

The ordering assertions here are regression guards for a bug that actually
shipped: Postgres defaults `DESC` to `NULLS FIRST`, so the two undated essays
(`fix`, `noop`) sorted to the *top* of the catalog instead of the bottom. The
ordering SQL is asserted without a database so the guard runs in unit tests.
"""

from typing import Any

import pytest

from rag.snapshot import _ORDER_BY


def test_order_by_puts_nulls_last() -> None:
    """Undated essays must land at the end of the catalog, not the start.

    Only the DESC clauses carry NULLS LAST; the final title tiebreak is a plain
    ASC and must not be constrained.
    """
    desc_clauses = [c for c in _ORDER_BY if ".desc(" in str(c) or " DESC" in str(c).upper()]
    assert len(desc_clauses) == 2, "expected date_year and date_month to be DESC"
    for clause in desc_clauses:
        # A bare DESC compiles to `x DESC` with no NULLS clause and would sort
        # undated essays to the top.
        assert "NULLS LAST" in str(clause).upper(), f"missing NULLS LAST in: {clause}"


def test_title_tiebreak_is_ascending_and_unconstrained() -> None:
    """The tiebreak must stay a plain ASC with no NULLS clause."""
    title = str(_ORDER_BY[-1])
    assert "NULLS" not in title.upper()
    assert " DESC" not in title.upper()


def test_order_by_is_newest_first() -> None:
    sql = " ".join(str(c).upper() for c in _ORDER_BY)
    assert "DATE_YEAR DESC" in sql
    assert "DATE_MONTH DESC" in sql


def test_order_by_ends_with_stable_title_tiebreak() -> None:
    """Two essays share a date; the title keeps their relative order stable."""
    assert str(_ORDER_BY[-1]).lower().endswith("title")


def test_year_only_dates_sort_after_month_known_dates() -> None:
    """`date_month` is null for "1993"; it must fall last within its own year.

    Order is date_year, date_month, title — so the second clause is the one
    that has to carry NULLS LAST for year-only essays to sort after the
    month-known ones from the same year.
    """
    date_month_clause = str(_ORDER_BY[1]).upper()
    assert "DATE_MONTH" in date_month_clause
    assert "NULLS LAST" in date_month_clause


@pytest.mark.parametrize("clause", list(_ORDER_BY))
def test_order_clauses_compile_to_sql(clause: Any) -> None:
    """Catches typos that would only surface at query time."""
    assert str(clause.compile(compile_kwargs={"literal_binds": True}))
