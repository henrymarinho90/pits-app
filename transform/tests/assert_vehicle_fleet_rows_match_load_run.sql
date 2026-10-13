{{ config(tags=['vehicle_fleet']) }}
-- Rows per publication must equal row_count of its LATEST load_run (D99: a publication is replaced
-- whole). Full join: a publication without rows, or rows without a load_run, also fail.
with latest as (
    select distinct on (coverage_from) coverage_from as publication_date, row_count, load_id
    from {{ source('ops', 'load_run_fleet') }}
    where dataset = 'vehicle_fleet_snapshot'
    order by coverage_from, load_id desc
),
actual as (
    select make_date(publication_year::int, publication_month::int, 1) as publication_date,
           count(*) as n_rows
    from {{ ref('stg_vehicle_fleet_snapshot') }}
    group by 1
)
select
    coalesce(latest.publication_date, actual.publication_date) as publication_date,
    latest.load_id,
    latest.row_count as expected_rows,
    actual.n_rows as actual_rows
from latest
full outer join actual on actual.publication_date = latest.publication_date
where latest.row_count is distinct from actual.n_rows
