"""Shared helpers: errors, validation report, naming, YAML loading (PyYAML or the vendored copy)."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ModelError(Exception):
    """Raised when a file cannot be loaded at all (syntax, missing file)."""


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def error(self, where: str, msg: str) -> None:
        self.errors.append(f"{where}: {msg}")

    def warn(self, where: str, msg: str) -> None:
        self.warnings.append(f"{where}: {msg}")

    @property
    def ok(self) -> bool:
        return not self.errors

    def render(self, ok_text: str = "Metamodel OK") -> str:
        lines = [f"ERROR   {e}" for e in self.errors] + [f"WARNING {w}" for w in self.warnings]
        if not lines:
            return ok_text
        return "\n".join(lines + [f"{len(self.errors)} error(s), {len(self.warnings)} warning(s)"])


# --------------------------------------------------------------------------- #
# Naming
# --------------------------------------------------------------------------- #
def snake(name: str) -> str:
    s = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name)
    s = re.sub(r"(?<=[A-Z])([A-Z][a-z])", r"_\1", s)
    return s.lower()


def pluralize(word: str) -> str:
    if re.search(r"[^aeiou]y$", word):
        return word[:-1] + "ies"
    if re.search(r"(s|x|z|sh|ch)$", word):
        return word + "es"
    return word + "s"


def humanize(key: str) -> str:
    words = re.sub(r"[_\-]+", " ", snake(key) if key[:1].isupper() else key).strip()
    return words[:1].upper() + words[1:]


# --------------------------------------------------------------------------- #
# YAML
# --------------------------------------------------------------------------- #
def import_yaml():
    """PyYAML if installed, else the vendored pure-Python copy (../vendor)."""
    try:
        import yaml  # type: ignore
        return yaml
    except ImportError:
        vendor = str(Path(__file__).resolve().parents[1] / "vendor")
        if vendor not in sys.path:
            sys.path.append(vendor)
        import yaml  # type: ignore
        return yaml


def loads(text: str) -> dict[str, Any]:
    yaml = import_yaml()
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ModelError(f"invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ModelError("the metamodel must be a mapping")
    return data
