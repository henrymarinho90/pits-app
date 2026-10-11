-- dbt reads the landing and audit tables it models from (D86). Executed as the owner.
-- Future landing tables get SELECT for the transformer via the bootstrap default privileges;
-- tables that already exist need the explicit grants below.

GRANT SELECT ON landing.fx_rate, ops.load_run TO {{transformer_role}};
