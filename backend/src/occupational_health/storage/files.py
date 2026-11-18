from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path
from typing import BinaryIO


class PrivateFileStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, storage_key: str) -> Path:
        candidate = (self.root / storage_key).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ValueError("storage key escapes private root")
        return candidate

    def save(self, stream: BinaryIO, digest: str, suffix: str = ".pdf") -> str:
        storage_key = f"objects/{digest[:2]}/{digest}{suffix}"
        target = self._path(storage_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{uuid.uuid4().hex}.tmp")
        hasher = hashlib.sha256()
        try:
            with temporary.open("xb") as output:
                while block := stream.read(1024 * 1024):
                    hasher.update(block)
                    output.write(block)
            if hasher.hexdigest() != digest:
                raise ValueError("content digest changed during storage")
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)
        return storage_key

    def open(self, storage_key: str) -> BinaryIO:
        return self._path(storage_key).open("rb")

    def delete(self, storage_key: str) -> None:
        self._path(storage_key).unlink(missing_ok=True)
