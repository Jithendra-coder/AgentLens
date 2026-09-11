"""PostgreSQL-backed storage for RagLens API keys and report summaries."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

POSTGRES_URL = os.environ.get(
    "AGENTLENS_DATABASE_URL",
    "postgresql://postgres:postgres@127.0.0.1:5432/postgres",
)

SQLITE_FALLBACK_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "raglens_fallback.db",
)


class RagLensDatabase:
    """Stores and retrieves per-API-key RAG execution reports in PostgreSQL."""

    def __init__(self) -> None:
        self.use_postgres = False
        self._init_db()

    def _init_db(self) -> None:
        """Initialize PostgreSQL table or fallback to SQLite."""
        try:
            import psycopg

            with psycopg.connect(POSTGRES_URL, connect_timeout=2) as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS raglens_reports (
                            api_key VARCHAR(64) PRIMARY KEY,
                            trace_id VARCHAR(64) NOT NULL,
                            query TEXT NOT NULL,
                            total_latency_ms REAL NOT NULL,
                            total_tokens INTEGER NOT NULL,
                            cost_usd REAL NOT NULL,
                            status VARCHAR(32) NOT NULL,
                            summary JSONB NOT NULL,
                            pipeline_spans JSONB NOT NULL,
                            diagnosis JSONB NOT NULL,
                            chunks JSONB NOT NULL,
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                        );
                        CREATE INDEX IF NOT EXISTS idx_raglens_reports_trace ON raglens_reports (trace_id);
                        """
                    )
                conn.commit()
            self.use_postgres = True
        except Exception:
            # Fallback to local SQLite if PostgreSQL is unreachable
            self.use_postgres = False
            with sqlite3.connect(SQLITE_FALLBACK_PATH) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS raglens_reports (
                        api_key TEXT PRIMARY KEY,
                        trace_id TEXT NOT NULL,
                        query TEXT NOT NULL,
                        total_latency_ms REAL NOT NULL,
                        total_tokens INTEGER NOT NULL,
                        cost_usd REAL NOT NULL,
                        status TEXT NOT NULL,
                        summary TEXT NOT NULL,
                        pipeline_spans TEXT NOT NULL,
                        diagnosis TEXT NOT NULL,
                        chunks TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """
                )
                conn.commit()

    def save_report(
        self,
        api_key: str,
        trace_id: str,
        query: str,
        total_latency_ms: float,
        total_tokens: int,
        cost_usd: float,
        status: str,
        summary: Dict[str, Any],
        pipeline_spans: List[Dict[str, Any]],
        diagnosis: Dict[str, Any],
        chunks: List[Dict[str, Any]],
    ) -> bool:
        """Save a report under a unique API key."""
        now_iso = datetime.now(timezone.utc).isoformat()
        if self.use_postgres:
            try:
                import psycopg

                with psycopg.connect(POSTGRES_URL, connect_timeout=2) as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO raglens_reports (
                                api_key, trace_id, query, total_latency_ms, total_tokens,
                                cost_usd, status, summary, pipeline_spans, diagnosis, chunks, created_at
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (api_key) DO UPDATE SET
                                query = EXCLUDED.query,
                                total_latency_ms = EXCLUDED.total_latency_ms,
                                total_tokens = EXCLUDED.total_tokens,
                                cost_usd = EXCLUDED.cost_usd,
                                status = EXCLUDED.status,
                                summary = EXCLUDED.summary,
                                pipeline_spans = EXCLUDED.pipeline_spans,
                                diagnosis = EXCLUDED.diagnosis,
                                chunks = EXCLUDED.chunks;
                            """,
                            (
                                api_key,
                                trace_id,
                                query,
                                total_latency_ms,
                                total_tokens,
                                cost_usd,
                                status,
                                json.dumps(summary),
                                json.dumps(pipeline_spans),
                                json.dumps(diagnosis),
                                json.dumps(chunks),
                                now_iso,
                            ),
                        )
                    conn.commit()
                return True
            except Exception:
                pass

        # Fallback to SQLite
        try:
            with sqlite3.connect(SQLITE_FALLBACK_PATH) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO raglens_reports (
                        api_key, trace_id, query, total_latency_ms, total_tokens,
                        cost_usd, status, summary, pipeline_spans, diagnosis, chunks, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        api_key,
                        trace_id,
                        query,
                        total_latency_ms,
                        total_tokens,
                        cost_usd,
                        status,
                        json.dumps(summary),
                        json.dumps(pipeline_spans),
                        json.dumps(diagnosis),
                        json.dumps(chunks),
                        now_iso,
                    ),
                )
                conn.commit()
            return True
        except Exception:
            return False

    def get_report(self, api_key: str) -> Optional[Dict[str, Any]]:
        """Retrieve a report by its unique API key."""
        if self.use_postgres:
            try:
                import psycopg

                with psycopg.connect(POSTGRES_URL, connect_timeout=2) as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            SELECT api_key, trace_id, query, total_latency_ms, total_tokens,
                                   cost_usd, status, summary, pipeline_spans, diagnosis, chunks, created_at
                            FROM raglens_reports WHERE api_key = %s
                            """,
                            (api_key,),
                        )
                        row = cur.fetchone()
                        if row:
                            return {
                                "api_key": row[0],
                                "trace_id": row[1],
                                "query": row[2],
                                "total_latency_ms": row[3],
                                "total_tokens": row[4],
                                "cost_usd": row[5],
                                "status": row[6],
                                "summary": row[7] if isinstance(row[7], dict) else json.loads(row[7]),
                                "pipeline_spans": row[8] if isinstance(row[8], list) else json.loads(row[8]),
                                "diagnosis": row[9] if isinstance(row[9], dict) else json.loads(row[9]),
                                "chunks": row[10] if isinstance(row[10], list) else json.loads(row[10]),
                                "created_at": str(row[11]),
                                "storage": "PostgreSQL",
                            }
            except Exception:
                pass

        # Fallback to SQLite
        try:
            with sqlite3.connect(SQLITE_FALLBACK_PATH) as conn:
                cur = conn.execute(
                    """
                    SELECT api_key, trace_id, query, total_latency_ms, total_tokens,
                           cost_usd, status, summary, pipeline_spans, diagnosis, chunks, created_at
                    FROM raglens_reports WHERE api_key = ?
                    """,
                    (api_key,),
                )
                row = cur.fetchone()
                if row:
                    return {
                        "api_key": row[0],
                        "trace_id": row[1],
                        "query": row[2],
                        "total_latency_ms": row[3],
                        "total_tokens": row[4],
                        "cost_usd": row[5],
                        "status": row[6],
                        "summary": json.loads(row[7]),
                        "pipeline_spans": json.loads(row[8]),
                        "diagnosis": json.loads(row[9]),
                        "chunks": json.loads(row[10]),
                        "created_at": row[11],
                        "storage": "SQLite",
                    }
        except Exception:
            return None
        return None

    def get_recent_reports(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent reports."""
        reports = []
        if self.use_postgres:
            try:
                import psycopg

                with psycopg.connect(POSTGRES_URL, connect_timeout=2) as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            SELECT api_key, trace_id, query, total_latency_ms, total_tokens,
                                   cost_usd, status, summary, pipeline_spans, diagnosis, chunks, created_at
                            FROM raglens_reports ORDER BY created_at DESC LIMIT %s
                            """,
                            (limit,),
                        )
                        for row in cur.fetchall():
                            reports.append({
                                "api_key": row[0],
                                "trace_id": row[1],
                                "query": row[2],
                                "total_latency_ms": row[3],
                                "total_tokens": row[4],
                                "cost_usd": row[5],
                                "status": row[6],
                                "summary": row[7] if isinstance(row[7], dict) else json.loads(row[7]),
                                "pipeline_spans": row[8] if isinstance(row[8], list) else json.loads(row[8]),
                                "diagnosis": row[9] if isinstance(row[9], dict) else json.loads(row[9]),
                                "chunks": row[10] if isinstance(row[10], list) else json.loads(row[10]),
                                "created_at": str(row[11]),
                                "storage": "PostgreSQL",
                            })
                        return reports
            except Exception:
                pass

        try:
            with sqlite3.connect(SQLITE_FALLBACK_PATH) as conn:
                cur = conn.execute(
                    """
                    SELECT api_key, trace_id, query, total_latency_ms, total_tokens,
                           cost_usd, status, summary, pipeline_spans, diagnosis, chunks, created_at
                    FROM raglens_reports ORDER BY created_at DESC LIMIT ?
                    """,
                    (limit,),
                )
                for row in cur.fetchall():
                    reports.append({
                        "api_key": row[0],
                        "trace_id": row[1],
                        "query": row[2],
                        "total_latency_ms": row[3],
                        "total_tokens": row[4],
                        "cost_usd": row[5],
                        "status": row[6],
                        "summary": json.loads(row[7]),
                        "pipeline_spans": json.loads(row[8]),
                        "diagnosis": json.loads(row[9]),
                        "chunks": json.loads(row[10]),
                        "created_at": row[11],
                        "storage": "SQLite",
                    })
        except Exception:
            pass
        return reports


db = RagLensDatabase()
