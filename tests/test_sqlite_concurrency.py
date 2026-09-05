import sqlite3
from collections.abc import Callable
from pathlib import Path
from queue import Queue
from threading import Event, Lock, Thread

from dj_digger.catalog.factory import DatabaseFactory

THREAD_TIMEOUT_SECONDS = 3.0
READER_COUNT = 8
READS_PER_READER = 5


def _initialize_catalog(factory: DatabaseFactory) -> None:
    with factory.open() as database:
        database.migrate()
        database.execute(
            "CREATE TABLE concurrency_probe (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
        )
        database.execute("INSERT INTO concurrency_probe (value) VALUES ('baseline')")
        database.commit()


def _capture_thread_errors(errors: Queue[BaseException], operation: Callable[[], None]) -> None:
    try:
        operation()
    except BaseException as error:
        errors.put(error)


def _join_threads(threads: list[Thread]) -> None:
    for thread in threads:
        thread.join(THREAD_TIMEOUT_SECONDS)
    assert not [thread.name for thread in threads if thread.is_alive()]


def _assert_no_thread_errors(errors: Queue[BaseException]) -> None:
    captured = list(errors.queue)
    assert not captured, captured


def test_reader_sees_pre_write_snapshot_during_uncommitted_writer(
    tmp_path: Path,
) -> None:
    factory = DatabaseFactory(tmp_path / "catalog.sqlite")
    _initialize_catalog(factory)
    writer_ready = Event()
    release_writer = Event()
    reader_finished = Event()
    counts: Queue[int] = Queue()
    errors: Queue[BaseException] = Queue()

    def write_uncommitted_row() -> None:
        with factory.open() as database, database.transaction():
            database.execute("INSERT INTO concurrency_probe (value) VALUES ('pending')")
            writer_ready.set()
            if not release_writer.wait(THREAD_TIMEOUT_SECONDS):
                raise TimeoutError("writer release was not signalled")

    def read_snapshot() -> None:
        if not writer_ready.wait(THREAD_TIMEOUT_SECONDS):
            raise TimeoutError("writer did not start")
        with factory.open() as database:
            counts.put(int(database.scalar("SELECT count(*) FROM concurrency_probe")))
        reader_finished.set()

    threads = [
        Thread(
            target=_capture_thread_errors,
            args=(errors, write_uncommitted_row),
            name="uncommitted-writer",
        ),
        Thread(
            target=_capture_thread_errors,
            args=(errors, read_snapshot),
            name="snapshot-reader",
        ),
    ]
    for thread in threads:
        thread.start()

    try:
        assert reader_finished.wait(THREAD_TIMEOUT_SECONDS)
        assert counts.get_nowait() == 1
    finally:
        release_writer.set()
        _join_threads(threads)

    _assert_no_thread_errors(errors)


def test_readers_remain_available_during_bounded_bulk_write(tmp_path: Path) -> None:
    factory = DatabaseFactory(tmp_path / "catalog.sqlite")
    _initialize_catalog(factory)
    writer_ready = Event()
    start_readers = Event()
    release_writer = Event()
    readers_finished = Event()
    completion_lock = Lock()
    completed_readers = 0
    counts: Queue[int] = Queue()
    errors: Queue[BaseException] = Queue()

    def write_bounded_batch() -> None:
        with factory.open() as database, database.transaction():
            database.execute(
                """
                WITH RECURSIVE sequence(value) AS (
                    SELECT 1
                    UNION ALL
                    SELECT value + 1 FROM sequence WHERE value < 500
                )
                INSERT INTO concurrency_probe (value)
                SELECT 'bulk-' || value FROM sequence
                """
            )
            writer_ready.set()
            if not release_writer.wait(THREAD_TIMEOUT_SECONDS):
                raise TimeoutError("bulk writer release was not signalled")

    def repeatedly_read() -> None:
        nonlocal completed_readers
        try:
            if not start_readers.wait(THREAD_TIMEOUT_SECONDS):
                raise TimeoutError("reader start was not signalled")
            for _ in range(READS_PER_READER):
                with factory.open() as database:
                    counts.put(int(database.scalar("SELECT count(*) FROM concurrency_probe")))
        finally:
            with completion_lock:
                completed_readers += 1
                if completed_readers == READER_COUNT:
                    readers_finished.set()

    threads = [
        Thread(
            target=_capture_thread_errors,
            args=(errors, write_bounded_batch),
            name="bulk-writer",
        )
    ]
    threads.extend(
        Thread(
            target=_capture_thread_errors,
            args=(errors, repeatedly_read),
            name=f"bulk-reader-{index}",
        )
        for index in range(READER_COUNT)
    )
    for thread in threads:
        thread.start()

    try:
        assert writer_ready.wait(THREAD_TIMEOUT_SECONDS)
        start_readers.set()
        assert readers_finished.wait(THREAD_TIMEOUT_SECONDS)
    finally:
        start_readers.set()
        release_writer.set()
        _join_threads(threads)

    _assert_no_thread_errors(errors)
    assert list(counts.queue) == [1] * (READER_COUNT * READS_PER_READER)

    with factory.open() as database, database.transaction():
        database.execute("INSERT INTO concurrency_probe (value) VALUES ('after-bulk')")
    with factory.open() as database:
        assert database.scalar("SELECT count(*) FROM concurrency_probe") == 502


