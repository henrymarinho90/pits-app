# 01 — Project Brief: Data Platform for an Auto Parts Marketplace

Última actualización: 2026-10-10
Estado: v4 — alcance alineado con D68–D73 (tres productos, mercados por país, fuera de alcance reformulado, diagrama con OLTP, outbox y raw). Métricas (§12) y distinción stock/flujo sin cambios.

## 1. Objetivo personal

Construir un proyecto de portafolio que demuestre, de punta a punta, las habilidades esperadas de un Data Engineer junior y cree una base sólida para avanzar hacia nivel intermedio:

- ingesta reproducible desde fuentes reales;
- almacenamiento raw y capacidad de replay;
- modelado relacional y dimensional;
- calidad de datos y contratos;
- transformaciones con SQL/dbt;
- orquestación, incrementalidad y backfills;
- observabilidad y debugging;
- CI/CD;
- despliegue con Docker;
- documentación técnica y comunicación de resultados.

El proyecto se publicará como caso de estudio en el portafolio de Henry construido con Astro.

## 2. Visión del producto

Pits es un repo con **tres productos** (D68). Cada uno avanza por hitos aprobados uno a uno:

1. **Plataforma de datos** (portafolio de Data Engineering; base actual del repo): ingesta reproducible, raw, normalización, warehouse, transformaciones, orquestación, calidad y analítica. Sus fases están en §10 (D40).
2. **Marketplace web de autopartes y repuestos** para carros y motos, en **Colombia y Estados Unidos** (D71). Sus mercados son domésticos y separados; sin cross-border en el MVP.
3. **App de gestión de talleres pequeños**, **solo Colombia**, con facturación electrónica (D68, D69, D72).

El marketplace debe representar tres necesidades reales del sector:

1. **Encontrar el repuesto correcto.** Resolver compatibilidad entre vehículo, pieza, marca y códigos equivalentes.
2. **Conectar oferta y demanda.** Permitir que compradores y vendedores publiquen, busquen, negocien y generen ofertas o contraofertas.
3. **Convertirse en una fuente de inteligencia del mercado.** Medir disponibilidad, precios, demanda, búsquedas sin resultado, actividad comercial y confiabilidad de los participantes.

El **warehouse es la base analítica**: no procesa checkout, reservas de inventario ni emisión fiscal (D68, D70). Las apps tienen persistencia transaccional y autorización propias (base OLTP separada; D70, D72). Los hechos operativos llegan al warehouse por outbox transaccional y export al raw con manifest.

La plataforma de datos **no construye frontend, pagos ni logística**. Sí construye el modelo de datos y los eventos que esos componentes producirían, usando un generador sintético cuando no exista una fuente real. El frontend de los productos web es un hito de su producto, no de la plataforma (D68, que reemplaza a D34 en ese punto); los pagos y la logística reales siguen fuera hasta una decisión propia.

## 3. Problemas que resuelve

### 3.1 Compatibilidad y equivalencias

El mismo repuesto puede aparecer con:

- número OEM vigente;
- número OEM reemplazado;
- código aftermarket;
- referencia cruzada o interchange;
- SKU interno de un vendedor;
- código de barras.

La plataforma debe poder responder: **“¿qué pieza concreta sirve para este vehículo y bajo qué códigos la puedo encontrar?”**

### 3.2 Fragmentación de inventario

El inventario de repuestos está distribuido entre tiendas, distribuidores, importadores, talleres, concesionarios, fabricantes y personas naturales. La plataforma debe representar **quién tiene qué pieza, en qué ciudad, en qué condición y a qué precio**.

### 3.3 Negociación

Un precio publicado no siempre es el precio final. El dominio debe soportar:

- oferta inicial del comprador o vendedor;
- contraofertas;
- aceptación;
- rechazo;
- retiro;
- expiración.

Estas interacciones se modelarán como eventos para poder analizar conversión, elasticidad y comportamiento de mercado.

### 3.4 Confianza

Existen dos problemas de confianza distintos:

- **Confianza técnica:** qué tan confiable es una persona al contribuir equivalencias o datos de catálogo.
- **Reputación comercial:** qué tan confiable es una cuenta como comprador o vendedor.

Se modelan por separado para evitar mezclar semánticas.

### 3.5 Inteligencia de mercado

La plataforma debe permitir responder preguntas como:

- ¿qué repuestos se buscan más?
- ¿qué búsquedas terminan sin resultados?
- ¿en qué ciudades hay falta de inventario?
- ¿qué marcas y tipos de parte presentan mayor demanda?
- ¿qué diferencia existe entre precio publicado y precio aceptado?
- ¿qué porcentaje de negociaciones termina en orden?
- ¿qué vendedores tienen disponibilidad consistente?
- ¿cómo cambia el precio de una referencia con el tiempo?

Algunas de estas preguntas requieren fases posteriores de historial de precios o streaming.

## 4. Propuesta de valor

