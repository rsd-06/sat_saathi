"""The GPU side: one resident 4-bit base, every adapter attached, one call at a time.

Importing this package imports no torch. `runtime` does, lazily, the first
time a model is actually loaded; `cli doctor` can therefore run on a machine
with no GPU stack and say so.
"""

from .loader import register

__all__ = ["register"]
