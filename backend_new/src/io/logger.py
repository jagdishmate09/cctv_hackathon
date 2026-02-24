from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


class JSONLLogger:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, obj: Dict[str, Any]):
        with self.path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


class JSONLogger:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, obj: Dict[str, Any]):
        with self.path.open('w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
