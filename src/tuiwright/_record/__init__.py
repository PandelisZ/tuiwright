"""Record & codegen subsystem.

This package provides the wrapper that lets you drive a TUI interactively
while tuiwright records what you do, then synthesises a pytest test that
codifies the behaviour you just demonstrated.
"""

from tuiwright._record.codegen import CodegenStyle, generate_test
from tuiwright._record.decoders import RecordedAction, decode_input_stream

__all__ = [
    "CodegenStyle",
    "RecordedAction",
    "decode_input_stream",
    "generate_test",
]
