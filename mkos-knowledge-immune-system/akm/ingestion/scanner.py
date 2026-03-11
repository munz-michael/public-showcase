"""Workspace scanner - discovers ingestible files across projects."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from akm.config import Config
from akm.utils.logger import log_info, log_warning


@dataclass
class FileInfo:
    path: str
    project_slug: str
    file_type: str  # 'markdown' or 'json'
    size: int
    mtime: float


class WorkspaceScanner:
    """Walk workspace projects and discover ingestible files."""

    EXT_MAP = {".md": "markdown", ".json": "json"}

    def __init__(self, config: Config) -> None:
        self.config = config
        self._projects: list[dict] = []

    def load_projects(self) -> list[dict]:
        """Load project registry from Cockpit/data.json."""
        cockpit_path = self.config.cockpit_path
        if not os.path.exists(cockpit_path):
            log_warning(f"Cockpit nicht gefunden: {cockpit_path}")
            return []

        with open(cockpit_path, encoding="utf-8") as f:
            data = json.load(f)

        self._projects = data.get("projects", [])
        return self._projects

    def scan_all(self) -> list[FileInfo]:
        """Discover all ingestible files across workspace."""
        if not self._projects:
            self.load_projects()

        all_files: list[FileInfo] = []
        workspace = Path(self.config.workspace_root)

        for proj in self._projects:
            slug = proj.get("id", "")
            rel_path = proj.get("path", "")
            if not slug or not rel_path:
                continue

            proj_dir = workspace / rel_path
            if not proj_dir.is_dir():
                log_info(f"Projekt-Verzeichnis nicht gefunden: {proj_dir}")
                continue

            files = self._scan_directory(proj_dir, slug)
            all_files.extend(files)

        # Also scan directories not in Cockpit (like ai_knowledge_management, rUv guide)
        known_paths = {proj.get("path", "") for proj in self._projects}
        for entry in workspace.iterdir():
            if not entry.is_dir():
                continue
            if entry.name.startswith("."):
                continue
            if entry.name in self.config.ignore_patterns:
                continue
            # Check if this directory is already covered by a project
            rel = str(entry.relative_to(workspace))
            if rel not in known_paths:
                slug = self._slugify(entry.name)
                files = self._scan_directory(entry, slug)
                all_files.extend(files)

        return all_files

    def _scan_directory(self, root: Path, slug: str) -> list[FileInfo]:
        """Scan a single project directory for ingestible files."""
        files: list[FileInfo] = []
        ignore = set(self.config.ignore_patterns)

        for dirpath, dirnames, filenames in os.walk(root):
            # Prune ignored directories
            dirnames[:] = [d for d in dirnames if d not in ignore and not d.startswith(".")]

            for fname in filenames:
                ext = Path(fname).suffix.lower()
                if ext not in self.EXT_MAP:
                    continue

                fpath = os.path.join(dirpath, fname)
                try:
                    stat = os.stat(fpath)
                except OSError:
                    continue

                # Skip very large files (>500KB) and tiny files (<10 bytes)
                if stat.st_size > 500_000 or stat.st_size < 10:
                    continue

                files.append(FileInfo(
                    path=fpath,
                    project_slug=slug,
                    file_type=self.EXT_MAP[ext],
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                ))

        return files

    @staticmethod
    def _slugify(name: str) -> str:
        return name.lower().replace(" ", "-").replace("_", "-").replace(".", "-")
