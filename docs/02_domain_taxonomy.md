# 02 — Taxonomía del dominio

Última actualización: 2026-10-03
Estado: v11 — referencia vigente para el dominio.

Los valores en `código` son los valores previstos para tablas, seeds y columnas: inglés en `snake_case`.

## 1. Propósito

Este archivo define el vocabulario del negocio. No define todavía el esquema físico completo; ese trabajo está en `03_data_model.md`.

El dominio se divide en cuatro áreas:

1. **Catálogo técnico:** partes, códigos, equivalencias y compatibilidad.
2. **Conocimiento técnico:** síntomas, reparaciones, mantenimiento y kits.
3. **Marketplace:** cuentas, roles, publicaciones, búsquedas, negociaciones, órdenes y reseñas.
4. **Gobernanza de datos:** contribuidores, moderación, procedencia y confianza de los datos técnicos.

## 2. Cambios principales de la v10

1. Se separa formalmente **confianza del contribuidor de catálogo** de **reputación comercial del marketplace**.
2. Se agrega el concepto de `account`: una misma cuenta puede comprar, vender y contribuir datos.
3. Se incorporan `negotiation` y `offer_event` para ofertas y contraofertas.
4. Se define vocabulario inicial para órdenes y reseñas comerciales.
5. Se corrige la granularidad conceptual de publicaciones para considerar ubicación.
6. El historial completo de decisiones queda en `05_decisions_log.md`; este archivo mantiene principalmente el estado vigente.

---

# A. Catálogo técnico

## 3. Criterio de clasificación de partes

Las familias agrupan por **sistema funcional** —por ejemplo frenos, transmisión o motor— y no por tipo de vehículo.

El tipo de vehículo se expresa mediante `vehicle_scope`:

- `car`
- `motorcycle`
- `both`

Esto permite que un filtro como “Frenos” funcione para carros y motos sin mantener dos árboles paralelos.

Excepción: sistemas sin equivalente razonable en carros pueden conservar una familia propia, como `handlebar_controls` y `support_ergonomics`.

## 4. Jerarquía de partes

Jerarquía:

```text
part_family -> part_subfamily -> part_type -> part
```

Ejemplo:

```text
engine -> cooling -> thermostat -> termostato específico con marca y códigos
```

Definiciones:

- `part_family`: sistema funcional amplio.
- `part_subfamily`: agrupación funcional dentro de una familia.
- `part_type`: clase de pieza; por ejemplo `thermostat`.
- `part`: pieza concreta comercializable, con marca y uno o varios códigos.

Los kits de reparación apuntan a `part_type`; `fitment` resuelve qué `part` concreto sirve para cada vehículo.

### 4.1 Familias y subfamilias actuales

| part_family | part_subfamily | vehicle_scope | Tipos de parte de ejemplo |
|---|---|---|---|
| `engine` | `internal_engine` | both | pistones, anillos, empaques, válvulas, distribución, bomba de aceite |
| `engine` | `cooling` | both | termostato, radiador, bomba de agua, tapa del reservorio, mangueras, refrigerante |
| `engine` | `fuel` | both | inyectores, bomba de combustible, filtro de combustible, carburador |
| `engine` | `wet_clutch` | motorcycle | discos de fricción, separadores |
| `engine` | `kick_start` | motorcycle | patada de encendido |
| `engine` | `sequential_shift` | motorcycle | selector y horquillas de cambio |
| `electrical` | `charging_starting` | both | batería, alternador/estator, motor de arranque |
| `electrical` | `ignition` | both | bujías, bobinas, CDI |
| `electrical` | `sensors` | both | sensores |
| `electrical` | `lighting` | both | luces, farolas, bombillas |
| `electrical` | `wiring` | both | cables, arneses, conectores |
| `transmission` | `clutch` | car | embrague seco |
| `transmission` | `gearbox` | car | caja de cambios |
| `transmission` | `axles_joints` | car | juntas homocinéticas, ejes |
| `transmission` | `final_drive` | motorcycle | cadena, piñón, corona |
| `suspension` | `car_suspension` | car | amortiguadores, espirales, bujes, barras, tijeras |
| `suspension` | `front_fork` | motorcycle | barras, tijas, retenes, guardapolvos |
| `suspension` | `rear_suspension` | motorcycle | amortiguador trasero, basculante |
| `steering` | `car_steering` | car | terminales, rótulas, cremallera, bomba de dirección |
| `brakes` | `brakes` | both | pastillas, bandas, discos, campanas, cilindros, líquido |
| `handlebar_controls` | `levers` | motorcycle | manetas de freno y embrague |
| `handlebar_controls` | `throttle` | motorcycle | puño de acelerador |
| `handlebar_controls` | `control_cables` | motorcycle | guayas de acelerador, embrague y freno |
| `handlebar_controls` | `switch_housings` | motorcycle | comandos o piñas |
| `chassis_body` | `car_body` | car | guardabarros, espejos, capó |
| `chassis_body` | `fairing` | motorcycle | carenado, tapas laterales, visor, colín, quilla |
| `support_ergonomics` | `stands` | motorcycle | caballete central, pata lateral |
| `support_ergonomics` | `footrests` | motorcycle | estriberas o posapiés |
| `filters_fluids` | `filters_fluids` | both | aceite, filtro de aire, filtro de aceite, filtro de cabina |
| `exhaust` | `exhaust` | both | silenciador, catalizador, sonda lambda |
| `wheels_tires` | `tires` | both | llantas, neumáticos, cámaras |
| `wheels_tires` | `rims` | both | rines |
| `wheels_tires` | `wheel_bearings` | both | rodamientos de rueda |

