import os
from pathlib import Path
from typing import Protocol
class Storage(Protocol):
    def write(self, key: str, raw: bytes) -> None: ...
    def path(self, key: str) -> Path: ...
    def delete(self, key: str) -> None: ...
class LocalStorage:
    def __init__(self, root): self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True)
    def path(self, key):
        if '/' in key or '..' in key: raise ValueError('Invalid storage key')
        return self.root / key
    def write(self, key, raw):
        target = self.path(key)
        temporary = target.with_suffix('.part')
        temporary.write_bytes(raw); os.chmod(temporary, 0o600); temporary.replace(target)
    def delete(self, key): self.path(key).unlink(missing_ok=True)
