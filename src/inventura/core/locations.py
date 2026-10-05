"""Storage locations in RACK-LEVEL-POSITION notation, e.g. B6-1-1 or K2-03-11.

A location is parsed into a rack (letter prefix and number), a level and a position.
Comparison and sorting use the parsed values, so leading zeros do not matter
(K2-03-11 and K2-3-11 are the same location) and racks sort naturally (B2 before B10).
The text as written in the source is kept for display.
"""

import re
from dataclasses import dataclass, field

_PATTERN = re.compile(r"^([A-Z]+)([0-9]{1,4})-([0-9]{1,4})-([0-9]{1,4})$", re.ASCII)

FORMAT_HINT = "pričakovana oblika REGAL-NIVO-POLOŽAJ, npr. B6-1-1 ali K2-03-11"


class LocationError(ValueError):
    """The text is not a valid location."""


@dataclass(frozen=True, slots=True, order=True)
class Location:
    rack_prefix: str
    rack_number: int
    level: int
    position: int
    raw: str = field(default="", compare=False)

    @property
    def rack(self) -> str:
        """Canonical rack name, e.g. B6 (also for B06 in the source)."""
        return f"{self.rack_prefix}{self.rack_number}"

    @property
    def rack_key(self) -> tuple[str, int]:
        return (self.rack_prefix, self.rack_number)

    @property
    def canonical(self) -> str:
        return f"{self.rack}-{self.level}-{self.position}"

    def __str__(self) -> str:
        return self.raw or self.canonical

    @classmethod
    def from_parts(cls, rack: str, level: int, position: int, raw: str = "") -> "Location":
        """Rebuild a location from stored parts, e.g. ("K2", 3, 11, "K2-03-11")."""
        prefix, number = rack_sort_key(rack)
        return cls(prefix, number, level, position, raw=raw)


def parse_location(text: str) -> Location:
    """Parse a location; surrounding spaces and letter case are ignored."""
    raw = text.strip()
    match = _PATTERN.match(raw.upper())
    if match is None:
        raise LocationError(f"neveljavna lokacija, {FORMAT_HINT}")
    prefix, rack, level, position = match.groups()
    return Location(prefix, int(rack), int(level), int(position), raw=raw)


def rack_sort_key(rack: str) -> tuple[str, int]:
    """Natural sort key for a rack name such as B10."""
    match = re.fullmatch(r"([A-Z]+)([0-9]+)", rack.strip().upper(), re.ASCII)
    if match is None:
        raise LocationError(f"neveljaven regal {rack!r}")
    return (match.group(1), int(match.group(2)))
