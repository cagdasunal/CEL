"""Selector substrings whose flipped RTL override rules must be DROPPED.

rtlcss flips everything mechanically. Some flips are semantically wrong and can't
be detected automatically — logos/brandmarks, media-play controls (play points
right regardless of reading direction), intentional `direction` scroll hacks,
carousel internals, etc. When live `/ar/` browser validation finds a rule that
flipped incorrectly, add a substring of its selector here and it will be excluded
from the generated override.

Seed is intentionally EMPTY — populate it from real validation findings, not
speculation (the current generated override has no known mis-flips).
"""

EXCLUDE_SUBSTRINGS: list[str] = []