Notas de clasificación vigentes:

- Las tijas permanecen en `suspension/front_fork`.
- Los comandos o piñas permanecen en `handlebar_controls`.
- `rear_suspension` es una subfamilia independiente para motos.

La lista exhaustiva de `part_type` debe vivir como seed versionado, no como texto libre dentro de este documento.

## 5. Tipos de código de parte

Una misma pieza física puede tener muchos códigos. Todos pueden resolver al mismo `part_id`.

| code_type | Significado |
|---|---|
| `oem_current` | Número OEM vigente |
| `oem_superseded` | Número OEM reemplazado por otro |
| `aftermarket` | Código de fabricante no original |
| `interchange` | Referencia cruzada de equivalencia |
| `internal_sku` | Código interno de vendedor/almacén |
| `barcode` | EAN/UPC u otro código de barras |

Atributos previstos por código:

- `brand`
- `valid_from`
- `valid_to`
- referencia de procedencia

## 6. Vehículo y compatibilidad

Atributos vigentes del vehículo:

- `vehicle_type`
- `make`
- `model`
- `year_from`
- `year_to`
- `engine_displacement_cc`
- `fuel_type`
- `trim`
- `manufacture_country`

`manufacture_country` usa ISO 3166-1 alpha-2 cuando se conozca.

La compatibilidad se representa con `fitment`: una relación entre una pieza concreta y una configuración de vehículo.

La decisión de manejar años como rango es una **simplificación del MVP** y no debe interpretarse como una afirmación universal de que ningún fabricante cambia piezas dentro de un mismo año modelo. Si una fuente futura exige mayor precisión, el modelo deberá evolucionar.

---

# B. Gobernanza y confianza del catálogo

## 7. Contributor de catálogo

Un `catalog_contributor` es una cuenta que propone o revisa datos técnicos del catálogo.

Tipos previstos:

- `manufacturer_rep`
- `distributor`
- `seller`
- `community`

Esta identidad puede estar vinculada a una `account` del marketplace, pero su confianza técnica se calcula de forma independiente de la reputación comercial.

## 8. Componentes del contributor trust score

El score técnico conserva la lógica definida previamente.

| Componente | Puntos máximos |
|---|---:|
| Google Business Profile | 50 |
| Historial de ediciones | 30 |
| Certificación fabricante/distribuidor | 20 |

```text
contributor_trust_score = gbp_score + edit_history_score + certification_score
```

### 8.1 Factor de volumen

```text
volume_factor(n, n_full) = min(1, ln(1 + n) / ln(1 + n_full))
```

Parámetros vigentes:

- `gbp_review_count_full = 100`
- `reviewed_edits_full = 50`

### 8.2 GBP score

```text
gbp_score = 50 * (gbp_rating / 5) * volume_factor(gbp_review_count, 100)
```

Reglas de borde:

- sin perfil vinculado: 0;
- cero reseñas: 0;
- rating nulo: 0;
- rating válido se acota a 1–5.

### 8.3 Historial de ediciones y test inicial

```text
w = volume_factor(reviewed, 50)

edit_history_score = 30 * (
    w * approved / reviewed
    + (1 - w) * initial_test_score / 100
)
```

Cuando `reviewed = 0`, se usa únicamente el test y no se divide por cero.