def test_competing_writer_waits_then_succeeds_after_short_lock(tmp_path: Path) -> None:
    factory = DatabaseFactory(tmp_path / "catalog.sqlite")
    _initialize_catalog(factory)
    lock_held = Event()
    second_attempting = Event()
    release_first = Event()
    second_finished = Event()
    errors: Queue[BaseException] = Queue()

    def hold_write_lock() -> None:
        with factory.open() as database, database.transaction():
            database.execute("INSERT INTO concurrency_probe (value) VALUES ('first-writer')")
            lock_held.set()
            if not release_first.wait(THREAD_TIMEOUT_SECONDS):
                raise TimeoutError("first writer release was not signalled")

    def wait_for_write_lock() -> None:
        if not lock_held.wait(THREAD_TIMEOUT_SECONDS):
            raise TimeoutError("first writer did not acquire its lock")
        with factory.open() as database:
            assert database.scalar("PRAGMA busy_timeout") == 5_000
            second_attempting.set()
            database.execute("INSERT INTO concurrency_probe (value) VALUES ('second-writer')")
            database.commit()
        second_finished.set()

    threads = [
        Thread(
            target=_capture_thread_errors,
            args=(errors, hold_write_lock),
            name="first-writer",
        ),
        Thread(
            target=_capture_thread_errors,
            args=(errors, wait_for_write_lock),
            name="waiting-writer",
        ),
    ]
    for thread in threads:
        thread.start()

    try:
        assert second_attempting.wait(THREAD_TIMEOUT_SECONDS)
        assert not second_finished.wait(0.2)
        release_first.set()
        assert second_finished.wait(THREAD_TIMEOUT_SECONDS)
    finally:
        release_first.set()
        _join_threads(threads)

    _assert_no_thread_errors(errors)
    with factory.open() as database:
        assert database.scalar("SELECT count(*) FROM concurrency_probe") == 3


def test_competing_writer_fails_with_explicit_short_busy_timeout(tmp_path: Path) -> None:
    factory = DatabaseFactory(tmp_path / "catalog.sqlite")
    _initialize_catalog(factory)
    lock_held = Event()
    release_first = Event()
    second_finished = Event()
    lock_errors: Queue[sqlite3.OperationalError] = Queue()
    errors: Queue[BaseException] = Queue()

    def hold_write_lock() -> None:
        with factory.open() as database, database.transaction():
            database.execute("INSERT INTO concurrency_probe (value) VALUES ('held')")
            lock_held.set()
            if not release_first.wait(THREAD_TIMEOUT_SECONDS):
                raise TimeoutError("first writer release was not signalled")

    def exceed_short_timeout() -> None:
        if not lock_held.wait(THREAD_TIMEOUT_SECONDS):
            raise TimeoutError("first writer did not acquire its lock")
        with factory.open() as database:
            database.execute("PRAGMA busy_timeout = 100")
            assert database.scalar("PRAGMA busy_timeout") == 100
            try:
                database.execute("INSERT INTO concurrency_probe (value) VALUES ('blocked')")
            except sqlite3.OperationalError as error:
                lock_errors.put(error)
            else:
                raise AssertionError("competing writer unexpectedly acquired the write lock")
        second_finished.set()

    threads = [
        Thread(
            target=_capture_thread_errors,
            args=(errors, hold_write_lock),
            name="overlong-lock-holder",
        ),
        Thread(
            target=_capture_thread_errors,
            args=(errors, exceed_short_timeout),
            name="short-timeout-writer",
        ),
    ]
    for thread in threads:
        thread.start()

    try:
        assert second_finished.wait(THREAD_TIMEOUT_SECONDS)
        assert "locked" in str(lock_errors.get_nowait()).lower()
    finally:
        release_first.set()
        _join_threads(threads)

    _assert_no_thread_errors(errors)

    with factory.open() as database, database.transaction():
        database.execute("INSERT INTO concurrency_probe (value) VALUES ('after-timeout')")
    with factory.open() as database:
        assert database.scalar("SELECT count(*) FROM concurrency_probe") == 3
