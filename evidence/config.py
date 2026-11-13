"""Phase 1 limits and storage locations."""
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path(os.environ.get('AUDIT_DATA_DIR', ROOT / '.evidence-data'))
    timeout_seconds: float = 12.0
    attempts: int = 3
    max_file_bytes: int = 512 * 1024
    max_fragment_lines: int = 120
    max_fragment_chars: int = 6000
    max_files: int = 8
    max_issues: int = 5
    max_comments: int = 3

    @property
    def db_path(self): return self.data_dir / 'audit_engine.db'
    @property
    def legacy_path(self): return self.data_dir / 'evidence.sqlite3'
