from __future__ import annotations

import hashlib
import secrets

from app.db.session import Database

class InstanceService:
    def __init__(self, db: Database) -> None:
        self._db = db

    def ensure_seed(self) -> str:
        seed = secrets.token_hex(32)
        created = self._db.execute(
            """
            INSERT INTO instance_state (singleton_key, instance_seed)
            VALUES (%s, %s)
            ON CONFLICT (team_id, singleton_key) DO NOTHING
            RETURNING instance_seed
            """,
            ["default", seed],
        )
        if created is not None:
            return str(created["instance_seed"])

        row = self._db.fetch_one(
            """
            SELECT instance_seed
            FROM instance_state
            WHERE team_id = current_setting('app.team_id') AND singleton_key = %s
            """,
            ["default"],
        )
        if row is not None:
            return str(row["instance_seed"])
        return seed

    def derive_token(self, label: str) -> str:
        seed = self.ensure_seed()
        return hashlib.sha256(f"{seed}:{label}".encode()).hexdigest()
