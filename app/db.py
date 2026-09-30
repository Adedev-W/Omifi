from collections.abc import AsyncIterator
import sys

from sqlalchemy import event
from sqlalchemy import create_engine as create_sync_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings
from .models import Base


class Database:
    def __init__(self, settings: Settings):
        self.sync_mode = sys.version_info >= (3, 14)
        if self.sync_mode:
            database_url = settings.database_url.replace("sqlite+aiosqlite", "sqlite")
            self.engine = create_sync_engine(
                database_url,
                connect_args={"timeout": settings.busy_timeout_seconds},
                pool_pre_ping=True,
            )
            self.session_factory = sessionmaker(self.engine, expire_on_commit=False)
            event.listen(
                self.engine,
                "connect",
                lambda connection, record: self._configure_connection(connection, record, settings.busy_timeout_seconds),
            )
        else:
            self.engine = create_async_engine(
                settings.database_url_async,
                connect_args={"timeout": settings.busy_timeout_seconds},
                pool_pre_ping=True,
            )
            self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)
            event.listen(
                self.engine.sync_engine,
                "connect",
                lambda connection, record: self._configure_connection(connection, record, settings.busy_timeout_seconds),
            )

    @staticmethod
    def _configure_connection(dbapi_connection: object, _: object, busy_timeout_seconds: int) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute(f"PRAGMA busy_timeout={max(0, int(busy_timeout_seconds * 1000))}")
        cursor.close()

    async def create_schema(self) -> None:
        if self.sync_mode:
            Base.metadata.create_all(self.engine)
            return
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as session:
            yield session

    async def close(self) -> None:
        if self.sync_mode:
            self.engine.dispose()
        else:
            await self.engine.dispose()

    def session_context(self):
        if self.sync_mode:
            return _SyncSessionContext(self.session_factory())
        return self.session_factory()


class _SyncSessionContext:
    def __init__(self, session: Session):
        self._session = session
        self._compat = _AsyncSessionCompat(session)

    async def __aenter__(self) -> "_AsyncSessionCompat":
        return self._compat

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        if exc_type:
            self._session.rollback()
        self._session.close()


class _AsyncSessionCompat:
    """Small async-shaped facade for Python 3.14's broken aiosqlite worker."""

    def __init__(self, session: Session):
        self._session = session

    def add(self, instance):
        return self._session.add(instance)

    def add_all(self, instances):
        return self._session.add_all(instances)

    async def get(self, entity, ident):
        return self._session.get(entity, ident)

    async def execute(self, statement):
        return self._session.execute(statement)

    async def commit(self):
        self._session.commit()

    async def rollback(self):
        self._session.rollback()
