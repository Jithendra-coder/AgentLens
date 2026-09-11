"""Unit tests for InMemoryBenchmarkRepository lifecycle."""

from __future__ import annotations

from uuid import uuid4

from agentlens.benchmarking.models import (
    ModelBenchmark,
    ModelBenchmarkRun,
    ModelQualification,
)
from agentlens.benchmarking.repository import InMemoryBenchmarkRepository


def test_in_memory_benchmark_repository_lifecycle() -> None:
    repo = InMemoryBenchmarkRepository()
    bench_id = uuid4()

    bench = ModelBenchmark(
        benchmark_id=bench_id,
        project_id="proj-bench-repo",
        name="Reasoning Core Suite",
    )

    # 1. Save & get benchmark
    saved = repo.save_benchmark(bench)
    assert saved.benchmark_id == bench_id

    fetched = repo.get_benchmark(bench_id)
    assert fetched is not None
    assert fetched.name == "Reasoning Core Suite"

    # 2. List benchmarks
    bench_list = repo.list_benchmarks("proj-bench-repo")
    assert len(bench_list) == 1

    # 3. Record & list runs
    run = ModelBenchmarkRun(
        run_id=uuid4(),
        benchmark_id=bench_id,
        project_id="proj-bench-repo",
        model_name="gpt-4o",
        overall_score=0.94,
    )
    repo.record_run(run)
    runs = repo.list_runs("proj-bench-repo", benchmark_id=bench_id)
    assert len(runs) == 1
    assert runs[0].model_name == "gpt-4o"

    # 4. Save & list qualifications
    qual = ModelQualification(
        project_id="proj-bench-repo",
        model_name="gpt-4o",
        is_qualified=True,
    )
    repo.save_qualification(qual)
    quals = repo.list_qualifications("proj-bench-repo")
    assert len(quals) == 1
    assert quals[0].is_qualified is True

    # 5. Delete benchmark
    assert repo.delete_benchmark(bench_id) is True
    assert repo.get_benchmark(bench_id) is None
