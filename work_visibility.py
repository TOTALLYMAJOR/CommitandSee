"""Independent work visibility CLI; retains the supplied GitHub starter commands."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys

from local_observer import ObservationError, observe
from observation_store import Store, guard_storage


def default_database():
    base = Path(os.getenv('XDG_STATE_HOME', Path.home() / '.local' / 'state'))
    return base / 'work-visibility' / 'observations.sqlite3'


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in {'collect', 'report', 'demo'}:
        from starter.wale_visibility import main as starter_main
        return starter_main(argv)
    parser = argparse.ArgumentParser(description=__doc__, epilog='Existing commands: collect, report, demo (use COMMAND --help).')
    sub = parser.add_subparsers(dest='command', required=True)
    scan = sub.add_parser('snapshot', help='Observe configured clones and their registered worktrees; no network')
    scan.add_argument('--root', action='append', required=True, help='Existing clone/worktree path; repeat for independent clones')
    scan.add_argument('--database', type=Path, default=default_database())
    history = sub.add_parser('history', help='Read saved transitions; no scan')
    history.add_argument('--database', type=Path, default=default_database())
    history.add_argument('--limit', type=int, default=50)
    args = parser.parse_args(argv)
    try:
        if args.command == 'history':
            if not args.database.is_file():
                raise ValueError('Observation database does not exist')
            if not 1 <= args.limit <= 1000:
                raise ValueError('History limit must be between 1 and 1000')
            # History never opens or creates a write connection.
            db = sqlite3.connect(args.database.resolve().as_uri() + '?mode=ro', uri=True)
            try:
                rows = db.execute('SELECT sequence, entity_id, observed_at, state_json FROM transitions ORDER BY sequence DESC LIMIT ?', (args.limit,)).fetchall()
                result = [{'sequence': s, 'entity_id': e, 'observed_at': t, 'state': json.loads(v)} for s, e, t, v in rows]
            finally:
                db.close()
        else:
            guard_storage(args.database, args.root)
            result = observe(args.root)
            protected = args.root + [c['common_directory'] for c in result['clones']]
            protected += [w['path'] for c in result['clones'] for w in c['worktrees']]
            database = guard_storage(args.database, protected)
            store = Store(database)
            try:
                store.record(result)
            finally:
                store.close()
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return 2 if isinstance(result, dict) and result['coverage'] != 'complete' else 0
    except (ObservationError, ValueError, OSError, sqlite3.Error) as error:
        print('Observation failed: ' + (str(error) if isinstance(error, (ObservationError, ValueError)) else 'local_io_unavailable'), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
