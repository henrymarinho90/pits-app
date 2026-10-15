{{ config(tags=['fleet_brand', 'brand_synthetic']) }}
-- D142/D145: the publication of the synthetic cells is the one the pooled weights of D140 use
-- (the latest of fct_parts_demand_fleet). Compared against fct_regional_brand_weight, a
-- fleet_brand node, never against a vehicle_fleet node (D139). Fails on a cell publication that
-- differs from the weight publication. The calibrated brand rows must also carry that weight
-- publication.
with weight as (
    select distinct weight_publication_year, weight_publication_month
    from {{ ref('fct_regional_brand_weight') }}
),

cells as (
    select distinct publication_year, publication_month
    from {{ ref('fct_synthetic_fleet_cell') }}
)

select
    'cell' as kind,
    c.publication_year,
    c.publication_month
from cells as c
where not exists (
    select 1 from weight as w
    where w.weight_publication_year = c.publication_year
        and w.weight_publication_month = c.publication_month
)
union all
select
    'brand' as kind,
    b.publication_year,
    b.publication_month
from {{ ref('fct_synthetic_brand_fleet') }} as b
where b.brand_norm <> 'SIN CALIBRACION'
    and (
        b.weight_publication_year is distinct from b.publication_year
        or b.weight_publication_month is distinct from b.publication_month
    )
group by b.publication_year, b.publication_month
