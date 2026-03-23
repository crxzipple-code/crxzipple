from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar


IdT = TypeVar("IdT")


@dataclass(kw_only=True)
class Entity(Generic[IdT]):
    id: IdT

