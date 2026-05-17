"""Adapter base types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AdapterDefinition:
    name: str
    description: str
