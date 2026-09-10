"""Text and JSON presentation for portable set-copy results."""

from typing import Any

from dj_digger.core.progress import ProgressEvent
from dj_digger.core.set_copy import SetCopyResult


def copy_payload(result: SetCopyResult) -> dict[str, Any]:
    """Map the typed copy result to a stable machine-readable payload."""
    return {
        "event": "copy",
        "status": "succeeded",
        "total": result.total,
        "playlist": str(result.playlist),
        "text_list": str(result.text_list),
    }


def copy_progress_lines(event: ProgressEvent, *, verbose: bool) -> tuple[str, ...]:
    """Render presentation-neutral copy events as CLI lines."""
    if event.kind == "copy_started":
        return (f"[  0%] (0/{event.total or 0})",)
    if event.kind == "copy_item_started" and verbose and event.subject is not None:
        total = event.total or 0
        index = (event.completed or 0) + 1
        width = max(2, len(str(total)))
        return (f"COPY {index:0{width}d}/{total}\n  to:    {event.subject}",)
    if event.kind == "copy_item_finished":
        total = event.total or 0
        completed = event.completed or 0
        return (f"[{completed * 100 // total:3d}%] ({completed}/{total})",) if total else ()
    return ()


__all__ = ["copy_payload", "copy_progress_lines"]
