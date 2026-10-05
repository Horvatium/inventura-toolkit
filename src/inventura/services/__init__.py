"""Use cases that combine the core rules with the database."""

from sqlalchemy import Insert, insert
from sqlalchemy.orm import DeclarativeBase


def bulk_insert(model: type[DeclarativeBase]) -> Insert:
    """An INSERT for many rows at once.

    By default the ORM leaves out None values, so rows with and without a batch would have
    different columns and be sent one by one; render_nulls keeps them in a single batch.
    """
    return insert(model).execution_options(render_nulls=True)


class NotFoundError(LookupError):
    """The requested record does not exist."""


class ConflictError(RuntimeError):
    """The action contradicts the current state, e.g. documents already exist."""
