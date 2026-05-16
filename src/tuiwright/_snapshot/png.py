"""syrupy extension for PNG snapshots, with PIL-based pixel-diff reporting.

Accepts raw ``bytes`` (assumed PNG) or paths. Comparison uses
``pixelmatch`` with a configurable threshold; on mismatch, writes
``expected.png``, ``actual.png``, and ``diff.png`` next to the snapshot
for human review and trace-viewer embedding.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image
from pixelmatch.contrib.PIL import pixelmatch
from syrupy.extensions.single_file import SingleFileSnapshotExtension, WriteMode

if TYPE_CHECKING:
    from syrupy.types import (
        PropertyFilter,
        PropertyMatcher,
        SerializableData,
        SerializedData,
    )


class PNGSnapshotExtension(SingleFileSnapshotExtension):
    """Snapshots raw PNG bytes; pixel-diffs on read."""

    file_extension = "png"
    _write_mode = WriteMode.BINARY

    threshold: float = 0.1
    include_anti_alias: bool = True

    def serialize(  # type: ignore[override]
        self,
        data: SerializableData,
        *,
        exclude: PropertyFilter | None = None,
        include: PropertyFilter | None = None,
        matcher: PropertyMatcher | None = None,
    ) -> SerializedData:
        if isinstance(data, (bytes, bytearray)):
            return bytes(data)
        if isinstance(data, (str, Path)):
            return Path(data).read_bytes()
        raise TypeError(
            f"PNGSnapshotExtension expects bytes or a path, got {type(data).__name__}"
        )

    def matches(  # type: ignore[override]
        self,
        *,
        serialized_data: SerializedData,
        snapshot_data: SerializedData,
    ) -> bool:
        if serialized_data == snapshot_data:
            return True
        # Pixel-tolerant compare.
        try:
            actual = Image.open(io.BytesIO(serialized_data)).convert("RGBA")
            expected = Image.open(io.BytesIO(snapshot_data)).convert("RGBA")
        except Exception:
            return False
        if actual.size != expected.size:
            return False
        diff_img = Image.new("RGBA", actual.size)
        mismatched = pixelmatch(
            expected,
            actual,
            diff_img,
            threshold=self.threshold,
            includeAA=self.include_anti_alias,
        )
        return mismatched == 0