El peso del test disminuye gradualmente hasta desaparecer cuando el contribuidor alcanza 50 ediciones revisadas.

### 8.3.1 Casos de prueba verificados

Verificados con Python. Se convertirán en tests unitarios del cálculo en dbt o pytest.

| Caso | Entrada | Puntaje |
|---|---|---|
| GBP, muy buena calificación, pocas reseñas | 4,9 estrellas, 10 reseñas | 25,5 / 50 |
| GBP, buena calificación, volumen completo | 4,5 estrellas, 100 reseñas | 45,0 / 50 |
| GBP, calificación media, mucho volumen | 3,0 estrellas, 500 reseñas | 30,0 / 50 |
| GBP, una sola reseña perfecta | 5,0 estrellas, 1 reseña | 7,5 / 50 |
| GBP sin reseñas o sin perfil | 0 reseñas o calificación nula | 0 / 50 |
| Historial, test 0, 9 aprobadas de 10 | `initial_test_score` = 0 | 16,5 / 30 |
| Historial, test 0, 45 aprobadas de 50 | `initial_test_score` = 0 | 27,0 / 30 |
| Historial, test 90, sin ediciones revisadas | 0 revisadas | 27,0 / 30 |
| Historial, test 90, 1 aprobada de 1 | mezcla gradual | 27,5 / 30 |
| Historial, test 90, 0 aprobadas de 1 | mezcla gradual | 22,2 / 30 |

Caso que justificó la mezcla gradual (D26): con la regla de reemplazo, un contribuidor con 90
en el test bajaba de 27,0 a 5,3 puntos al acertar su primera edición.

### 8.4 Certificación

```text
certification_score = 20 if is_certified else 0
```

Se otorgan máximo 20 puntos aunque una cuenta tenga más de una clase de certificación.

## 9. Senior contributor

Existen dos caminos:

| Camino | Condición |
|---|---|
| Reputación técnica | `contributor_trust_score >= 50` |
| Historial comprobado | `reviewed_edits >= 50` y `approval_rate >= 0.90` |

El test inicial no cuenta como historial revisado.

La condición de senior se recalcula; puede perderse si el historial deja de cumplir el umbral.

## 10. Estados de una contribución técnica

| status | Significado |
|---|---|
| `suggested` | Pendiente de revisión |
| `certified` | Aprobada o certificada automáticamente |
| `rejected` | Rechazada |

Reglas:

1. Cualquier contribuidor puede proponer cambios.
2. Si era senior al enviar, la propuesta puede quedar certificada automáticamente.
3. Una revisión posterior puede aprobar o rechazar la propuesta.
4. El sistema conserva una foto de la condición de senior al momento del envío.
5. El historial de cambios y revisiones es append-only.

---

# C. Marketplace

## 11. Cuenta y roles

`account` representa a la identidad que participa en la plataforma.

### 11.1 Tipo de cuenta

| account_type | Descripción |
|---|---|
| `individual` | Persona natural |
| `business` | Negocio u organización |

### 11.2 Roles

Una cuenta puede tener varios roles simultáneos:

- `buyer`
- `seller`
- `catalog_contributor`

No se crearán identidades separadas para comprador y vendedor cuando se trate de la misma cuenta.

La clasificación funcional (`buyer_type` o `seller_type`) se guarda en el rol, no en el perfil
comercial, porque las cuentas individuales también la necesitan (por ejemplo, `driver` o
`independent_mechanic`). Ver `account_role.role_type` en `03_data_model.md`.

## 12. Buyer types

Cuando una cuenta compra, puede clasificarse funcionalmente como:

| buyer_type | Nombre |
|---|---|
| `independent_mechanic` | Mecánico particular |
| `car_workshop` | Taller de autos |
| `motorcycle_workshop` | Taller de motos |
| `parts_store` | Tienda de repuestos |
| `wholesale_distributor` | Distribuidor mayorista |
| `manufacturer` | Fabricante |
| `driver` | Conductor o dueño del vehículo |

## 13. Seller types

| seller_type | Nombre |
|---|---|
| `parts_store` | Tienda de repuestos |
| `wholesale_distributor` | Distribuidor mayorista |
| `manufacturer` | Fabricante |
| `importer` | Importador |
| `dealership` | Concesionario |
| `workshop` | Taller |
| `individual` | Persona natural |

## 14. Publicaciones y disponibilidad

Una publicación representa la oferta comercial de una pieza por una cuenta vendedora en una ubicación y condición determinadas.

