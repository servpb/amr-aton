"""Durable local reminders; OS notification submission is not proof of perception."""
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import math
import sqlite3
import time
import uuid

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "reminders.sqlite3"


class ReminderStore:
    def __init__(self, path=DEFAULT_PATH, clock=time.time):
        self.path = Path(path)
        self.clock = clock
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS reminders (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, due_at REAL NOT NULL,
                created_at REAL NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
                lease_until REAL NOT NULL DEFAULT 0, retry_at REAL NOT NULL DEFAULT 0,
                attempts INTEGER NOT NULL DEFAULT 0, notified_at REAL,
                last_error TEXT)""")
            db.execute("CREATE INDEX IF NOT EXISTS reminders_due ON reminders(state, due_at)")

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def create(self, title, *, seconds=None, at=None):
        if not isinstance(title, str) or not title.strip() or len(title.strip()) > 200:
            raise ValueError("Informe um texto de 1 a 200 caracteres.")
        if (seconds is None) == (at is None):
            raise ValueError("Informe uma duração OU uma data e horário.")
        now = self.clock()
        if seconds is not None:
            if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds <= 0:
                raise ValueError("A duração deve ser um número positivo de segundos.")
            due = now + seconds
        else:
            parsed = datetime.fromisoformat(at)
            if parsed.tzinfo is None or parsed.utcoffset() is None:
                raise ValueError("O horário deve incluir o fuso, por exemplo -03:00.")
            due = parsed.timestamp()
        if not math.isfinite(due) or due <= now or due - now > 366 * 86400:
            raise ValueError("Escolha um horário futuro dentro dos próximos 366 dias.")
        item_id = uuid.uuid4().hex
        with self.connection() as db:
            db.execute("INSERT INTO reminders(id,title,due_at,created_at) VALUES(?,?,?,?)",
                       (item_id, title.strip(), due, now))
        return self.get(item_id)

    def get(self, item_id):
        with self.connection() as db:
            row = db.execute("SELECT * FROM reminders WHERE id=?", (item_id,)).fetchone()
        return dict(row) if row else None

    def list(self, include_history=False):
        with self.connection() as db:
            rows = db.execute("SELECT * FROM reminders " +
                ("" if include_history else "WHERE state IN ('pending','delivering') ") +
                "ORDER BY due_at LIMIT 100").fetchall()
        return [dict(row) for row in rows]

    def cancel(self, item_id):
        with self.connection() as db:
            db.execute("UPDATE reminders SET state='cancelled' WHERE id=? AND state='pending'", (item_id,))
            changed = db.execute("SELECT changes()").fetchone()[0]
        return bool(changed)

    def claim_due(self):
        now = self.clock()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            # Recover a crashed worker only after its notification lease expires.
            db.execute("UPDATE reminders SET state='pending' WHERE state='delivering' AND lease_until<=?", (now,))
            row = db.execute("SELECT * FROM reminders WHERE state='pending' AND due_at<=? AND retry_at<=? ORDER BY due_at LIMIT 1", (now, now)).fetchone()
            if row is None:
                return None
            db.execute("UPDATE reminders SET state='delivering', lease_until=?, attempts=attempts+1 WHERE id=?", (now + 60, row['id']))
            return dict(row)

    def finish(self, item_id, error=None):
        with self.connection() as db:
            if error:
                db.execute("UPDATE reminders SET state='pending', retry_at=?, last_error=? WHERE id=? AND state='delivering'", (self.clock()+30, str(error)[:200], item_id))
            else:
                db.execute("UPDATE reminders SET state='notified', notified_at=?, last_error=NULL WHERE id=? AND state='delivering'", (self.clock(), item_id))

    def deliver_one(self, notify):
        item = self.claim_due()
        if item is None:
            return False
        try:
            notify(item)
        except Exception as exc:
            self.finish(item['id'], error=type(exc).__name__)
        else:
            self.finish(item['id'])
        return True


_store = None

def get_reminder_store():
    global _store
    if _store is None:
        _store = ReminderStore()
    return _store
