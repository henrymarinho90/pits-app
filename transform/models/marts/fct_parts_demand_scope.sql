-- D134: what the parts-demand mart keeps and what it leaves out, per publication, so the
-- exclusions are visible and the total reconciles with staging. Status is evaluated first, then
-- service; the first exclusion that applies wins. A status or service outside the known set gets
-- a NULL scope_status and fails the not_null test (no invented category).
select
    publication_year,
    publication_month,
    case
        when vehicle_status = 'INCONSISTENTE' then 'excluded_status_inconsistente'
        when vehicle_status = 'ACTIVO' and service_name in ('PARTICULAR', 'PÚBLICO') then 'included'
        when vehicle_status = 'ACTIVO' and service_name = 'OFICIAL' then 'excluded_service_oficial'
        when vehicle_status = 'ACTIVO' and service_name = 'OTROS' then 'excluded_service_otros'
        when vehicle_status = 'ACTIVO' and service_name = 'NO REGISTRA'
            then 'excluded_service_no_registra'
    end as scope_status,
    sum(vehicle_count)::bigint as vehicle_count
from {{ ref('fct_vehicle_fleet_snapshot') }}
group by 1, 2, 3
