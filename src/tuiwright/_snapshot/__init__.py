"""Snapshot subsystem — custom syrupy extensions for screens + PNGs."""

from tuiwright._snapshot.cells import ScreenSnapshotExtension
from tuiwright._snapshot.png import PNGSnapshotExtension

__all__ = ["PNGSnapshotExtension", "ScreenSnapshotExtension"]
