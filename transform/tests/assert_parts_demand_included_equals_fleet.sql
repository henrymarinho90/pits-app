{{ config(tags=['vehicle_fleet', 'divipola', 'parts_demand']) }}
-- D134: per publication, the 'included' vehicles equal the sum of active_vehicle_count of
-- fct_parts_demand_fleet (D132): both marts apply the same filter.
with scope as (
    select publication_year, publication_month, vehicle_count as included_total
    from {{ ref('fct_parts_demand_scope') }}
    where scope_status = 'included'
),

fleet as (
    select publication_year, publication_month, sum(active_vehicle_count) as fleet_total
    from {{ ref('fct_parts_demand_fleet') }}
    group by 1, 2
)

select
    coalesce(scope.publication_year, fleet.publication_year) as publication_year,
    coalesce(scope.publication_month, fleet.publication_month) as publication_month,
    scope.included_total,
    fleet.fleet_total
from scope
full outer join fleet
    on fleet.publication_year = scope.publication_year
    and fleet.publication_month = scope.publication_month
where scope.included_total is distinct from fleet.fleet_total
