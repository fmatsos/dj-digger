from dj_digger.analysis.windows import WINDOW_BARS, DjWindowPlanner


def beats(count: int) -> tuple[float, ...]:
    return tuple(index * 0.5 for index in range(count))


def test_window_lengths_are_fixed() -> None:
    assert WINDOW_BARS == (8, 16, 32, 64)


def test_short_track_has_no_64_bar_intro_or_outro_window() -> None:
    windows = DjWindowPlanner().plan(beats(64 * 4))

    assert windows[64].intro is None
    assert windows[64].outro is None


def test_intro_and_outro_are_stably_anchored_to_beat_boundaries() -> None:
    windows = DjWindowPlanner().plan(beats(64 * 4 + 1))

    eight = windows[8]
    assert eight.intro is not None
    assert eight.outro is not None
    assert (eight.intro.start, eight.intro.end) == (0.0, 16.0)
    assert (eight.outro.start, eight.outro.end) == (112.0, 128.0)
