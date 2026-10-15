# 08 — Investigación de mercado y fuentes
Última actualización: 2026-10-14 (hora Colombia; Ficha 9 agregada). Fecha de consulta de todas las fuentes: 2026-10-03, salvo indicación (la Ficha 9 indica 2026-10-14). Corrección del 2026-10-12: el corte vigente de `u3vn-bdcy` es OCTUBRE 2026 (Ficha 1). Las citas del corte AGOSTO 2026 de este documento quedan marcadas como superadas; el texto original se conserva.

Convenciones: **Hecho** = dato leído en la fuente primaria. **Dato de prensa** = no se usó prensa en este documento. **Inferencia** = deducción mía, marcada como tal. Las cifras de ANDI-FENALCO son matrículas nuevas (flujo), no parque (stock). Nunca se mezclan.

Método y límite de la sesión: la búsqueda web no estaba habilitada. Todo se leyó con WebFetch contra APIs y páginas oficiales. WebFetch resume el contenido con un modelo pequeño: los valores numéricos de los PDF de ANDI-FENALCO se leyeron por ese canal y deben verificarse abriendo el PDF antes de citarlos en el caso de estudio público. Los datos de las APIs (Socrata, NHTSA) llegaron como JSON; los conteos y filas de ejemplo son copia del JSON devuelto. Verificaciones aritméticas hechas: la suma de la tabla de motos de agosto 2026 da 111.896 (coincide con el total) y las participaciones recalculadas coinciden; la tabla completa de carros 2025 (20 marcas + otras) suma 254.205, igual que el total impreso. Una primera lectura automática del tramo 11–20 no cuadraba (26.182) y se corrigió con una segunda lectura. Los epoch de `rowsUpdatedAt` se convirtieron con Python, porque el resumen automático convirtió mal uno de ellos.

## Resumen

1. No existe en datos.gov.co un dataset nacional de parque automotor con marca. El dataset nacional RUNT `u3vn-bdcy` (191.640 filas en el corte AGOSTO 2026, **superado**; corte vigente OCTUBRE 2026 con 191.922 filas, Ficha 1) trae clase, servicio, estado, departamento y municipio, pero no `marca`. Participación de marca en el parque total: **No encontrado** (objetivo 1a no cumplido).
2. Participación de marca en matrículas nuevas sí está validada con ANDI-FENALCO (datos RUNT). Carros 2025 año completo: Kia 13,4 %, Renault 13,2 %, Toyota 9,3 %, Mazda 8,5 %, Chevrolet 8,3 %. Las 7 marcas de la hipótesis de carros están en el top 10; faltan en la hipótesis Suzuki, Volkswagen y BYD.
3. Motos, agosto 2026 (solo ese mes): Bajaj 16,60 %, AKT 15,13 %, Suzuki 14,99 %, Honda 14,27 %, Yamaha 13,57 %. Faltan en la hipótesis Hero (7,38 %) y, si se cuentan aparte, TVS (8,23 %) y Victory (4,01 %), que son de Auteco.
4. Auteco no incluye Bajaj. Portafolio en auteco.com.co: TVS, Victory, Kymco, Benelli, Kawasaki, Zontes, Ceronte, Eléctricos. ANDI atribuye Bajaj a Grupo UMA.
5. NHTSA vPIC cubre Bajaj (12 modelos), Chevrolet, Kia, Nissan, Toyota, Mazda, Hyundai, Honda, Suzuki, Yamaha, Kymco, Kawasaki y Benelli. No cubre TVS, Zontes ni Ceronte. "Victory" devuelve datos, pero son de la marca estadounidense homónima (Inferencia: no es la de Auteco). AKT no existe: devuelve un falso positivo ("Maktec Manufacturing") porque `GetModelsForMake` busca por subcadena. Renault solo trae 5 modelos históricos.
6. DIVIPOLA existe como dataset Socrata oficial de DANE (`gdxc-w37w`, 1.122 filas, corte 30-dic-2024). `u3vn-bdcy` no trae código DANE: solo nombre de municipio.
7. Recomendación Fase 1: TRM de la Superfinanciera, dataset `32sa-8pi3` (8.360 filas, diaria, sin costo). Segunda fuente candidata: `u3vn-bdcy`.

## Hallazgos

### Objetivo 1 — Participación por marca en Colombia

**1a. Parque activo por marca**

| Afirmación | Fuente (nombre + URL) | Fecha de consulta | Periodo/cobertura | Limitaciones | Impacto en el proyecto |
|---|---|---|---|---|---|
| Hecho: el dataset nacional RUNT `u3vn-bdcy` no tiene columna de marca. Columnas: `nombre_departamento`, `nombre_municipio`, `nombre_servicio`, `estado_del_vehiculo`, `nombre_de_la_clase`, `fecha_de_registro`, `cantidad`, `mes_de_publicacion`, `a_o_de_publicacion`. | datos.gov.co, MinTransporte. https://www.datos.gov.co/api/views/u3vn-bdcy.json | 2026-10-03 | Corte AGOSTO 2026 (**superado** el 2026-10-12: el corte vigente es OCTUBRE 2026, Ficha 1) | Solo clase, no marca | No sirve para participación por marca. Sí sirve para demanda por clase y geografía. |
| Hecho (**superado** el 2026-10-12; el corte vigente es OCTUBRE 2026, ACTIVO 22.613.691, ver Ficha 1): parque `ACTIVO` en agosto 2026 = 22.455.403 vehículos (suma de `cantidad`); 14.391.640 son `MOTOCICLETA`, 4.037.760 `AUTOMOVIL`, 2.139.196 `CAMIONETA`, 774.479 `CAMPERO`. | Consulta SODA a `u3vn-bdcy` (`$select=nombre_de_la_clase,sum(cantidad)&$where=estado_del_vehiculo='ACTIVO'`). https://www.datos.gov.co/resource/u3vn-bdcy.json | 2026-10-03 | Parque total, corte agosto 2026 | Incluye todas las clases, también carga y maquinaria | Dimensiona mercado por clase. Motos son ~64 % del parque activo (Inferencia: 14.391.640 / 22.455.403). |
| Hecho: RUNT publica parque a 31-jul-2026: motos 14.309.240; vehículos 7.782.564; maquinaria, remolques y semirremolques 242.886; total 22.334.690. | RUNT, "RUNT en cifras". https://www.runt.gov.co/runt-en-cifras | 2026-10-03 | Parque total, 31-jul-2026 | La página no muestra marca; el dashboard por marca no se pudo leer | Cifra oficial de contraste. No comparable 1 a 1 con agosto (otro corte). |
| Hecho: el dataset `n4ic-hiug` (Gobernación del Atlántico) tiene `anio`, `marca`, `clase`, `cantidad`; es regional, anual, última actualización 2022-11-03. | https://www.datos.gov.co/api/views/n4ic-hiug.json | 2026-10-03 | Solo Atlántico | Regional, desactualizado, no es el parque nacional | No usar como proxy nacional. Sirve para probar un parser con marca. |
| Hecho: el dataset `bj7e-xc9g` (Alcaldía de Calarcá) trae `marca` por matrícula, pero solo un municipio, ene-2020 a may-2022. | https://www.datos.gov.co/api/views/bj7e-xc9g.json | 2026-10-03 | Calarcá, 2020-2022 | Municipal, cerrado | Descartado como fuente de participación. |
| No encontrado: parque activo por marca a nivel nacional en datos.gov.co o en RUNT. | Catálogo Socrata, consultas "parque automotor", "RUNT", "vehiculos matriculados marca", "matriculas vehiculos nuevos" | 2026-10-03 | n/a | El dashboard del RUNT podría tener marca pero no era legible por WebFetch | La hipótesis de marcas prioritarias no se puede validar sobre parque. Solo sobre matrículas nuevas (ver 1b). |

