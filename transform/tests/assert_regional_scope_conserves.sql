{{ config(tags=['fleet_brand']) }}
-- D140: per source_system, nothing is lost or invented by the scope rules. The scope total must
-- equal the staging total, the staging row count must equal row_count of the LATEST load_run of
-- the source, and (when the manifest carries it) the scope total must equal its vehicle_total.
-- Full join: a source with rows but no load_run, or a load_run without rows, also fails.
with scope as (
    select source_system, sum(vehicle_count) as scope_total
    from {{ ref('fct_regional_fleet_brand_scope') }}
    group by source_system
),

stg as (
    select source_system, sum(vehicle_count) as stg_total, count(*) as stg_rows
    from {{ ref('stg_regional_fleet_brand') }}
    group by source_system
),

latest as (
    select distinct on (source_system)
        source_system,
        row_count,
        (normalized_manifest ->> 'vehicle_total')::bigint as manifest_total
    from {{ source('ops', 'load_run_brand') }}
    where dataset = 'regional_fleet_brand_count'
    order by source_system, load_id desc
)

select
    coalesce(stg.source_system, scope.source_system, latest.source_system) as source_system,
    scope.scope_total,
    stg.stg_total,
    stg.stg_rows,
    latest.row_count,
    latest.manifest_total
from stg
full outer join scope on scope.source_system = stg.source_system
full outer join latest on latest.source_system = coalesce(stg.source_system, scope.source_system)
where scope.scope_total is distinct from stg.stg_total
   or stg.stg_rows is distinct from latest.row_count
   or (latest.manifest_total is not null and latest.manifest_total is distinct from scope.scope_total)
