"""The advisory lock keys of the warehouse writers (D90)."""

from pits.transform.runner import TRANSFORM_LOCK_KEY
from pits.warehouse.bootstrap import RUN_LOCK_KEY
from pits.warehouse.fx_rate_load import LOAD_LOCK_KEY
from pits.warehouse.locks import MIGRATE_LOCK_KEY, WAREHOUSE_LOCK_KEY


def test_load_transform_and_warehouse_share_one_key_and_the_others_differ():
    # Same key on purpose (D90): session and transaction locks with one key exclude each other.
    assert LOAD_LOCK_KEY == TRANSFORM_LOCK_KEY == WAREHOUSE_LOCK_KEY
    assert len({RUN_LOCK_KEY, MIGRATE_LOCK_KEY, WAREHOUSE_LOCK_KEY}) == 3
