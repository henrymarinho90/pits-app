"""Advisory lock keys shared by every writer of the warehouse (D90).

`WAREHOUSE_LOCK_KEY` is the single write lock of the warehouse database. The three writers
take it so that they never overlap: the load (`pg_try_advisory_xact_lock`, per transaction),
the transform (`pg_try_advisory_lock`, per session, for the whole dbt run) and the migrate
(`pg_try_advisory_lock`, per session, from the bootstrap objects to the last migration).

`LOAD_LOCK_KEY == TRANSFORM_LOCK_KEY == WAREHOUSE_LOCK_KEY` on purpose: in PostgreSQL 17 a
session-level and a transaction-level advisory lock with the same key exclude each other, so
sharing one key is what makes the load block the transform (and the other way round). Do not
give them different values.

`RUN_LOCK_KEY` (held in the maintenance database for the whole `pits db` run) and
`MIGRATE_LOCK_KEY` (per-migration transaction lock inside the warehouse database) are
different keys with different scopes and stay distinct from the warehouse key.
"""

from __future__ import annotations

RUN_LOCK_KEY = 0x5049545301
MIGRATE_LOCK_KEY = 0x5049545302
WAREHOUSE_LOCK_KEY = 0x5049545303

LOAD_LOCK_KEY = WAREHOUSE_LOCK_KEY
TRANSFORM_LOCK_KEY = WAREHOUSE_LOCK_KEY
