{{ config(tags=['vehicle_fleet', 'divipola', 'parts_demand']) }}
-- D132/D99: a publication is replaced whole, so fct_parts_demand_fleet has exactly one load_id
-- per publication (max(load_id) in the model would hide a mix otherwise).
select publication_year, publication_month, count(distinct load_id) as load_ids
from {{ ref('fct_parts_demand_fleet') }}
group by publication_year, publication_month
having count(distinct load_id) <> 1
