"""Snapshot extension tests — uses syrupy in update mode for first run."""

from __future__ import annotations

import pytest
from syrupy.assertion import SnapshotAssertion

from tuiwright import TuiSession
from tuiwright._snapshot import ScreenSnapshotExtension

pytestmark = pytest.mark.asyncio


async def test_screen_snapshot_round_trip(
    tui: TuiSession, demo_cmd: list[str], snapshot: SnapshotAssertion
) -> None:
    await tui.start(demo_cmd, cols=40, rows=10)
    await tui.wait_for_text("Ready")
    await tui.wait_for_stable(quiet_ms=60)
    assert tui.screen == snapshot(extension_class=ScreenSnapshotExtension)


async def test_screen_after_typing(
    tui: TuiSession, demo_cmd: list[str], snapshot: SnapshotAssertion
) -> None:
    await tui.start(demo_cmd, cols=40, rows=10)
    await tui.wait_for_text("Ready")
    await tui.type("snap")
    await tui.wait_for_text("snap")
    await tui.wait_for_stable(quiet_ms=60)
    assert tui.screen == snapshot(extension_class=ScreenSnapshotExtension)