Condiciones iniciales:

- `new`
- `used`

El grano conceptual es:

```text
seller + part + condition + location
```

Un vendedor puede publicar la misma parte en varias ciudades.

Disponibilidad actual:

```text
in_stock = stock_qty > 0
```

`in_stock` se deriva; no se almacena como bandera independiente.

## 15. Búsquedas

Filtros primarios definidos por Henry:

- marca;
- modelo;
- año.

Filtros secundarios:

- tipo de vehículo;
- cilindraje;
- país de fabricación;
- familia;
- subfamilia;
- tipo de parte;
- marca del repuesto;
- condición;
- tipo de código;
- ciudad;
- disponibilidad.

Las búsquedas con cero resultados son un hecho analítico importante para demanda insatisfecha.

## 16. Negociaciones y ofertas

Una `negotiation` representa una conversación comercial sobre una publicación entre un comprador y un vendedor.

Las propuestas y cambios de estado se conservan como `offer_event` append-only.

Tipos de evento iniciales:

| event_type | Significado |
|---|---|
| `offer_created` | Se propone un monto |
| `counteroffer_created` | La otra parte propone un monto diferente |
| `accepted` | Se acepta la propuesta vigente |
| `rejected` | Se rechaza la propuesta vigente |
| `withdrawn` | Quien hizo la oferta la retira |
| `expired` | La oferta vence |

Cada propuesta monetaria debe conservar:

- actor que la hizo;
- monto;
- moneda;
- cantidad;
- timestamp.

Una aceptación puede originar una `sales_order`.

## 17. Órdenes

Estados iniciales propuestos para el generador sintético:

- `created`
- `confirmed`
- `completed`
- `cancelled`
- `returned`

Cada orden representa una relación entre **un comprador y un vendedor**. Si una experiencia futura permite un carrito con productos de varios vendedores, el checkout genera una orden separada por vendedor.

El modelo debe conservar el precio acordado en la orden aunque luego cambie el precio publicado.

Pagos y logística reales quedan fuera del MVP.

## 18. Reputación comercial

La reputación comercial responde si una cuenta se comporta de forma confiable dentro del marketplace.

No comparte fórmula con `contributor_trust_score`.

Hechos potenciales para un mart futuro:

- órdenes completadas;
- cancelaciones;
- devoluciones;
- reseñas recibidas;
- disputas, si se modelan;
- antigüedad y volumen de actividad.

La fórmula definitiva **queda abierta** hasta disponer del modelo fuente y de datos sintéticos suficientes para probar comportamiento y casos de borde.

## 19. Reseñas comerciales

Una reseña debe estar vinculada a una transacción/orden para reducir reviews sin evidencia de interacción.

Dimensiones iniciales:

- calificación general 1–5;
- comentario opcional;
- rol evaluado: comprador o vendedor.

Si en una fase futura se agregan subratings —por ejemplo exactitud del producto, comunicación o cumplimiento— deberán documentarse como nueva decisión.

---

# D. Conocimiento técnico

## 20. Repair jobs

`repair_job` conecta un problema o mantenimiento con los tipos de parte necesarios.

Estructura:

- `symptom`: problema genérico;
- `repair_job`: trabajo aplicado a un vehículo o alcance;
- `repair_job_part`: `part_type` requerido, cantidad y obligatoriedad.

## 21. Job categories

| job_category | Nombre | Trigger |
|---|---|---|
| `corrective_repair` | Reparación correctiva | Síntoma |
| `preventive_maintenance` | Mantenimiento preventivo | Kilometraje o tiempo |

Reglas:

- reparación correctiva requiere síntoma;
- mantenimiento preventivo requiere `interval_km` o `interval_months`;
- intervalos reales deben citar manual del fabricante;
- en datos sintéticos, un intervalo sin manual se etiqueta como ilustrativo.

## 22. Quantity units

Valores provisionales:

- `piece`
- `pair`
- `set`
- `liter`

Pendiente validar si se necesitan unidades adicionales como `gallon`, `quart` u otras presentaciones usadas comercialmente en Colombia.

## 23. Síntomas frecuentes — carros

Fuente: experiencia de Henry en el sector. No representan un ranking estadístico de frecuencia.