**1b. Matrículas nuevas**

| Afirmación | Fuente (nombre + URL) | Fecha de consulta | Periodo/cobertura | Limitaciones | Impacto en el proyecto |
|---|---|---|---|---|---|
| Hecho: 2025 cerró con 254.205 vehículos nuevos matriculados, +26,5 % vs 2024. | ANDI-FENALCO, "Informe final sector automotor 2025" (datos RUNT). https://www.andi.com.co/Uploads/12.%20INFORME%20SECTOR%20AUTOMOTOR%20DIC_PRENSA-INDUSTRIA%202025_639034007525631477.pdf | 2026-10-03 | Ene–dic 2025, matrículas nuevas, vehículos (no motos) | Leído vía resumen automático; verificar en PDF | Línea base del último año completo. |
| Hecho: top 10 de marcas 2025 (unidades; participación): Kia 34.063 (13,4 %); Renault 33.658 (13,2 %); Toyota 23.711 (9,3 %); Mazda 21.565 (8,5 %); Chevrolet 21.038 (8,3 %); Suzuki 13.835 (5,4 %); Nissan 13.750 (5,4 %); Hyundai 11.688 (4,6 %); Volkswagen 11.051 (4,3 %); BYD 10.884 (4,3 %). | Mismo informe, tabla "Top 20 marcas Acumulado 2025" | 2026-10-03 | Ene–dic 2025 | Leído dos veces por canales distintos; la segunda lectura reprodujo las 20 filas. Verificación: marcas 1–10 suman 195.243; marcas 11–20 suman 34.173 (Ford 7.268; Foton 6.672; Mercedes Benz 3.352; JAC 2.812; BMW 2.660; Citroën 2.635; JMC 2.496; Subaru 2.105; Chery 2.104; Peugeot 2.069); otras marcas 24.789; total 254.205 (cuadra). Total 2024: 200.953 | Aun así, confirmar contra el PDF antes de publicar. Participaciones recalculadas (unidades/254.205) coinciden. |
| Hecho: 2024 (mismo informe): Toyota 27.008, Renault 25.302, Kia 24.209, Chevrolet 19.560, Mazda 17.960. | Mismo informe | 2026-10-03 | Ene–dic 2024 | Idem | Toyota era #1 en 2024 y bajó 12,2 % en 2025; Kia y Renault lo superaron. El orden no es estable. |
| Hecho: BYD pasó de 4.589 a 10.884 (+137,2 %); Hyundai de 7.196 a 11.688 (+62,4 %). | Mismo informe | 2026-10-03 | 2024 vs 2025 | Idem | BYD es una marca emergente que la hipótesis no incluye. |
| No encontrado: ranking de marcas de carros del año en curso (2026). | Página de Cámara automotriz ANDI (solo informes anuales 2018–2025) y fenalco.com.co (sin informe legible) | 2026-10-03 | n/a | Los informes mensuales de carros 2026 no aparecieron en las páginas leídas | Falta el año en curso para carros. |
| Hecho: motos, agosto 2026 (solo ese mes): total 111.896. Bajaj 18.575 (16,60 %); AKT 16.932 (15,13 %, incluye AKT + AKT Voge + AKT SYM); Suzuki 16.770 (14,99 %); Honda 15.973 (14,27 %); Yamaha 15.186 (13,57 %); TVS 9.205 (8,23 %); Hero 8.262 (7,38 %); Victory 4.491 (4,01 %); Vento 1.650; Bera 807; SYM 779; Fratelli 653; Royal Enfield 630; KTM 510; Kymco 484; Otras 989. | ANDI-FENALCO, "Informe Motocicletas Agosto 2026" (datos RUNT). https://andi.com.co/Uploads/08.%20Informe%20Motocicletas%20ANDI-Fenalco%20-%20Agosto%202026_639238831628738263.pdf | 2026-10-03 | Agosto 2026 únicamente, matrículas nuevas | Es un mes, no el acumulado. SYM aparece separado aunque la nota dice que AKT incluye SYM: ambigüedad sin resolver | Ranking mensual, no anual. No usar como "participación del año". |
| Hecho: motos acumulado ene–ago 2026 = 899.078 matrículas nuevas vs 697.272 en 2025 (+28,94 %). | Mismo informe | 2026-10-03 | Ene–ago 2026 | Total, sin ranking de marcas | Año en curso: volumen, no marcas. |
| Hecho: motos, diciembre 2025 (solo ese mes): total 112.310. Bajaj 18.458 (16,43 %); AKT 17.133 (15,26 %); Suzuki 16.187 (14,41 %); Honda 15.924 (14,18 %); Yamaha 14.849 (13,22 %); Hero 10.138 (9,03 %); TVS 8.323 (7,41 %); Victory 5.649 (5,03 %). | ANDI-FENALCO, "Informe Motocicletas Diciembre 2025". https://andi.com.co/Uploads/12.%20Informe%20Motocicletas%20ANDI-FENALCO%20-%20Diciembre%202025%20-%20V1_639039032554379159.pdf | 2026-10-03 | Diciembre 2025 únicamente | Un mes | Confirma el mismo orden que agosto 2026 con dos puntos de control. |
| Hecho: 2025 cerró con "más de un millón cien mil motocicletas" y +34,94 % acumulado vs 2024. | Mismo informe | 2026-10-03 | Ene–dic 2025 | Sin cifra exacta ni ranking anual por marca en ese PDF | Hay que sumar 12 informes mensuales para el ranking anual. |
| No encontrado: ranking anual 2025 de marcas de motos. | Informes mensuales ANDI-FENALCO (listados 2025 y 2026) | 2026-10-03 | n/a | No se sumaron los 12 PDF | Pendiente si se necesita. |