1. Catálogo unificado con códigos equivalentes.
2. Compatibilidad repuesto–vehículo (`fitment`).
3. Búsqueda por vehículo, pieza, código, marca y ubicación.
4. Disponibilidad por vendedor y ciudad.
5. Negociaciones y ofertas entre compradores y vendedores.
6. Reputación comercial basada en hechos del marketplace.
7. Sistema independiente de confianza para contribuciones al catálogo.
8. Del síntoma o mantenimiento al kit de repuestos requerido.
9. Analítica de demanda satisfecha e insatisfecha.
10. Base de datos histórica que pueda convertirse en una fuente de inteligencia para comerciantes del sector.

## 5. Mercados y segmento

Mercados domésticos separados (D71). Cada mercado tiene su moneda, impuestos, políticas y vendedores; el catálogo técnico es compartible; no hay cross-border en el MVP.

- **Marketplace:** Colombia y Estados Unidos (moneda COP y USD).
- **App de talleres:** solo Colombia (D68).
- **Plataforma de datos:** Colombia (fuentes de Fase 1 y 1b, D46 y D48) y Estados Unidos (WA DOL, D43). Investigación de mercado de EE. UU.: `09_us_market_research.md`; de Colombia: `08_market_research.md`.

Los actores considerados en el dominio incluyen (pendiente de validar por mercado; detalles de dominio en `05` §F):

- conductor o dueño del vehículo;
- mecánico independiente;
- taller de carros;
- taller de motos;
- tienda de repuestos;
- distribuidor mayorista;
- importador;
- fabricante;
- concesionario;
- persona natural que compra o vende.

Una misma cuenta puede cumplir más de un rol.

## 6. Marcas prioritarias

Hipótesis de trabajo de Henry, pendiente de validación con fuentes en la Fase 0.5:

- Autos: Chevrolet, Renault, Hyundai, Kia, Nissan, Toyota y Mazda.
- Motos: Bajaj, Suzuki, Yamaha, Honda, AKT y las marcas distribuidas por Auteco.

Pendiente:

- validar participación por marca en el parque automotor;
- confirmar portafolio actual de Auteco;
- confirmar marcas con fabricación o ensamble en Colombia.

Ninguna cifra de mercado entra al proyecto como hecho sin fuente citada.

## 7. Fuentes de datos

| Fuente | Tipo | Uso previsto | Estado |
|---|---|---|---|
| Datos Abiertos Colombia / datos.gov.co | Real, pública | Parque automotor, TRM y otras estadísticas disponibles | Por validar datasets y esquema real |
| NHTSA vPIC API | Real, pública | Marcas/modelos/VIN como fuente complementaria | Por validar cobertura para Colombia |
| Catálogos públicos de fabricantes | Metadatos / posible scraping permitido | Descubrimiento de fuentes y procedencia | Revisar términos y `robots.txt` antes de extraer |
| Generador sintético en Python | Sintético | Cuentas, publicaciones, búsquedas, negociaciones, órdenes y reseñas | Por construir |
| Seeds versionados | Curado/manual | Taxonomías de partes, síntomas y valores controlados | Por construir |
| Google Search Console | Real, sitio propio | Demanda orgánica futura del contenido del proyecto | Futuro; requiere sitio publicado y tráfico |

### Regla de procedencia

Cada dato ingerido debe poder responder, cuando aplique:

- de qué sistema vino;
- cuál era su identificador en origen;
- cuándo se extrajo;
- en qué batch llegó;
- dónde está su payload raw;
- qué transformación lo llevó al modelo analítico.

## 8. Alcance

### 8.1 Plataforma de datos (MVP de Data Engineering)

Incluido:

- fuentes reales y sintéticas;
- catálogo y fitment;
- usuarios/cuentas y roles;
- publicaciones e inventario actual;
- búsquedas;
- negociaciones y ofertas;
- órdenes sintéticas;
- reseñas comerciales;
- contribuciones y moderación del catálogo;
- almacenamiento raw;
- PostgreSQL;
- dbt;
- Airflow;
- tests;
- CI/CD;
- Metabase;
- despliegue en VPS.

### 8.2 Productos (por hito; D68)

Cada producto avanza por hitos aprobados uno a uno (D68): un hito se aprueba antes de implementarse.

- **Marketplace web (CO y EE. UU.; D71):** el orden comercial del MVP (taller frente a marketplace) y el stack de la app quedan pendientes (`05` §F).
- **App de taller (CO; D69, D72):** la mano de obra y los servicios entran como entidades operativas nuevas (orden de servicio y sus líneas), con diseño en hito propio. Tenant y autenticación propios (D72).
- **Persistencia de las apps:** base OLTP propia, separada del warehouse por base y rol; los hechos llegan al warehouse por outbox y export al raw (D70).

### 8.3 Fuera de alcance

- pagos reales (fuera hasta una decisión propia; D68);
- logística/envíos;
- checkout, reservas de inventario y emisión fiscal en el warehouse (D68, D70); la emisión fiscal del taller requiere proveedor aprobado (`05` §F);
- cross-border entre Colombia y EE. UU. en el MVP (D71);
- conciliación financiera real;
- extracción de contenido protegido por licencia;
- Spark sin una necesidad de volumen que lo justifique (D6).

