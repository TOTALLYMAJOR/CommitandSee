"""Monitor-owned SQLite projection. Store transitions, never file contents."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import uuid

from local_observer import digest


def guard_storage(path, roots):
    destination = Path(path).expanduser().resolve()
    for root in roots:
        root = Path(root).expanduser().resolve()
        if destination == root or root in destination.parents:
            raise ValueError('Monitor storage must be outside every observed worktree and Git directory')
    return destination


class Store:
    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Create private files without changing permissions on an existing parent directory.
        fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600) if not self.path.exists() else None
        if fd is not None:
            os.close(fd)
        self.db = sqlite3.connect(self.path)
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS entities (
            id TEXT PRIMARY KEY, kind TEXT NOT NULL, first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL, last_changed TEXT NOT NULL, last_success TEXT,
            fingerprint TEXT NOT NULL, state_json TEXT NOT NULL, last_known_json TEXT);
          CREATE TABLE IF NOT EXISTS transitions (
            sequence INTEGER PRIMARY KEY, entity_id TEXT NOT NULL, observed_at TEXT NOT NULL,
            fingerprint TEXT NOT NULL, state_json TEXT NOT NULL);
        ''')
        self.db.execute('INSERT OR IGNORE INTO metadata VALUES (?, ?)', ('schema_version', '1'))
        self.db.execute('INSERT OR IGNORE INTO metadata VALUES (?, ?)', ('machine_id', str(uuid.uuid4())))
        self.machine_id = self.db.execute("SELECT value FROM metadata WHERE key='machine_id'").fetchone()[0]
        self.db.commit()

    def close(self):
        self.db.close()

    def record(self, snapshot):
        at, updates = snapshot['finished_at'], []
        entities = []
        for clone in snapshot['clones']:
            clone_id = digest([self.machine_id, clone['common_directory']])
            clone['clone_id'], clone['machine_id'] = clone_id, self.machine_id
            complete = clone['shared_refs_coverage'] == 'complete' and all(w['coverage'] == 'complete' for w in clone['worktrees'])
            for root in clone['configured_roots']:
                state = {'path': root, 'clone_id': clone_id, 'coverage': 'complete' if complete else 'partial'}
                entities.append((digest([self.machine_id, 'configured_root', root]), 'configured_root', state, complete))
            entities.append((clone_id, 'clone', {k: v for k, v in clone.items() if k not in {'worktrees', 'configured_roots', 'refs_observed_at'}}, clone['shared_refs_coverage'] == 'complete'))
            for worktree in clone['worktrees']:
                worktree['worktree_id'] = digest([clone_id, worktree['path']])
                state = {k: v for k, v in worktree.items() if k not in {'attempts', 'started_at', 'finished_at'}}
                entities.append((worktree['worktree_id'], 'worktree', state, worktree['coverage'] == 'complete'))
        for gap in snapshot['coverage_gaps']:
            entities.append((digest([self.machine_id, 'configured_root', gap['path']]), 'configured_root', gap, False))
        with self.db:
            for entity_id, kind, state, success in entities:
                fingerprint, encoded = digest(state), json.dumps(state, ensure_ascii=True, sort_keys=True)
                previous = self.db.execute('SELECT fingerprint FROM entities WHERE id=?', (entity_id,)).fetchone()
                changed = previous is None or previous[0] != fingerprint
                self.db.execute('''INSERT INTO entities VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                  ON CONFLICT(id) DO UPDATE SET last_seen=excluded.last_seen,
                    last_changed=CASE WHEN entities.fingerprint != excluded.fingerprint THEN excluded.last_changed ELSE entities.last_changed END,
                    last_success=COALESCE(excluded.last_success, entities.last_success),
                    last_known_json=COALESCE(excluded.last_known_json, entities.last_known_json),
                    fingerprint=excluded.fingerprint, state_json=excluded.state_json''',
                  (entity_id, kind, at, at, at, at if success else None, fingerprint, encoded, encoded if success else None))
                if changed:
                    self.db.execute('INSERT INTO transitions(entity_id, observed_at, fingerprint, state_json) VALUES (?, ?, ?, ?)',
                                    (entity_id, at, fingerprint, encoded))
                row = self.db.execute('SELECT first_seen, last_changed, last_success FROM entities WHERE id=?', (entity_id,)).fetchone()
                updates.append({'entity_id': entity_id, 'kind': kind, 'first_seen': row[0],
                                'last_state_change': row[1], 'last_successful_collection': row[2], 'changed': changed})
        snapshot['persistence'] = {'machine_id': self.machine_id, 'entities': updates,
                                   'note': 'Observed age only; gaps do not establish inactivity. IDs are path-bound within this database.'}
        return snapshot

    def history(self, limit=50):
        rows = self.db.execute('SELECT sequence, entity_id, observed_at, state_json FROM transitions ORDER BY sequence DESC LIMIT ?', (limit,)).fetchall()
        return [{'sequence': row[0], 'entity_id': row[1], 'observed_at': row[2], 'state': json.loads(row[3])} for row in rows]