**Veredicto de la hipótesis** (detalle en la tabla de hipótesis): carros, las 7 marcas están en el top 10 de matrículas nuevas 2025; sobran Suzuki, Volkswagen y BYD fuera de la lista. Motos, las 5 marcas nombradas son el top 5 de ambos meses medidos; falta Hero.

### Objetivo 2 — Portafolio de Auteco

| Afirmación | Fuente (nombre + URL) | Fecha de consulta | Periodo/cobertura | Limitaciones | Impacto en el proyecto |
|---|---|---|---|---|---|
| Hecho: el menú de auteco.com.co lista TVS, Victory, Kymco, Benelli, Kawasaki, Zontes, Ceronte y "Eléctricos". Bajaj no aparece. | Auteco, sitio oficial. https://www.auteco.com.co | 2026-10-03 | Sitio a 2026-10-03 | Se leyó la portada; no las páginas de cada marca. `https://www.auteco.com.co/marca/bajaj` devolvió 404 | Auteco no incluye Bajaj. Las "marcas de Auteco" de la hipótesis son TVS, Victory, Kymco, Benelli, Kawasaki, Zontes y Ceronte. |
| Hecho: ANDI separa dos afiliados: Auteco SAS (TVS; plantas en Cartagena e Itagüí) y Auteco Mobility SAS (Kymco, Victory, Kawasaki, Benelli). | ANDI, Cámara de la Industria de Motocicletas, "AfiliadosProductos". https://andi.com.co/Uploads/AfiliadosProductos%20-%20C%C3%A1mara%20de%20la%20Ind.%20de%20Motocicletas%20-%20ANDI%20(1).pdf | 2026-10-03 | Directorio vigente de afiliados (sin fecha en el PDF) | Zontes y Ceronte no figuran en ese directorio | Dos razones sociales en el dominio "Auteco". Relevante para `dim_brand` / `dim_distributor`. |
| Hecho: ANDI atribuye Bajaj ("Boxer, Discover, Pulsar y Dominar") a Grupo UMA, con dos plantas de ensamble. | Mismo PDF | 2026-10-03 | Idem | Afirmación de la cámara gremial, no del fabricante | Bajaj tiene distribuidor/ensamblador distinto de Auteco. |
| Hecho: en el dataset municipal de Calarcá (2020–2022) aparecen valores de marca `AUTECO BAJAJ` (260) y `AUTECO KAWASAKI` en `marca`. | `bj7e-xc9g`. Consulta SODA de marcas | 2026-10-03 | Calarcá, 2020–2022 | Dato local histórico | Inferencia: Auteco sí distribuyó Bajaj en el pasado; el portafolio actual ya no lo muestra. Y el campo `marca` mezcla distribuidor y marca: requiere normalización. |

### Objetivo 3 — Marcas que fabrican o ensamblan en Colombia

| Afirmación | Fuente (nombre + URL) | Fecha de consulta | Periodo/cobertura | Limitaciones | Impacto en el proyecto |
|---|---|---|---|---|---|
| Hecho (motos): AKT (Corbeta S.A.), Honda (Fanalca-Honda, planta en Acopí Yumbo), Hero (planta en Cauca), Yamaha (Incolmotos Yamaha, sede Girardota), Suzuki ("única planta ensambladora de la región"), TVS (Auteco SAS, plantas en Cartagena e Itagüí), Bajaj (Grupo UMA, dos plantas en el Eje Cafetero) están en el directorio de afiliados de ANDI. | ANDI, "AfiliadosProductos" (URL arriba) | 2026-10-03 | Directorio sin fecha | Es una lista de afiliados con descripción de plantas, no un censo oficial de producción; no distingue ensamble completo de CKD | Las 7 marcas de motos principales ensamblan localmente. Útil para el atributo `is_assembled_in_colombia`. |
| Hecho: la cámara automotriz de ANDI declara que en 2024 la industria automotriz aportó 559 millones de dólares en valor de producción nacional y ejecutó 102 millones de dólares en proyectos de ensamble. | ANDI, Cámara Automotriz. https://www.andi.com.co/Home/Camara/4-automotriz | 2026-10-03 | 2024 | No nombra marcas | Confirma producción local de carros, sin marcas. |
| Hecho: el sitio de Renault Colombia dice que "RENAULT-Sofasa ha fabricado más de 1 millón de vehículos Renault". | Renault Colombia. https://www.renault.com.co/renault-en-colombia.html | 2026-10-03 | Acumulado histórico | No indica planta, modelos actuales ni fecha | Evidencia parcial de fabricación local. No confirma qué modelos hoy. |
| No encontrado: confirmación oficial de ensamble actual de Chevrolet (GM Colmotores), Renault (modelos vigentes en la planta de Envigado) y otras marcas de carros. | chevrolet.com.co (sin mención), gmcolmotores.com.co (bloqueado por robots.txt), sofasa.com.co (bloqueado), ANDI sección "Ensambladores" (índice sin contenido) | 2026-10-03 | n/a | No se pudo leer | Pendiente. No marcar `is_assembled_in_colombia` para carros hasta tener fuente. |

### Objetivo 4 — Datasets de datos.gov.co