La autenticación de producción no es parte de la plataforma de datos; las apps la tendrán en su propio hito (D72).

## 9. Arquitectura conceptual

```text
PLATAFORMA DE DATOS (warehouse analítico)

Fuentes reales (TRM, RUNT, WA DOL)     Generador sintético
            \                              /
             ------ ingestion ------      (payload + manifest, D65)
                        |
                        v
S3 raw (SeaweedFS, D57): payloads inmutables
                        |
                        v
            normalized files / loaders
                        |
                        v
PostgreSQL WAREHOUSE (analítico; sin checkout, reservas ni emisión fiscal; D68, D70)
                        |
                        v
          dbt staging -> intermediate -> marts
                        |
           +------------+------------+
           |                         |
       data tests                 Metabase
           |
   Airflow orquesta datos (ingesta, load, dbt, tests)

PRODUCTOS (apps, por hito; D68)

Marketplace web (CO, US)        App de taller (CO)
            \                          /
             PostgreSQL OLTP propia por app
             (base y rol separados del warehouse; D70; tenant_id, D72)
                        |
                        v
             tabla outbox transaccional (event_id)
                        |
                        v
   export con manifest hacia S3 raw (al menos una vez; dedupe por event_id; no exactly-once; D70)

Worker operacional: facturas electrónicas y webhooks (no es Airflow; D70)
```

## 10. Fases y objetivos de aprendizaje

| Fase | Entregable | Habilidad demostrada |
|---|---|---|
| 0 | Dominio, ERD, decisiones y alcance | Modelado y traducción de negocio a datos |
| 0.5 | Investigación de mercado con fuentes | Evaluación de fuentes, evidencia y schemas reales |
| 1 | Primera ingesta real a storage S3 (SeaweedFS, D57) + manifest + tests | APIs, raw storage, idempotencia y contratos |
| 2 | Generador sintético del marketplace | Generación reproducible y modelado de eventos |
| 3 | Carga a Postgres + dbt staging/intermediate/marts | SQL, dimensional modeling, incrementalidad y tests |
| 4 | DAGs de Airflow, schedules y backfills | Orquestación, dependencias, retries y recuperación |
| 5 | GitHub Actions | CI, linting, unit tests y `dbt build` |
| 6 | Deploy en OVH/Coolify + Metabase + observabilidad mínima | Docker, operación y consumo analítico |
| 7 | Caso de estudio en portafolio | Comunicación técnica y storytelling de datos |
| 8 opcional | Historial de precios/SCD2 | Slowly Changing Dimensions e historia |
| 9 opcional | Streaming de búsquedas/ofertas con Redpanda | Event streaming y consumidores |
| 10 opcional | Réplica cloud con IaC | Terraform y arquitectura cloud |

Las fases 0 a 10 no cambian por D68. Pista de productos (D68, sin fechas): marketplace web y app de taller avanzan por hitos aprobados uno a uno, fuera de esta tabla. Su orden comercial (taller frente a marketplace) y el stack de las apps quedan abiertos (`05` §F; `06` §1-bis).

## 11. Criterios de éxito técnicos

El proyecto se considera exitoso cuando:

- una persona puede levantar el entorno local siguiendo el README;
- la misma entrada produce el mismo resultado al reejecutarse;
- un batch puede reejecutarse sin crear duplicados lógicos;
- los payloads raw permanecen disponibles para replay;
- fallas de esquema y reglas de negocio se detectan automáticamente;
- existen tests unitarios y de datos en los puntos críticos;
- los DAGs soportan retry y backfill;
- cada modelo analítico tiene grano y propósito documentado;
- se puede rastrear un dato analítico hacia su fuente;
- CI bloquea cambios que rompen código o modelos;
- el pipeline corre desplegado y genera métricas visibles en Metabase;
- el caso de estudio explica decisiones, errores, trade-offs y aprendizajes.

## 12. Métricas de producto que el warehouse debe poder producir

Como mínimo:

- búsquedas por día y por vehículo;
- porcentaje de búsquedas sin resultados;
- publicaciones activas y disponibilidad por ciudad;
- precio publicado promedio/mediano por tipo de parte;
- negociaciones iniciadas;
- tasa de aceptación de ofertas;
- diferencia entre precio publicado y precio aceptado;
- órdenes creadas y completadas;
- compradores/vendedores activos;
- cobertura de fitment;
- contribuciones de catálogo sugeridas/certificadas/rechazadas;
- calidad y frescura de las fuentes.

## 13. Principios del proyecto

1. **No inventar hechos de mercado.** Hipótesis y datos sintéticos se etiquetan como tales.
2. **Raw primero.** Conservar la entrada original antes de transformarla.
3. **Grano antes que columnas.** Cada tabla declara qué representa una fila.
4. **Eventos antes que scores.** La reputación se deriva de hechos observables; no sustituye los eventos fuente.
5. **Idempotencia por diseño.** Reejecutar no debe corromper datos.
6. **El historial importa.** No sobrescribir hechos que se necesiten para auditoría.
7. **Complejidad justificada.** No incorporar herramientas solo para hacer el stack más grande.
