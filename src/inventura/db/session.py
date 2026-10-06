"""Engine and session factory."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

CONNECT_TIMEOUT_SECONDS = 10


def make_engine(url: str) -> Engine:
    # A bounded connect timeout: an unreachable database fails fast instead of hanging.
    return create_engine(
        url, pool_pre_ping=True, connect_args={"connect_timeout": CONNECT_TIMEOUT_SECONDS}
    )


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