| Afirmación | Fuente (nombre + URL) | Fecha de consulta | Periodo/cobertura | Limitaciones | Impacto en el proyecto |
|---|---|---|---|---|---|
| Hecho: parque nacional RUNT = `u3vn-bdcy`; contiene un único corte (AGOSTO 2026; **superado** el 2026-10-12, hoy OCTUBRE 2026, Ficha 1): 182.978 filas `ACTIVO` y 8.662 `INCONSISTENTE` (suma 191.640); no hay otros meses. | Consulta SODA agrupada por año/mes/estado | 2026-10-03 | Agosto 2026 | El nombre dice "Crecimiento", pero no hay serie mensual | Si la fuente se sobrescribe cada mes, el historial solo existe si Fase 1 guarda cada snapshot en raw. |
| Hecho: TRM oficial = `32sa-8pi3` (Superfinanciera): 8.360 filas, desde 1991-12-02 hasta 2026-10-03. Existen al menos 9 datasets TRM más en el catálogo (`mcec-87by`, `ceyp-9c7c`, `djvb-n8kv`, `dit9-nnvp`, otros). | Consulta SODA `count(*),min,max` | 2026-10-03 | 1991-12-02 a 2026-10-03 | Duplicados con distinto esquema | Fijar un solo ID y documentar por qué. |
| Hecho: DIVIPOLA municipios = `gdxc-w37w`, 1.122 filas; departamentos = `vcjz-niiq`. | Consulta SODA | 2026-10-03 | Corte 30-dic-2024 | Lat/long usan coma decimal y son `text` | Requiere parseo y cast en staging. |
| Hecho: trámites RUNT = `akpq-tuqi`, mensual, columnas con tildes inconsistentes (`TRAMITE CAMBIO PLACA` vs `TRÁMITE CAMBIO PLACA`, mismo `cod_tramite`). | Consulta SODA | 2026-10-03 | Desde al menos 1/10/2024 | Conteo de filas agotó el tiempo de espera; no se verificó que exista código de "matrícula inicial" de vehículos (solo `MATRICULA_INICIAL_REMOLQUE_SEMIREMOLQUE`, cód. 80, en los primeros 100 grupos) | Normalizar por `cod_tramite`, no por descripción. |

Fichas completas en la sección siguiente.

### Objetivo 5 — NHTSA vPIC

| Afirmación | Fuente (nombre + URL) | Fecha de consulta | Periodo/cobertura | Limitaciones | Impacto en el proyecto |
|---|---|---|---|---|---|
| Hecho: `GetAllMakes`, `GetModelsForMake`, `GetModelsForMakeId` y `GetVehicleTypesForMake` existen; `GetModelsForMake` con `*` y `GetModelsForMakeId` con `0` devuelven todos los modelos y "can be slow". La documentación habla de un control automático de tráfico sin dar cifras. Solo `GetAllManufacturers`/`GetManufacturerDetails` paginan (`page`, 100 por página). | NHTSA vPIC. https://vpic.nhtsa.dot.gov/api/ | 2026-10-03 | Doc vigente | No hay límite numérico publicado | Meter retry con backoff y caché en raw. |
| Hecho: `GetModelsForMake/{make}` hace coincidencia por subcadena: `akt` devolvió `Maktec Manufacturing`; `kia` incluyó `MGS Grand Sport (Mardikian)` y `TEKIAR`; `hyundai` incluyó `Hyundai Translead Trailers`; `victory` incluyó 7 marcas. | Pruebas abajo | 2026-10-03 | Prueba puntual | Observado en 4 marcas | Filtrar por `Make_ID` exacto, nunca por texto. |

Cobertura por marca (prueba `https://vpic.nhtsa.dot.gov/api/vehicles/GetModelsForMake/<marca>?format=json`, 2026-10-03):

| Marca | `Count` | Cobertura | Observación |
|---|---|---|---|
| bajaj | 12 | Sí (`Make_ID` 4007, "Bajaj Auto") | Legend, Chetak, Classic, Saffire, Caliber, Boxer, Acer, Eliminator, Spirit, Spice, M80 Major, Pulsar. No aparecen CT100 (modelo líder en el informe de dic-2025), Dominar ni Discover (ANDI/UMA los menciona). Inferencia: el catálogo es histórico y orientado a EE. UU. |
| akt | 1 | No | Falso positivo: "Maktec Manufacturing" |
| renault | 5 | Parcial (`Make_ID` 13647) | LeCar, 18i, Fuego, Alliance, Encore. Ninguno de la gama colombiana actual. Inferencia: son modelos históricos de EE. UU. |
| chevrolet | 124 | Sí (467) | |
| hyundai | 40 | Sí (498) | Incluye otras empresas "Hyundai …" |
| kia | 27 | Sí (499) | Incluye falsos positivos |
| nissan | 44 | Sí (478) | |
| toyota | 58 | Sí (448) | |
| mazda | 28 | Sí (473) | |
| suzuki | 399 | Sí (509) | |
| yamaha | 271 | Sí (564) | |
| honda | 362 | Sí (474) | Incluye "Sundiro Honda Motorcycle Co. Ltd" |
| tvs | 0 | No | |
| victory | 41 | Falso positivo probable (567) | Los modelos devueltos (Cross Roads, Cross Country, Vegas, Gunner, Judge) son de Victory Motorcycles (EE. UU.). Inferencia: es otra marca con el mismo nombre que la Victory de Auteco Mobility. También mezcla remolques y barredoras |
| kymco | 42 | Sí | |
| benelli | 16 | Sí (4785; y 3926 "BENELLI Q.J. SRL") | Dos IDs de marca |
| kawasaki | 223 | Sí (510) | |
| zontes | 0 | No | |
| ceronte | 0 | No | |

Impacto: vPIC sirve como catálogo de marcas global y de modelos de EE. UU., no del mercado colombiano. Inferencia: sin cobertura de TVS, Zontes, Ceronte, AKT y con solo modelos históricos de Renault, no sirve como fuente de verdad de modelos para Colombia. Los conteos no se compararon con la lista de modelos del mercado colombiano.

### Objetivo 6 — DANE DIVIPOLA

| Afirmación | Fuente (nombre + URL) | Fecha de consulta | Periodo/cobertura | Limitaciones | Impacto en el proyecto |
|---|---|---|---|---|---|
| Hecho: DANE publica DIVIPOLA como dataset Socrata `gdxc-w37w` ("DIVIPOLA- Códigos municipios"), formato JSON/CSV vía SODA. Columnas: `cod_dpto`, `dpto`, `cod_mpio`, `nom_mpio`, `tipo_municipio`, `longitud`, `latitud`. 1.122 filas. | datos.gov.co, DANE. https://www.datos.gov.co/resource/gdxc-w37w.json | 2026-10-03 | Corte 30-dic-2024; `rowsUpdatedAt` 2025-01-24; frecuencia declarada: semestral | `longitud` y `latitud` son `text` con coma decimal ("-75,581775") | Fuente oficial por API. Confirma que existe un listado oficial con código. La decisión de usar el código DANE desde el MVP (pregunta abierta 2 de `06_status.md`) sigue pendiente y es de Henry. |
| Hecho: departamentos en `vcjz-niiq`: `codigo_departamento`, `nombre_departamento`, `longitud`, `latitud`. | https://www.datos.gov.co/resource/vcjz-niiq.json | 2026-10-03 | Corte 30-dic-2024 | No se contó el número de filas | Tabla de departamentos. |
| Hecho: existen también centros poblados (`xaxy-8nri`) y réplicas de MinSalud y MinTIC. | Catálogo Socrata, búsqueda "DIVIPOLA" | 2026-10-03 | Varios | Usar solo la de DANE | Elegir la de DANE como autoridad. |
| No encontrado: página del geoportal de DANE (geoportal.dane.gov.co) legible: bloqueada por robots.txt. | WebFetch | 2026-10-03 | n/a | | No se verificó descarga directa XLSX del sitio DANE. |
| Hecho: `u3vn-bdcy` y `akpq-tuqi` traen nombre de municipio en texto (`nombre_municipio`), sin `cod_mpio`; `akpq-tuqi` trae `codigo_departamento` numérico (ej. 5, 11) sin cero a la izquierda. | Muestra SODA | 2026-10-03 | | Cruce por nombre propenso a error (tildes, "BOGOTA" vs "BOGOTÁ, D.C.") | Inferencia: Fase 3 necesita una tabla de equivalencias de nombres; el código DANE no viene en el origen. |

