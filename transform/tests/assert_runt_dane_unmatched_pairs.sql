{{ config(tags=['vehicle_fleet', 'divipola'], severity='warn') }}
-- D128: any RUNT pair without a DANE code warns, listing its cells and its vehicles in the latest
-- publication (all statuses). The row stays in the marts with NULL dane_* columns; the error
-- threshold is assert_runt_dane_unmatched_vehicle_share.
with latest as (
    select publication_year, publication_month
    from {{ ref('stg_vehicle_fleet_snapshot') }}
    group by publication_year, publication_month
    order by publication_year desc, publication_month desc
    limit 1
)

select
    m.department_name_norm,
    m.municipality_name_norm,
    m.exception_reason,
    count(s.vehicle_count) as latest_cells,
    coalesce(sum(s.vehicle_count), 0) as latest_vehicles
from {{ ref('map_runt_municipality_dane') }} as m
left join {{ ref('stg_vehicle_fleet_snapshot') }} as s
    on s.department_name_norm = m.department_name_norm
    and s.municipality_name_norm = m.municipality_name_norm
    and (s.publication_year, s.publication_month) = (select publication_year, publication_month from latest)
where m.dane_municipality_code is null
group by m.department_name_norm, m.municipality_name_norm, m.exception_reason
order by latest_vehicles desc
