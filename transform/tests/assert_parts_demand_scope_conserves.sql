{{ config(tags=['vehicle_fleet', 'divipola', 'parts_demand']) }}
-- D134: per publication, the sum of every scope_status equals the staging vehicle total (nothing
-- is lost or invented by the status/service rules). Full join: a publication missing on either
-- side also fails.
with scope as (
    select publication_year, publication_month, sum(vehicle_count) as scope_total
    from {{ ref('fct_parts_demand_scope') }}
    group by 1, 2
),

stg as (
    select publication_year, publication_month, sum(vehicle_count) as stg_total
    from {{ ref('stg_vehicle_fleet_snapshot') }}
    group by 1, 2
)

select
    coalesce(scope.publication_year, stg.publication_year) as publication_year,
    coalesce(scope.publication_month, stg.publication_month) as publication_month,
    scope.scope_total,
    stg.stg_total
from scope
full outer join stg
    on stg.publication_year = scope.publication_year
    and stg.publication_month = scope.publication_month
where scope.scope_total is distinct from stg.stg_total