### Objetivo 7 — Fuente de Fase 1

Ver "Recomendación para la Fase 1".

## Fichas de datasets y APIs

Todas las URLs de datos.gov.co: base `https://www.datos.gov.co`. Autenticación: ninguna para leer; token de aplicación opcional. Límites: sin token, el tráfico se limita por IP desde un pool compartido; con token se asigna cuota individual (cabecera `X-App-Token`; alternativa `$$app_token`) (https://dev.socrata.com/docs/app-tokens). Paginación: `$limit` (por defecto 1.000) y `$offset`; las APIs 2.0 limitan a 50.000 por petición; siempre se debe usar `$order` (https://dev.socrata.com/docs/paging). `$limit` máximo y cuota exacta sin token: **No encontrado** en la documentación leída.

### Ficha 1 — CRECIMIENTO DEL PARQUE AUTOMOTOR RUNT2.0 (`u3vn-bdcy`)

- URL: https://www.datos.gov.co/Transporte/CRECIMIENTO-DEL-PARQUE-AUTOMOTOR-RUNT2-0/u3vn-bdcy
- Endpoint: `https://www.datos.gov.co/resource/u3vn-bdcy.json`
- Atribución: Ministerio de Transporte. Licencia: CC BY-SA 4.0.
- Frecuencia: "Mensual". Última actualización: 2026-09-04 16:34 UTC (`rowsUpdatedAt` 1788539652).
- Filas: 191.640 por la metadata; `count(*)` de la consulta devolvió 191.293 (diferencia de 347 sin explicar; posible diferencia de momento de consulta).
- Columnas (`fieldName`, tipo declarado): `nombre_departamento` text; `nombre_municipio` text; `nombre_servicio` text; `estado_del_vehiculo` text (`ACTIVO`, `INCONSISTENTE`); `nombre_de_la_clase` text; `fecha_de_registro` number (año; `1900` aparece como valor centinela); `cantidad` number; `mes_de_publicacion` text; `a_o_de_publicacion` number. Observación: el JSON devuelve todo como string.
- Filas de ejemplo (JSON devuelto):
  1. ANTIOQUIA, ANDES, PARTICULAR, ACTIVO, CAMPERO, 1900, 1, AGOSTO, 2026 (**superado**: muestra del corte AGOSTO 2026)
  2. ATLANTICO, BARANOA, PARTICULAR, ACTIVO, AUTOMOVIL, 1900, 1, AGOSTO, 2026 (**superado**: muestra del corte AGOSTO 2026)
  3. ATLANTICO, BARANOA, PÚBLICO, ACTIVO, CAMION, 1900, 1, AGOSTO, 2026 (**superado**: muestra del corte AGOSTO 2026)
- Dato adicional: motos `ACTIVO` por año de registro: 2026 916.454; 2025 1.098.485; 2024 812.133; 2023 675.371; 2022 799.278. Es parque activo hoy por año de matrícula, no matrículas nuevas de cada año.

- **Corrección del 2026-10-12 (corte vigente; reemplaza la cita de AGOSTO 2026 de esta ficha).** El corte vigente de `u3vn-bdcy` es OCTUBRE 2026: publicado el 2026-10-05 (`rowsUpdatedAt` 1791220968, es decir, 2026-10-05 17:22:48 UTC, convertido con Python), con 191.922 filas y 22.655.040 vehículos (suma de `cantidad`). Fuente: API SODA de datos.gov.co, `u3vn-bdcy`, consultada el 2026-10-12 (reportada por el orquestador en la sesión del hito Fase 1b; cifras de la consulta, no de un documento). Las cifras de "Filas" de esta ficha (191.640; 191.293 en `count(*)`) y el corte AGOSTO 2026 corresponden al corte anterior y quedan superados. ACTIVO de OCTUBRE 2026 = 22.613.691 (landing, consultado por el revisor el 2026-10-13). El ACTIVO de agosto 2026 (22.455.403) queda superado. Inferencia: la fuente conserva solo el corte vigente, como ya se había observado (`03_data_model.md`, §27).

### Ficha 2 — TRM, Superfinanciera (`32sa-8pi3`)

- URL: https://www.datos.gov.co/Econom%C3%ADa-y-Finanzas/Tasa-de-Cambio-Representativa-del-Mercado-TRM/32sa-8pi3
- Endpoint: `https://www.datos.gov.co/resource/32sa-8pi3.json`
- Atribución: Superintendencia Financiera de Colombia. Licencia: CC BY-SA 4.0. Frecuencia: "Diaria". Última actualización: 2026-10-02 23:05 UTC (`rowsUpdatedAt` 1790982325).
- Filas: 8.360. Rango `vigenciadesde`: 1991-12-02 a 2026-10-03.
- Columnas: `valor` number; `unidad` text; `vigenciadesde` calendar_date; `vigenciahasta` calendar_date.
- Filas de ejemplo (orden `vigenciadesde DESC`):
  1. valor 3273.49, COP, desde 2026-10-03, hasta 2026-10-05 (fin de semana: una sola fila cubre varios días)
  2. valor 3307.73, COP, desde 2026-10-02, hasta 2026-10-02
  3. valor 3312.84, COP, desde 2026-10-01, hasta 2026-10-01
- Alternativa: `mcec-87by` (histórico; mismas 4 columnas; actualizado 2026-09-21 por `rowsUpdatedAt`). Otros IDs TRM (`ceyp-9c7c`, `djvb-n8kv`, `c47q-nfq8`, `dit9-nnvp`, etc.) no se inspeccionaron a fondo.

### Ficha 3 — Trámites radicados RUNT 2.0 (`akpq-tuqi`)

- URL: https://www.datos.gov.co/Transporte/TRAMITES-RADICADOS-POR-ACTORES-DEL-SISTEMA-RUNT-2-/akpq-tuqi
- Endpoint: `https://www.datos.gov.co/resource/akpq-tuqi.json`
- Atribución: MinTransporte. Frecuencia: "Mensual". Última actualización: 2026-09-04 21:15 UTC (`rowsUpdatedAt` 1788556520).
- Filas: **No encontrado** (el `count(*)` agotó el tiempo de espera).
- Columnas: `fecha` text (formato `d/m/aaaa`); `tipo_actor` text; `nombre_municipio` text; `codigo_departamento` number; `nombre_departamento` text; `estado_tramite` text; `registro` text; `cod_tramite` number; `descripcion_del_tramite_radicado` text; `cantidad` number.
- Filas de ejemplo:
  1. 1/10/2024, ASEGURADORA, BOGOTA, 11, BOGOTA D.C., APROBADO, RNS, 8001, SOAT, 16875
  2. 1/10/2024, ASEGURADORA, BOGOTA, 11, BOGOTA D.C., APROBADO, RNS, 8002, RCC, 1157
  3. 1/10/2024, ASEGURADORA, MEDELLIN, 5, ANTIOQUIA, APROBADO, RNS, 8001, SOAT, 19304
- Calidad: la misma `cod_tramite` aparece con descripciones con y sin tilde.

### Ficha 4 — DIVIPOLA- Códigos municipios (`gdxc-w37w`) y departamentos (`vcjz-niiq`)

- URL: https://www.datos.gov.co/resource/gdxc-w37w.json y https://www.datos.gov.co/resource/vcjz-niiq.json
- Atribución: DANE. Última actualización de `gdxc-w37w`: 2025-01-24 20:44 UTC (`rowsUpdatedAt` 1737751472); el catálogo muestra otra fecha (2026-09-24), sin explicación. Frecuencia: "Semestral". Corte: 30-dic-2024.
- Filas: `gdxc-w37w` 1.122. `vcjz-niiq` no contado.
- Columnas `gdxc-w37w` (todas text): `cod_dpto`, `dpto`, `cod_mpio`, `nom_mpio`, `tipo_municipio`, `longitud`, `latitud`.
- Columnas `vcjz-niiq` (muestra): `codigo_departamento`, `nombre_departamento`, `longitud`, `latitud`.
- Filas de ejemplo `gdxc-w37w`: (05, ANTIOQUIA, 05001, MEDELLÍN, Municipio, -75,581775, 6,246631); (05, ANTIOQUIA, 05002, ABEJORRAL, Municipio, -75,428739, 5,789315); (05, ANTIOQUIA, 05004, ABRIAQUÍ, Municipio, -76,064304, 6,632282).
- Filas de ejemplo `vcjz-niiq`: (05, ANTIOQUIA, -75,504557037, 6,702032125); (08, ATLÁNTICO, -74,965219492, 10,677009534); (11, BOGOTÁ, D.C., -74,181072702, 4,316107698).

### Ficha 5 — Datasets con marca (regionales/auxiliares)

- `n4ic-hiug` (Gobernación del Atlántico): https://www.datos.gov.co/resource/n4ic-hiug.json. Columnas: `anio` number, `marca` text, `clase` text, `cantidad` number. Anual. Última actualización 2022-11-03. Filas: no contadas. Ejemplo: (2018, CHEVROLET, AMBULANCIA, 4); (2018, DODGE, AMBULANCIA, 1); (2018, FORD, AMBULANCIA, 2).
- `bj7e-xc9g` (Alcaldía de Calarcá): https://www.datos.gov.co/resource/bj7e-xc9g.json. Columnas text: `orden`, `clase`, `marca`, `modelo`, `fecha_matricula_radicacion`, `a_o`, `mes`, `dia`. Semestral, última actualización 2022-06-15. Ejemplo: (1, MOTOCICLETA, YAMAHA, 2000, 02/02/2000, 2000, 02.febrero, 02.miércoles); (2, MOTOCICLETA, SUZUKI, 2000, 23/02/2000, 2000, 02.febrero, 23.miércoles); (3, MOTOCICLETA, AUTECO KAWASAKI, 2000, 25/09/2000, 2000, 09.septiembre, 25.lunes). Top de `marca` (conteo de filas): CHEVROLET 2.584; YAMAHA 2.084; SUZUKI 1.804; BAJAJ 1.338; HONDA 1.145; MAZDA 1.119; RENAULT 1.072; AKT 827; AUTECO BAJAJ 260.
- `6jmc-vaxk` (vehículos involucrados en accidentes, Ley 2251-2022, MinTransporte): columnas `marca_vehiculo` text, `modelo_vehiculo` number, `tipo_vehiculo` text, `edad_vehiculo` number, `fecha_accidente` text (`mm/aaaa`), `gravedad_accidente`, `departamento_accidente`, `municipio_accidente`, `autoridad_de_transito`. 450.335 filas. Frecuencia "Semestral". `rowsUpdatedAt` = 2026-02-03 pero la muestra trae registros de 09/2026 y el catálogo dice 2026-09-04: la fecha no es consistente. Es siniestralidad, no parque ni matrículas: no sirve para participación de marca. Ejemplo: (VOLKSWAGEN, 2018, CAMION, 7, 09/2026, CON HERIDOS, ANTIOQUIA, MEDELLIN, DIRECCION DE TRANSITO Y TRANSPORTE).
- Otros datasets de parque listados en el catálogo (solo columnas del catálogo, esquema real no inspeccionado). Son municipales o departamentales, no sirven para participación nacional: `dkxf-ikd7` Caldas (con `MARCA`; actualizado 2026-09-19); `em3d-hmim` Boyacá particular (con `MARCA`, `COD DANE`; vigencia 2024); `x9pp-pcn5` Risaralda (con `MARCA`); `aj2e-7jwg` Fusagasugá (con `Marca`; RUNT al 30-ene-2026); `g4h5-prph` Barranquilla acumulado mensual (sin marca: `CLASE_VEHICULOS`, `COMBUSTIBLE_VEHICULOS`, `SERVICIO_VEHICULOS`, `CANTIDAD_VEHICULOS`); `fvnt-frpb` parque público activo/inactivo (con `MARCA`). Fecha de actualización tomada del catálogo.
- `ntxy-q9ix` (eléctricos e híbridos RUNT 2.0): solo se leyeron las columnas del catálogo (`CLASE`, `MODELO`, `CANTIDAD`, `COMBUSTIBLE`, `DEPARTAMENTO`, `CARROCERIA`, `MUNICIPIO`, `AÑO_REGISTRO`). Sin marca. No se inspeccionó el esquema real ni filas.

### Ficha 6 — NHTSA vPIC API

- URL base: https://vpic.nhtsa.dot.gov/api/
- Endpoints: `GET https://vpic.nhtsa.dot.gov/api/vehicles/GetModelsForMake/{make}?format=json`; `GetModelsForMakeId/{id}`; `GetAllMakes`; `GetVehicleTypesForMake`.
- Autenticación: ninguna. Límites: control automático de tráfico, sin cifras publicadas.
- Paginación: ninguna en estos endpoints; `page` solo en `GetAllManufacturers` y `GetManufacturerDetails` (100 por página).
- Columnas devueltas por `GetModelsForMake`: `Make_ID` number, `Make_Name` string, `Model_ID` number, `Model_Name` string. Envoltorio: `Count`, `Message`, `SearchCriteria`, `Results`. No se verificaron los tipos más allá del JSON.
- Filas de ejemplo (`bajaj`): (4007, Bajaj Auto, 8663, Legend); (4007, Bajaj Auto, 8664, Chetak); (4007, Bajaj Auto, 8665, Classic).
- Actualización: No encontrado en la documentación.

### Ficha 7 — ANDI-FENALCO informes mensuales (PDF)

- Motos: https://www.andi.com.co/Home/Camara/1047-camara-de-la-industria-de-motocicletas (informes ene-2025 a ago-2026). Carros: https://www.andi.com.co/Home/Camara/4-automotriz (informes anuales 2018–2025).
- Autenticación: ninguna. Formato: PDF, sin API. Frecuencia: mensual (motos), anual (carros). Fuente de datos declarada: RUNT, elaboración ANDI-FENALCO.
- Columnas: no aplica (tablas en PDF). Riesgo: extraer tablas de PDF es frágil.

### Ficha 8 — RUNT en cifras

- URL: https://www.runt.gov.co/runt-en-cifras (enlaces a `matriculas-iniciales`, `parque-automotor`, `balance-del-sector-transito-y-transporte`). Dashboards sin API documentada que yo haya visto. No se pudo leer el contenido por marca.

### Ficha 9 — Parque departamental con marca: Boyacá `em3d-hmim` y Risaralda `x9pp-pcn5` (verificado por API, 2026-10-14)

Fecha de consulta: 2026-10-14. Verificado por API (SODA, `count(*)`, metadata y consultas `$group`) por el orquestador. Estas fichas son la fuente de los insumos regionales de D135–D140 (hito A de marca). Son datos regionales de dos departamentos: no son dato nacional (`research/parque_por_marca.md`, sección 7).

- Boyacá `em3d-hmim`: https://www.datos.gov.co/resource/em3d-hmim.json. Filas: 182.379 (`count(*)`). `rowsUpdatedAt` = 1725049480 = 2024-08-30. Columnas: 18 (metadata confirmada). Nombres según la consulta del arquitecto (2026-10-14): n, motivo_ingreso, cod_dane, dane_mun, provincia, municipio, clase, marca, linea, modelo, carroceria, pasajeros, tonelaje, cilindraje, servicio, estado, blindaje, importado. Valores de `servicio` (`$group`): PARTICULAR, OFICIAL, MIXTO, OTRO, PUBLICO (sin tilde), NA y DIPLOMATICO. `estado`: ACTIVO en las 182.379 filas. Requeridos `clase`, `marca`, `linea`, `servicio` y `estado`: 0 filas nulas o vacías. Calibración de D135–D140: servicio PARTICULAR y estado ACTIVO (D52, D59).
- Risaralda `x9pp-pcn5`: https://www.datos.gov.co/resource/x9pp-pcn5.json. Filas: 453.925 (`count(*)`). `rowsUpdatedAt` = 1783366796 = 2026-07-06. Columnas: 6 (metadata confirmada): clase, placa, marca, modelo, linea, cilindraje. La columna `placa` existe en la fuente; el extractor no la pide (D136). No tiene `servicio` ni `estado` (D55). Requeridos `clase`, `marca` y `linea`: 0 filas nulas o vacías. Clases (`$group`, 18): MOTOCICLETA 251.757; AUTOMOVIL 110.290; CAMIONETA 51.145; CAMPERO 23.393; CAMION 6.431; MOTOCARRO 3.433; VOLQUETA 1.735; MICROBUS 1.629; BUS 1.296; TRACTOCAMION 1.129; BUSETA 954; CUATRIMOTO 360; CICLOMOTOR 329; MOTOTRICICLO 24; CUADRICICLO 13; SIN CLASE 3; AUTOMOVIL ELECTRICO 3; MOTOCICLETA ELECTRICA 1.
- Licencia: la migración 0006 declara CC BY-SA 4.0 para ambos datasets; la licencia no está verificada en la evidencia de este paso (no verificado). Verificado después (revisión final de M1, 2026-10-14; lectura de archivos): `research/parque_por_marca.md:95-96` registra CC BY-SA 4.0 para Risaralda `x9pp-pcn5` y Boyacá `em3d-hmim` (consulta del 2026-10-10), y el manifest la escribe fija (`src/pits/sources/brand_fleet/contract.py:38`, `LICENSE = "CC_40_BY_SA"`).
- Límite de fecha: Boyacá (2024-08-30) y Risaralda (2026-07-06) no son del mismo corte. Ninguno es el corte vigente del RUNT (`u3vn-bdcy`, Ficha 1).

## Hipótesis validadas y refutadas

| Hipótesis | Resultado (validada / refutada / sin evidencia) | Fuente |
|---|---|---|
| Carros: Chevrolet, Renault, Hyundai, Kia, Nissan, Toyota y Mazda son las marcas principales (por matrículas nuevas 2025) | Validada: las 7 están en el top 10. Faltan en la hipótesis: Suzuki (#6), Volkswagen (#9) y BYD (#10) | ANDI-FENALCO, informe final 2025 (URL en Obj. 1b) |
| Carros: esas marcas también dominan el parque activo | Sin evidencia: no hay parque por marca | Ver Obj. 1a |
| Motos: Bajaj, Suzuki, Yamaha, Honda y AKT son las principales | Validada con dos meses (dic-2025 y ago-2026), no con el año completo. Falta Hero (#6–7) | ANDI-FENALCO motos dic-2025 y ago-2026 |
| Motos: las marcas de Auteco están entre las principales | Validada en parte: TVS (8,23 %) y Victory (4,01 %) están en el top 8; Kymco 0,43 %; Benelli, Kawasaki, Zontes y Ceronte no aparecen en la tabla (Inferencia: están en "Otras") | ANDI-FENALCO motos ago-2026; auteco.com.co |
| Bajaj forma parte del portafolio de Auteco | Refutada: no aparece en el sitio y ANDI lo asigna a Grupo UMA | auteco.com.co; ANDI "AfiliadosProductos" |
| AKT, Renault y marcas de Auteco están en NHTSA vPIC | Refutada para AKT (falso positivo), TVS, Zontes y Ceronte; parcial para Renault (5 modelos históricos). Validada para Bajaj y Chevrolet, Hyundai, Kia, Nissan, Toyota, Mazda, Suzuki, Yamaha, Honda, Kymco, Kawasaki, Benelli. Victory: coincide el nombre, pero Inferencia de homonimia con la marca de EE. UU. | NHTSA vPIC (pruebas en Obj. 5) |
| Existe un listado oficial de departamentos/municipios con código DANE por API | Validada | datos.gov.co `gdxc-w37w`, `vcjz-niiq` |
| datos.gov.co publica parque automotor nacional con marca | Refutada | Catálogo Socrata; `u3vn-bdcy` sin `marca` |
| Las marcas principales de motos ensamblan en Colombia | Validada para AKT, Honda, Hero, Yamaha, Suzuki, TVS, Bajaj (directorio ANDI). Sin evidencia para carros | ANDI "AfiliadosProductos" |

## Recomendación para la Fase 1

**Fuente elegida: TRM de la Superfinanciera en datos.gov.co, dataset `32sa-8pi3`.**

Por qué, contra los criterios:

1. Sin costo y sin autenticación obligatoria; token opcional con `X-App-Token`.
2. API estable: Socrata SODA, mismo esquema de 4 columnas, publicador oficial (Superfinanciera), actualización diaria (`rowsUpdatedAt` 2026-10-02).
3. Sin scraping: JSON por HTTP.
4. Paginación documentada: `$limit`, `$offset`, `$order`.
5. Volumen manejable: 8.360 filas en total. Cabría en una sola petición si el tope es 50.000 (límite documentado para Socrata API 2.0; no verifiqué qué versión sirve datos.gov.co), pero conviene paginar para demostrar el patrón.
6. Periodicidad natural: llave `vigenciadesde`, carga incremental diaria y backfill del historial desde 1991.

Contra las alternativas:

- `u3vn-bdcy` (parque RUNT): relevante al dominio, pero 191k filas, sin historial (solo el corte de agosto 2026, **superado** el 2026-10-12: hoy OCTUBRE 2026, Ficha 1), sin marca y sin código DANE. Es mejor como segunda fuente (Fase 1b) cuando el patrón de snapshots mensuales ya funcione.
- DIVIPOLA `gdxc-w37w`: dato estable pero casi estático (corte 2024, semestral): no ejercita incrementalidad. Es una dimensión de apoyo, no una fuente de ingesta.
- NHTSA vPIC: cobertura de Colombia pobre y límites no publicados.
- ANDI-FENALCO: PDF, requiere parsear tablas; frágil y fuera del criterio "sin scraping".
- `akpq-tuqi`: conteo agotó el tiempo de espera y la descripción del trámite no es estable.

Riesgos y mitigaciones:

- Hay al menos 9 datasets TRM duplicados con esquemas distintos. Fijar `32sa-8pi3` y verificar atribución en el manifest.
- Fines de semana y festivos: una fila cubre varios días (`vigenciadesde` 2026-10-03, `vigenciahasta` 2026-10-05). El modelo debe usar rango de vigencia, no fecha única.
- Todo llega como string en el JSON: validar y castear en el parser.
- Paginar con `$order=vigenciadesde` (o `:id`), no sin orden.
- La relevancia al marketplace es indirecta (Inferencia: la TRM sirve para convertir precios de repuestos importados en dólares). Presentarlo así en el caso de estudio.
- Rate limit sin token: **No encontrado** el número exacto. Registrar un token y manejar reintentos con backoff.

## No encontrado

| Lo que falta | Qué se buscó |
|---|---|
| Parque activo por marca a nivel nacional | Catálogo Socrata con "parque automotor", "RUNT", "vehiculos matriculados marca", "registro inicial vehiculos marca motocicletas"; página RUNT en cifras (sin marca). |
| Matrículas nuevas de carros del año en curso (2026) por marca | ANDI Cámara Automotriz (solo anuales hasta 2025); fenalco.com.co (no se encontró el informe). |
| Ranking anual 2025 de motos por marca | Informe de diciembre 2025 (solo diciembre); no se sumaron los 12 informes mensuales. |
| Ensamble actual de Chevrolet, Renault y otras marcas de carros, con fuente oficial | chevrolet.com.co; renault.com.co (solo "ha fabricado más de 1 millón de vehículos"); gmcolmotores.com.co y sofasa.com.co (bloqueados por robots.txt); ANDI sección "Ensambladores" (sin contenido legible). |
| Páginas individuales de marca en Auteco; presencia actual de Zontes y Ceronte en un directorio oficial | `auteco.com.co/marca/bajaj` (404); `auteco.com.co/nosotros` (sin datos de manufactura). |
| Descarga XLSX o API alternativa de DANE | geoportal.dane.gov.co (bloqueado por robots.txt). |
| Número de filas de `akpq-tuqi` y `vcjz-niiq`; existencia del código de matrícula inicial de vehículos en `akpq-tuqi` | Consultas `count(*)` (timeout) y `group by` truncado a 100 grupos. |
| Esquema real de `ntxy-q9ix` | Solo columnas del catálogo. |
| Límite numérico de peticiones sin token en Socrata y de NHTSA vPIC | Documentación de Socrata (app tokens, paging) y de vPIC. |
| Verificación visual de las tablas de ANDI contra el PDF | Los valores se leyeron por WebFetch (resumen automático). Las sumas cuadran, pero nadie abrió el PDF original. |
| Motivo de la diferencia entre `count(*)` 191.293 y filas 191.640 en `u3vn-bdcy`; de la fecha de actualización de `gdxc-w37w` (2025-01-24 vs 2026-09-24 en catálogo); y de `rowsUpdatedAt` de `6jmc-vaxk` | Consultas de metadata y catálogo. |
