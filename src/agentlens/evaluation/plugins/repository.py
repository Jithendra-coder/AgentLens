"""Custom evaluator plugin repository ."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Protocol, cast
from uuid import UUID

from sqlalchemy import and_, create_engine, desc, select
from sqlalchemy.engine import Engine

from agentlens.evaluation.plugins.models import CustomEvaluatorPlugin
from agentlens.storage.config import DatabaseConfig
from agentlens.storage.models import custom_evaluator_plugins


class CustomEvaluatorRepository(Protocol):
    """Protocol for persisting and retrieving custom evaluator plugins."""

    def save_plugin(self, plugin: CustomEvaluatorPlugin) -> CustomEvaluatorPlugin: ...

    def get_plugin(self, plugin_id: UUID) -> CustomEvaluatorPlugin | None: ...

    def find_by_name(
        self,
        project_id: str,
        name: str,
        version: str | None = None,
    ) -> CustomEvaluatorPlugin | None: ...

    def list_plugins(self, project_id: str) -> Sequence[CustomEvaluatorPlugin]: ...

    def delete_plugin(self, plugin_id: UUID) -> bool: ...


class InMemoryCustomEvaluatorRepository:
    """In-memory custom evaluator repository for tests and local development."""

    def __init__(self) -> None:
        self._plugins: dict[UUID, CustomEvaluatorPlugin] = {}

    def save_plugin(self, plugin: CustomEvaluatorPlugin) -> CustomEvaluatorPlugin:
        self._plugins[plugin.plugin_id] = plugin
        return plugin

    def get_plugin(self, plugin_id: UUID) -> CustomEvaluatorPlugin | None:
        return self._plugins.get(plugin_id)

    def find_by_name(
        self,
        project_id: str,
        name: str,
        version: str | None = None,
    ) -> CustomEvaluatorPlugin | None:
        matches = [
            p
            for p in self._plugins.values()
            if p.project_id == project_id
            and p.name == name
            and (version is None or p.version == version)
        ]
        if not matches:
            return None
        return sorted(matches, key=lambda x: x.created_at, reverse=True)[0]

    def list_plugins(self, project_id: str) -> Sequence[CustomEvaluatorPlugin]:
        return [p for p in self._plugins.values() if p.project_id == project_id]

    def delete_plugin(self, plugin_id: UUID) -> bool:
        if plugin_id in self._plugins:
            del self._plugins[plugin_id]
            return True
        return False


class PostgresCustomEvaluatorRepository:
    """PostgreSQL storage repository for custom evaluator plugins."""

    def __init__(self, config: DatabaseConfig, engine: Engine | None = None) -> None:
        self._config = config
        self._engine = engine or create_engine(config.url, pool_pre_ping=True)

    def save_plugin(self, plugin: CustomEvaluatorPlugin) -> CustomEvaluatorPlugin:
        with self._engine.begin() as conn:
            conn.execute(
                custom_evaluator_plugins.insert().values(
                    plugin_id=plugin.plugin_id,
                    project_id=plugin.project_id,
                    name=plugin.name,
                    version=plugin.version,
                    evaluator_type=plugin.evaluator_type,
                    description=plugin.description,
                    code_body=plugin.code_body,
                    schema_parameters=plugin.schema_parameters,
                    created_at=plugin.created_at,
                    updated_at=plugin.updated_at,
                )
            )
        return plugin

    def get_plugin(self, plugin_id: UUID) -> CustomEvaluatorPlugin | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(custom_evaluator_plugins).where(
                    custom_evaluator_plugins.c.plugin_id == plugin_id
                )
            ).mappings().first()
            if row is None:
                return None
            return CustomEvaluatorPlugin(
                plugin_id=cast(UUID, row["plugin_id"]),
                project_id=cast(str, row["project_id"]),
                name=cast(str, row["name"]),
                version=cast(str, row["version"]),
                evaluator_type=cast(str, row["evaluator_type"]),
                description=cast(str | None, row["description"]),
                code_body=cast(str, row["code_body"]),
                schema_parameters=cast(dict[str, Any], row["schema_parameters"] or {}),
                created_at=cast(datetime, row["created_at"]),
                updated_at=cast(datetime, row["updated_at"]),
            )

    def find_by_name(
        self,
        project_id: str,
        name: str,
        version: str | None = None,
    ) -> CustomEvaluatorPlugin | None:
        with self._engine.connect() as conn:
            clauses = [
                custom_evaluator_plugins.c.project_id == project_id,
                custom_evaluator_plugins.c.name == name,
            ]
            if version is not None:
                clauses.append(custom_evaluator_plugins.c.version == version)

            row = conn.execute(
                select(custom_evaluator_plugins)
                .where(and_(*clauses))
                .order_by(desc(custom_evaluator_plugins.c.created_at))
            ).mappings().first()
            if row is None:
                return None
            return CustomEvaluatorPlugin(
                plugin_id=cast(UUID, row["plugin_id"]),
                project_id=cast(str, row["project_id"]),
                name=cast(str, row["name"]),
                version=cast(str, row["version"]),
                evaluator_type=cast(str, row["evaluator_type"]),
                description=cast(str | None, row["description"]),
                code_body=cast(str, row["code_body"]),
                schema_parameters=cast(dict[str, Any], row["schema_parameters"] or {}),
                created_at=cast(datetime, row["created_at"]),
                updated_at=cast(datetime, row["updated_at"]),
            )

    def list_plugins(self, project_id: str) -> Sequence[CustomEvaluatorPlugin]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(custom_evaluator_plugins)
                .where(custom_evaluator_plugins.c.project_id == project_id)
                .order_by(desc(custom_evaluator_plugins.c.created_at))
            ).mappings().all()

            return [
                CustomEvaluatorPlugin(
                    plugin_id=cast(UUID, r["plugin_id"]),
                    project_id=cast(str, r["project_id"]),
                    name=cast(str, r["name"]),
                    version=cast(str, r["version"]),
                    evaluator_type=cast(str, r["evaluator_type"]),
                    description=cast(str | None, r["description"]),
                    code_body=cast(str, r["code_body"]),
                    schema_parameters=cast(dict[str, Any], r["schema_parameters"] or {}),
                    created_at=cast(datetime, r["created_at"]),
                    updated_at=cast(datetime, r["updated_at"]),
                )
                for r in rows
            ]

    def delete_plugin(self, plugin_id: UUID) -> bool:
        with self._engine.begin() as conn:
            res = conn.execute(
                custom_evaluator_plugins.delete().where(
                    custom_evaluator_plugins.c.plugin_id == plugin_id
                )
            )
            return bool(res.rowcount and res.rowcount > 0)
