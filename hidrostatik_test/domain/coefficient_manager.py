from __future__ import annotations

from enum import Enum
from typing import Final


class CoefficientState(str, Enum):
    EMPTY = "empty"
    COMPUTED = "computed"
    REFERENCE = "reference"
    MANUAL = "manual"
    STALE = "stale"

    def is_usable(self) -> bool:
        return self in {CoefficientState.COMPUTED, CoefficientState.REFERENCE, CoefficientState.MANUAL}

    def is_auto_updateable(self) -> bool:
        return self in {CoefficientState.COMPUTED, CoefficientState.REFERENCE}


VALID_COEFFICIENT_KEYS: Final[tuple[str, ...]] = ("air_a", "pressure_a", "pressure_b")


class CoefficientManager:
    def __init__(self) -> None:
        self._states: dict[str, CoefficientState] = {
            "air_a": CoefficientState.EMPTY,
            "pressure_a": CoefficientState.EMPTY,
            "pressure_b": CoefficientState.EMPTY,
        }

    def get(self, key: str) -> CoefficientState:
        return self._states[key]

    def set(self, key: str, state: CoefficientState) -> None:
        self._states[key] = state

    def mark_dependencies_changed(self, keys: tuple[str, ...]) -> None:
        for key in keys:
            current = self._states.get(key)
            if current is not None and current.is_auto_updateable():
                self._states[key] = CoefficientState.STALE

    def is_ready(self, key: str) -> bool:
        return self._states.get(key, CoefficientState.EMPTY).is_usable()

    def reset(self, keys: tuple[str, ...] | None = None) -> None:
        target = keys if keys is not None else tuple(VALID_COEFFICIENT_KEYS)
        for key in target:
            if key in self._states:
                self._states[key] = CoefficientState.EMPTY

    def keys(self) -> tuple[str, ...]:
        return VALID_COEFFICIENT_KEYS

    def as_dict(self) -> dict[str, str]:
        return {k: v.value for k, v in self._states.items()}

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> CoefficientManager:
        manager = cls()
        for key, value in data.items():
            if key in manager._states:
                try:
                    manager._states[key] = CoefficientState(value)
                except ValueError:
                    manager._states[key] = CoefficientState.EMPTY
        return manager
