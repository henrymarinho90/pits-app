{{ config(tags=['vehicle_fleet', 'divipola']) }}
-- D128: fails when the vehicles of the LATEST publication without a DANE code (every status: this
-- is data quality, not demand) exceed var('dane_unmatched_vehicle_share_max') of all its vehicles.
-- A small new municipality only warns (assert_runt_dane_unmatched_pairs); a big one (for example
-- a rename of Bogota) stops the enriched mart, which keeps its previous content.
with latest as (
    select publication_year, publication_month
    from {{ ref('stg_vehicle_fleet_snapshot') }}
    group by publication_year, publication_month
    order by publication_year desc, publication_month desc
    limit 1
),

totals as (
    select
        sum(s.vehicle_count) as total_vehicles,
        coalesce(sum(s.vehicle_count) filter (where m.dane_municipality_code is null), 0)
            as unmatched_vehicles
    from {{ ref('stg_vehicle_fleet_snapshot') }} as s
    inner join latest as l
        on l.publication_year = s.publication_year
        and l.publication_month = s.publication_month
    left join {{ ref('map_runt_municipality_dane') }} as m
        on m.department_name_norm = s.department_name_norm
        and m.municipality_name_norm = s.municipality_name_norm
)

select
    total_vehicles,
    unmatched_vehicles,
    unmatched_vehicles::numeric / total_vehicles as unmatched_share,
    {{ var('dane_unmatched_vehicle_share_max') }} as max_share
from totals
where total_vehicles > 0
  and unmatched_vehicles::numeric / total_vehicles > {{ var('dane_unmatched_vehicle_share_max') }}
