"""User and session management implementations for Enterprise Authentication."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol, cast
from uuid import UUID, uuid4

from sqlalchemy import and_, create_engine, select, update
from sqlalchemy.engine import Engine

from agentlens.storage.config import DatabaseConfig
from agentlens.storage.models import user_sessions, users


@dataclass(frozen=True, slots=True)
class User:
    user_id: UUID
    email: str
    name: str
    auth_provider: str = "local"
    external_id: str | None = None
    created_at: datetime = datetime.now(UTC)
    status: str = "active"


@dataclass(frozen=True, slots=True)
class UserSession:
    session_id: UUID
    user_id: UUID
    refresh_token_hash: str
    expires_at: datetime
    created_at: datetime
    revoked_at: datetime | None = None
    user_agent: str | None = None

    @property
    def is_valid(self) -> bool:
        now = datetime.now(UTC)
        return self.revoked_at is None and now < self.expires_at


class UserRepository(Protocol):
    def get_or_create_user(
        self,
        email: str,
        name: str,
        auth_provider: str = "local",
        external_id: str | None = None,
    ) -> User: ...

    def get_user_by_id(self, user_id: UUID) -> User | None: ...

    def create_session(
        self,
        user_id: UUID,
        refresh_token_hash: str,
        expires_in_seconds: int = 86400 * 30,
        user_agent: str | None = None,
    ) -> UserSession: ...

    def get_session(self, refresh_token_hash: str) -> UserSession | None: ...

    def revoke_session(self, session_id: UUID) -> bool: ...


class InMemoryUserRepository:
    """In-memory user and session repository for tests."""

    def __init__(self) -> None:
        self._users: dict[UUID, User] = {}
        self._users_by_email: dict[str, UUID] = {}
        self._sessions: dict[UUID, UserSession] = {}
        self._sessions_by_hash: dict[str, UUID] = {}

    def get_or_create_user(
        self,
        email: str,
        name: str,
        auth_provider: str = "local",
        external_id: str | None = None,
    ) -> User:
        norm_email = email.strip().lower()
        if norm_email in self._users_by_email:
            uid = self._users_by_email[norm_email]
            return self._users[uid]

        user = User(
            user_id=uuid4(),
            email=norm_email,
            name=name,
            auth_provider=auth_provider,
            external_id=external_id,
            created_at=datetime.now(UTC),
        )
        self._users[user.user_id] = user
        self._users_by_email[norm_email] = user.user_id
        return user

    def get_user_by_id(self, user_id: UUID) -> User | None:
        return self._users.get(user_id)

    def create_session(
        self,
        user_id: UUID,
        refresh_token_hash: str,
        expires_in_seconds: int = 86400 * 30,
        user_agent: str | None = None,
    ) -> UserSession:
        now = datetime.now(UTC)
        session = UserSession(
            session_id=uuid4(),
            user_id=user_id,
            refresh_token_hash=refresh_token_hash,
            expires_at=now + timedelta(seconds=expires_in_seconds),
            created_at=now,
            user_agent=user_agent,
        )
        self._sessions[session.session_id] = session
        self._sessions_by_hash[refresh_token_hash] = session.session_id
        return session

    def get_session(self, refresh_token_hash: str) -> UserSession | None:
        sid = self._sessions_by_hash.get(refresh_token_hash)
        if sid is None:
            return None
        session = self._sessions.get(sid)
        if session is None or not session.is_valid:
            return None
        return session

    def revoke_session(self, session_id: UUID) -> bool:
        sess = self._sessions.get(session_id)
        if sess is None:
            return False
        revoked = UserSession(
            session_id=sess.session_id,
            user_id=sess.user_id,
            refresh_token_hash=sess.refresh_token_hash,
            expires_at=sess.expires_at,
            created_at=sess.created_at,
            revoked_at=datetime.now(UTC),
            user_agent=sess.user_agent,
        )
        self._sessions[session_id] = revoked
        return True


class PostgresUserRepository:
    """PostgreSQL user and session repository."""

    def __init__(self, config: DatabaseConfig, *, engine: Engine | None = None) -> None:
        self.engine = engine or create_engine(
            config.sqlalchemy_url,
            pool_pre_ping=True,
            pool_size=config.pool_size,
            max_overflow=config.max_overflow,
            pool_timeout=config.pool_timeout,
        )

    def get_or_create_user(
        self,
        email: str,
        name: str,
        auth_provider: str = "local",
        external_id: str | None = None,
    ) -> User:
        norm_email = email.strip().lower()
        now = datetime.now(UTC)

        with self.engine.begin() as conn:
            row = conn.execute(
                select(users).where(users.c.email == norm_email)
            ).mappings().one_or_none()
            if row is not None:
                return User(
                    user_id=cast(UUID, row["user_id"]),
                    email=str(row["email"]),
                    name=str(row["name"]),
                    auth_provider=str(row["auth_provider"]),
                    external_id=cast(str | None, row["external_id"]),
                    created_at=cast(datetime, row["created_at"]),
                    status=str(row["status"]),
                )

            new_id = uuid4()
            conn.execute(
                users.insert().values(
                    user_id=new_id,
                    email=norm_email,
                    name=name,
                    auth_provider=auth_provider,
                    external_id=external_id,
                    created_at=now,
                    status="active",
                )
            )

        return User(
            user_id=new_id,
            email=norm_email,
            name=name,
            auth_provider=auth_provider,
            external_id=external_id,
            created_at=now,
            status="active",
        )

    def get_user_by_id(self, user_id: UUID) -> User | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(users).where(users.c.user_id == user_id)
            ).mappings().one_or_none()
            if row is None:
                return None
            return User(
                user_id=cast(UUID, row["user_id"]),
                email=str(row["email"]),
                name=str(row["name"]),
                auth_provider=str(row["auth_provider"]),
                external_id=cast(str | None, row["external_id"]),
                created_at=cast(datetime, row["created_at"]),
                status=str(row["status"]),
            )

    def create_session(
        self,
        user_id: UUID,
        refresh_token_hash: str,
        expires_in_seconds: int = 86400 * 30,
        user_agent: str | None = None,
    ) -> UserSession:
        now = datetime.now(UTC)
        session_id = uuid4()
        expires_at = now + timedelta(seconds=expires_in_seconds)

        with self.engine.begin() as conn:
            conn.execute(
                user_sessions.insert().values(
                    session_id=session_id,
                    user_id=user_id,
                    refresh_token_hash=refresh_token_hash,
                    expires_at=expires_at,
                    created_at=now,
                    user_agent=user_agent,
                )
            )

        return UserSession(
            session_id=session_id,
            user_id=user_id,
            refresh_token_hash=refresh_token_hash,
            expires_at=expires_at,
            created_at=now,
            user_agent=user_agent,
        )

    def get_session(self, refresh_token_hash: str) -> UserSession | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                select(user_sessions).where(
                    and_(
                        user_sessions.c.refresh_token_hash == refresh_token_hash,
                        user_sessions.c.revoked_at.is_(None),
                    )
                )
            ).mappings().one_or_none()
            if row is None:
                return None
            return UserSession(
                session_id=cast(UUID, row["session_id"]),
                user_id=cast(UUID, row["user_id"]),
                refresh_token_hash=str(row["refresh_token_hash"]),
                expires_at=cast(datetime, row["expires_at"]),
                created_at=cast(datetime, row["created_at"]),
                revoked_at=cast(datetime | None, row["revoked_at"]),
                user_agent=cast(str | None, row["user_agent"]),
            )

    def revoke_session(self, session_id: UUID) -> bool:
        now = datetime.now(UTC)
        with self.engine.begin() as conn:
            res = conn.execute(
                update(user_sessions)
                .where(user_sessions.c.session_id == session_id)
                .values(revoked_at=now)
            )
            return bool(int(getattr(res, "rowcount", 0) or 0) > 0)
