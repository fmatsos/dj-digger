"""Bounded worker fan-out: at most N in flight, results consumed serially."""

import threading
import time
from collections.abc import Iterator

import pytest

from dj_digger.core.concurrency import bounded_results


def test_at_most_the_configured_number_of_tasks_run_concurrently() -> None:
    workers = 3
    in_flight = 0
    peak = 0
    guard = threading.Lock()

    def work(item: int) -> int:
        nonlocal in_flight, peak
        with guard:
            in_flight += 1
            peak = max(peak, in_flight)
        time.sleep(0.01)
        with guard:
            in_flight -= 1
        return item

    consumed = list(bounded_results(range(12), work, workers=workers))

    assert sorted(consumed) == list(range(12))
    assert peak <= workers


def test_every_item_is_processed_exactly_once() -> None:
    seen: list[int] = []
    guard = threading.Lock()

    def work(item: int) -> int:
        with guard:
            seen.append(item)
        return item * 2

    results = list(bounded_results(range(50), work, workers=4))

    assert sorted(seen) == list(range(50))
    assert sorted(results) == [item * 2 for item in range(50)]


def test_results_are_consumed_in_the_calling_thread() -> None:
    """Callers persist to SQLite from the consumer loop, which must stay single-threaded."""
    caller = threading.get_ident()
    consumer_threads: set[int] = set()

    for _ in bounded_results(range(20), lambda item: item, workers=5):
        consumer_threads.add(threading.get_ident())

    assert consumer_threads == {caller}


def test_a_failing_task_propagates_to_the_caller() -> None:
    def work(item: int) -> int:
        if item == 7:
            raise RuntimeError("task exploded")
        return item

    with pytest.raises(RuntimeError, match="task exploded"):
        list(bounded_results(range(20), work, workers=2))


def test_an_empty_input_yields_nothing_and_starts_no_worker() -> None:
    started = 0

    def work(item: int) -> int:
        nonlocal started
        started += 1
        return item

    assert list(bounded_results([], work, workers=4)) == []
    assert started == 0


def test_abandoning_the_iterator_does_not_leak_running_workers() -> None:
    running: set[int] = set()
    guard = threading.Lock()

    def work(item: int) -> int:
        with guard:
            running.add(item)
        time.sleep(0.01)
        with guard:
            running.discard(item)
        return item

    stream: Iterator[int] = bounded_results(range(30), work, workers=3)
    next(stream)
    stream.close()

    assert running == set()


def test_a_non_positive_worker_count_is_rejected() -> None:
    with pytest.raises(ValueError, match="positive"):
        list(bounded_results([1], lambda item: item, workers=0))
