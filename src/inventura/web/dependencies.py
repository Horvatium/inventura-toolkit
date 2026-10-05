"""Request-scoped dependencies."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from inventura.io.column_mapping import ColumnMapping
from inventura.settings import Settings


def get_session(request: Request) -> Iterator[Session]:
    with request.app.state.session_factory() as session:
        yield session


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_column_mapping(request: Request) -> ColumnMapping:
    mapping: ColumnMapping = request.app.state.column_mapping
    return mapping


SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
MappingDep = Annotated[ColumnMapping, Depends(get_column_mapping)]
