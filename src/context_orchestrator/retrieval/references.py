"""Follow references from retrieved text to the code that defines them.

Docs, bug reports and tests often name the function they are about
(``recurring.occurrence_windows()``) without sharing many words with it.
Keyword search finds the bug report but ranks the function low; following the
name closes that gap. Rules are deliberately simple and explainable:

* A *definition* is a ``def`` or ``class`` statement inside a code or test
  chunk (top-level or nested, e.g. a method).
* A *reference* is an identifier in a chunk's text that is followed by ``(``,
  appears after a dot (``module.name``), or is wrapped in backticks.
* Names that are short or defined in many places (``get``, ``run``) are too
  ambiguous to follow.
* For ``module.name`` the definition in a file named ``module.py`` wins.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from context_orchestrator.memory.store import MemoryStore
from context_orchestrator.models import Chunk, InfoKind

_DEFINITION = re.compile(r"^[ \t]*(?:async[ \t]+)?(?:def|class)[ \t]+([A-Za-z_]\w*)", re.MULTILINE)
_CALL = re.compile(r"\b([A-Za-z_]\w*)[ \t]*\(")
_DOTTED = re.compile(r"\b([A-Za-z_]\w*)\.([A-Za-z_]\w*)\b")
_BACKTICKED = re.compile(r"`([A-Za-z_]\w*)(?:\(\))?`")

MIN_NAME_LENGTH = 5
MAX_DEFINITIONS_PER_NAME = 2
_CODE_KINDS = (InfoKind.CODE.value, InfoKind.TEST.value)


@dataclass(frozen=True, slots=True)
class Reference:
    name: str
    chunk: Chunk  # the chunk that defines ``name``


class ReferenceIndex:
    """Maps definition names to the code/test chunks that define them."""

    def __init__(self, store: MemoryStore) -> None:
        self.store = store
        self._defs: dict[str, list[tuple[str, str]]] | None = None  # name -> [(chunk_id, path)]

    def _definitions(self) -> dict[str, list[tuple[str, str]]]:
        if self._defs is None:
            defs: dict[str, list[tuple[str, str]]] = {}
            rows = self.store.conn.execute(
                "SELECT chunk_id, path, text FROM chunks WHERE kind IN (?, ?)", _CODE_KINDS
            )
            for row in rows:
                for name in dict.fromkeys(_DEFINITION.findall(row["text"])):
                    defs.setdefault(name, []).append((row["chunk_id"], row["path"]))
            self._defs = defs
        return self._defs

    def references_in(self, chunk: Chunk) -> list[Reference]:
        """Definitions referenced by ``chunk``'s text, in order of first mention."""
        defs = self._definitions()
        text = chunk.text
        own = set(_DEFINITION.findall(text))
        # (name, module hint) in order of appearance.
        mentions: list[tuple[int, str, str | None]] = []
        mentions += [(m.start(), m.group(1), None) for m in _CALL.finditer(text)]
        mentions += [(m.start(), m.group(1), None) for m in _BACKTICKED.finditer(text)]
        mentions += [(m.start(), m.group(2), m.group(1)) for m in _DOTTED.finditer(text)]
        mentions.sort()

        found: list[Reference] = []
        seen: set[str] = set()
        for _, name, module in mentions:
            if name in seen or name in own or len(name) < MIN_NAME_LENGTH:
                continue
            candidates = defs.get(name, [])
            candidates = [c for c in candidates if c[0] != chunk.chunk_id]
            if module:
                in_module = [c for c in candidates if c[1].rsplit("/", 1)[-1] == f"{module}.py"]
                candidates = in_module or candidates
            if not candidates or len(candidates) > MAX_DEFINITIONS_PER_NAME:
                continue
            seen.add(name)
            row = self.store.conn.execute(
                "SELECT * FROM chunks WHERE chunk_id = ?", (candidates[0][0],)
            ).fetchone()
            found.append(Reference(name, self.store.row_to_chunk(row)))
        return found