| symptom | vehicle_scope | Problema | Familias relacionadas |
|---|---|---|---|
| `suspension_wear` | car | Desgaste de suspensión por huecos/resaltos | `suspension`, `steering` |
| `battery_failure` | both | Batería descargada o al final de vida útil | `electrical/charging_starting` |
| `brake_issues` | both | Chillidos, pastillas gastadas, discos deformados | `brakes` |
| `engine_overheating` | both | Recalentamiento | `engine/cooling` |
| `oil_leaks` | both | Fugas por empaques, retenedores o tapas | `engine/internal_engine` |
| `check_engine_light` | car | Testigo asociado a sensores/emisiones | `electrical/sensors`, `exhaust` |
| `transmission_failure` | car | Golpes, patinadas o ruidos | `transmission`, `filters_fluids` |
| `irregular_tire_wear` | car | Desgaste irregular | `wheels_tires`, `suspension`, `steering` |
| `charging_starting_failure` | car | Alternador o motor de arranque | `electrical/charging_starting` |
| `high_fuel_consumption` | car | Consumo elevado asociado a mezcla/encendido/filtros | `engine/fuel`, `electrical/ignition`, `electrical/sensors`, `filters_fluids` |

## 24. Síntomas frecuentes — motos

Las fuentes listadas en la versión anterior son cualitativas y algunas no son colombianas. Sirven para construir ejemplos del catálogo, no para afirmar prevalencia en Colombia.

| symptom | vehicle_scope | Problema | Familias relacionadas |
|---|---|---|---|
| `battery_failure` | both | Problemas de batería/encendido | `electrical/charging_starting` |
| `brake_issues` | both | Desgaste de frenos | `brakes` |
| `final_drive_wear` | motorcycle | Desgaste del kit de arrastre | `transmission/final_drive` |
| `electrical_faults` | motorcycle | Cableado, contactos o iluminación | `electrical/wiring`, `electrical/lighting` |
| `fuel_delivery_issues` | motorcycle | Carburación o inyección | `engine/fuel` |
| `clutch_wear` | motorcycle | Desgaste del embrague | `engine/wet_clutch` |
| `oil_leaks` | both | Fugas de aceite o retenes | `engine/internal_engine`, `suspension/front_fork` |
| `air_filter_clogged` | motorcycle | Filtro de aire saturado | `filters_fluids` |
| `fuel_pump_failure` | motorcycle | Falla de bomba | `engine/fuel` |
| `engine_overheating` | both | Recalentamiento | `filters_fluids`, `engine/cooling` |

Fuentes cualitativas aportadas previamente por Henry, todavía no verificadas como evidencia de frecuencia para Colombia. El País Motor (y posiblemente Cuidamos tu Moto) describen el mercado español. `engine_overheating` en motos no tiene fuente:

1. Dismerca — https://dismerca.com/blog-fallas-comunes-motos-soluciones/
2. Escuela Nacional de Mecánica de Motocicletas — https://escuelanacionaldemecanicademotocicletas.com/fallas-comunes-en-motocicletas/
3. El País Motor — https://motor.elpais.com/motos/las-10-averias-mas-comunes-en-las-motos/
4. YouTube — https://www.youtube.com/watch?v=08yjTOp2tPA
5. Instagram — https://www.instagram.com/reel/Ddw-t_wvz1l/
6. Cuidamos tu Moto — https://www.cuidamostumoto.com/actualidad/las-averias-mas-tipicas-en-moto
7. Facebook — https://www.facebook.com/groups/127407151223733/posts/1529783004319467/

---

# E. Procedencia y fuentes

## 25. Catalog source

`catalog_source` registra metadatos de una fuente técnica.

Atributos previstos:

- `brand`
- `catalog_name`
- `url`
- `access_type`
- `scraping_allowed`
- `last_checked_at`

Revisar términos y `robots.txt` antes de extraer contenido.

## 26. Provenance mínima

Las entidades provenientes de ingestas deberían poder relacionarse con metadata como:

- `source_system`
- `source_record_id`
- `ingestion_batch_id`
- `ingested_at`
- `raw_object_path`

No todas estas columnas tienen que vivir en cada tabla de negocio; pueden implementarse mediante columnas técnicas, tablas de control o ambas. La implementación exacta se define en las fases de ingesta.

---

# F. Preguntas abiertas

1. ¿Qué unidades adicionales necesita `quantity_unit` para representar kits reales en Colombia?
2. ¿Qué fórmula de reputación comercial debe usarse una vez existan suficientes eventos fuente para evaluarla?
3. ¿Se requiere una entidad normalizada de ubicación con código DANE desde el MVP o puede incorporarse después de inspeccionar las fuentes oficiales?
