"""Transactional UI repository overrides; the hand-edited JSON is never written."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import stat


APPLICATION_ID = 0x57565231  # WVR1: Work Visibility registry, schema 1.
SCHEMA_VERSION = 1


class RegistryError(OSError):
    """Unreadable, incompatible, or unsafe monitor-owned registry storage."""


def validate_state_destination(config_path, state_path):
    """Keep observation-history writes separate from configuration/registry data."""
    if not config_path or not state_path:
        return
    config = Path(config_path).expanduser().resolve()
    state = Path(state_path).expanduser().resolve()
    for protected in [config, *RepositoryRegistry(config).artifacts]:
        same = state == protected.resolve()
        if not same:
            try:
                same = state.samefile(protected)
            except FileNotFoundError:
                pass
        if same:
            raise ValueError('Observation state must be separate from the config and repository registry files.')


class RepositoryRegistry:
    def __init__(self, config_path):
        config_path = Path(config_path).expanduser().resolve()
        self.path = config_path.with_name(config_path.name + '.registry.sqlite3')

    @property
    def artifacts(self):
        return [Path(str(self.path) + suffix) for suffix in ('', '-journal', '-wal', '-shm')]

    def validate_paths(self):
        """Do not follow pre-existing links or adopt another user's storage."""
        for path in self.artifacts:
            try:
                info = path.lstat()
            except FileNotFoundError:
                continue
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise RegistryError('Registry files must be regular files without links.')
            if hasattr(os, 'geteuid') and info.st_uid != os.geteuid():
                raise RegistryError('Registry files must belong to the current user.')

    @staticmethod
    def _schema(connection, *, initialize=False):
        application = connection.execute('PRAGMA application_id').fetchone()[0]
        version = connection.execute('PRAGMA user_version').fetchone()[0]
        tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        if application == 0 and version == 0 and not tables:
            if not initialize:
                return False
            connection.execute('CREATE TABLE repository_overrides (path TEXT PRIMARY KEY, entry TEXT)')
            connection.execute(f'PRAGMA application_id={APPLICATION_ID}')
            connection.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
        elif application != APPLICATION_ID or version != SCHEMA_VERSION:
            raise RegistryError('This file is not a supported Work Visibility registry.')
        return True

    @staticmethod
    def _entries(connection):
        result = {}
        for path, payload in connection.execute('SELECT path, entry FROM repository_overrides ORDER BY rowid'):
            try:
                entry = json.loads(payload) if payload is not None else None
            except (TypeError, ValueError) as exc:
                raise RegistryError('Invalid repository registry entry.') from exc
            if not isinstance(path, str) or not path or (entry is not None and not isinstance(entry, dict)):
                raise RegistryError('Invalid repository registry entry.')
            result[path] = entry
        return result

    def read(self):
        """Read without creating a database or writing to the config directory."""
        self.validate_paths()
        if not self.path.exists():
            return {}
        connection = None
        try:
            connection = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True, timeout=5)
            connection.execute('PRAGMA query_only=ON')
            connection.execute('BEGIN')
            return self._entries(connection) if self._schema(connection) else {}
        except sqlite3.Error as exc:
            raise RegistryError('Could not read the repository registry.') from exc
        finally:
            if connection is not None:
                connection.close()

    def update(self, change, guard):
        """Merge a mutation with the latest registry under an SQLite write lock.

        `None` entries are durable removal tombstones. The callback receives all
        current overrides, so separate observer processes never replace a stale
        copy of another observer's changes. The JSON config is never opened for
        writing, even when an unrelated editor changes it after the last guard.
        """
        self.validate_paths()
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(descriptor)
        self.validate_paths()
        connection = None
        try:
            connection = sqlite3.connect(self.path, timeout=5, isolation_level=None)
            connection.execute('PRAGMA synchronous=FULL')
            connection.execute('BEGIN IMMEDIATE')
            self._schema(connection, initialize=True)
            guard()
            previous = self._entries(connection)
            entries = dict(previous)
            result = change(entries)
            for path, entry in entries.items():
                if path in previous and entry == previous[path]:
                    continue
                payload = json.dumps(entry, ensure_ascii=True, allow_nan=False) if entry is not None else None
                connection.execute(
                    'INSERT INTO repository_overrides(path, entry) VALUES (?, ?) '
                    'ON CONFLICT(path) DO UPDATE SET entry=excluded.entry', (path, payload))
            guard()
            connection.commit()
            return result, entries
        except sqlite3.Error as exc:
            raise RegistryError('Could not update the repository registry.') from exc
        finally:
            if connection is not None:
                # Closing rolls back any incomplete transaction, including a
                # callback failure, config conflict, or storage error.
                connection.close()
