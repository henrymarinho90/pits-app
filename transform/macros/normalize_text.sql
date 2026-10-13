{#- D100: upper case, no accents (translate, no unaccent extension), collapsed spaces, trimmed.
    Accents are translated BEFORE upper() so the result never depends on the database locale. -#}
{% macro normalize_text(column) -%}
btrim(regexp_replace(
    upper(translate({{ column }}, 'ÁÉÍÓÚÜÑáéíóúüñ', 'AEIOUUNAEIOUUN')),
    '\s+', ' ', 'g'
))
{%- endmacro %}
