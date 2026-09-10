"""Bounded worker fan-out shared by the analysis and duplicate pipelines.

Both pipelines compute independent per-track work concurrently but must persist
serially: the parent process is the sole SQLite writer. Yielding results to the
caller's own thread keeps that invariant a property of the helper rather than
something each call site has to remember.
"""

from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait

from dj_digger.core.errors import InvalidInputError


def bounded_results[T, R](
    items: Iterable[T],
    work: Callable[[T], R],
    *,
    workers: int,
) -> Iterator[R]:
    """Yield each result as it completes, keeping at most ``workers`` in flight.

    Results arrive in completion order, not input order. The consumer loop runs
    in the calling thread, so persistence stays single-threaded. Closing the
    iterator early shuts the pool down and waits for in-flight work, so no
    worker outlives the caller.
    """
    if workers < 1:
        raise InvalidInputError("workers must be positive")
    pending = iter(items)
    with ThreadPoolExecutor(max_workers=workers) as executor:
        running: set[Future[R]] = set()
        for _ in range(workers):
            try:
                running.add(executor.submit(work, next(pending)))
            except StopIteration:
                break
        while running:
            completed, running = wait(running, return_when=FIRST_COMPLETED)
            for future in completed:
                yield future.result()
                try:
                    running.add(executor.submit(work, next(pending)))
                except StopIteration:
                    continue


__all__ = ["bounded_results"]
