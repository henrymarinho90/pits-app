-- D126: one row per RUNT (department, municipality) pair seen in ANY publication, with its DANE code.
-- 1) A curated exception (seed, reviewed in the PR) takes precedence.
-- 2) Otherwise the automatic match on the normalized names (same macro on both sides, D100/D125).
-- No fuzzy rules here: a pair that neither matches nor is curated keeps a NULL code (D128) and the
-- coverage tests decide whether that is a warning or a failure.
-- Reads staging on purpose (like the fct): a failed staging test leaves the previous map intact.
with pairs as (
    select distinct department_name_norm, municipality_name_norm
    from {{ ref('stg_vehicle_fleet_snapshot') }}
),

auto_match as (
    select department_name_norm, municipality_name_norm, dane_municipality_code
    from {{ ref('dim_municipality') }}
),

curated as (
    select
        department_name_norm,
        municipality_name_norm,
        nullif(btrim(dane_municipality_code), '') as dane_municipality_code,
        reason
    from {{ ref('runt_municipality_dane_exception') }}
),

matched as (
    select
        p.department_name_norm,
        p.municipality_name_norm,
        case
            when c.department_name_norm is not null then c.dane_municipality_code
            else a.dane_municipality_code
        end as dane_municipality_code,
        case
            when c.dane_municipality_code is not null then 'curated'
            when c.department_name_norm is null and a.dane_municipality_code is not null
                then 'auto_norm'
        end as match_method,
        c.reason as exception_reason
    from pairs as p
    left join auto_match as a
        on a.department_name_norm = p.department_name_norm
        and a.municipality_name_norm = p.municipality_name_norm
    left join curated as c
        on c.department_name_norm = p.department_name_norm
        and c.municipality_name_norm = p.municipality_name_norm
)

select
    department_name_norm,
    municipality_name_norm,
    dane_municipality_code,
    left(dane_municipality_code, 2) as dane_department_code,
    match_method,
    exception_reason
from matched
