# Parque automotor (stock) por marca en Colombia — búsqueda de fuentes

- Fecha de consulta: 2026-10-10
- Alcance: solo lectura. Parte de `docs/08_market_research.md` (Objetivo 1a, Objetivo 4, Ficha 5, "No encontrado"). No repite lo ya probado salvo para confirmarlo.
- Convenciones: **Stock** = parque registrado o activo en un corte. **Flujo** = matrículas nuevas, importaciones, ventas o trámites. **Hecho** = leído en la fuente. **Inferencia** = deducción, marcada como tal.

## Objetivo

Encontrar una fuente real y pública del **parque** automotor de Colombia por **marca** (y modelo si existe) que pueda reemplazar el desglose sintético de D48.

## Método

1. Catálogo Socrata de datos.gov.co (`https://www.datos.gov.co/api/catalog/v1?q=<consulta>`) con estas consultas: `parque automotor`, `marca vehiculo`, `RUNT`, `SOAT`, `Fasecolda`, `vehiculos matriculados` y `movilidad vehiculos marca`. Los candidatos se inspeccionaron con `api/views/<id>.json` y con consultas SODA (`$select=count(*)`, `$group`).
2. Páginas de RUNT en cifras: `parque-automotor` y `balance-del-sector-transito-y-transporte` (PDF anuales).
3. MinTransporte, "Transporte en cifras".
4. Fasecolda: ramo de automóviles y guía de valores.
5. ANDI, Cámara Automotriz.
6. Bogotá: CKAN de datosabiertos.bogota.gov.co, Observatorio de Movilidad y portal de datos de la SDM (ArcGIS Hub).
7. Medellín (MEData, vía el registro federado en datos.gov.co) y Cali (datos.cali.gov.co).
8. No intentado (la sesión de investigación se cortó por límite de uso): UPME, DIAN, CCS y repositorios académicos.

## Tabla de fuentes

| Fuente | URL | Consulta | Cobertura | Stock / flujo | Granularidad | Periodo | Formato | Licencia | Limitaciones |
|---|---|---|---|---|---|---|---|---|---|
| RUNT `u3vn-bdcy` (MinTransporte) | https://www.datos.gov.co/api/views/u3vn-bdcy.json | 2026-10-10 | Nacional; autos, motos y otros | Stock | Clase, servicio, estado, departamento, municipio. **Sin marca** | Corte mensual (catálogo actualizado el 2026-10-05) | API SODA | Ver `08`, Ficha 1 | Sin marca ni modelo (confirmado de nuevo en el catálogo) |
| RUNT en cifras, parque automotor | https://www.runt.gov.co/runt-en-cifras/parque-automotor | 2026-10-10 | Nacional | Stock | Solo totales: motos 14.420.341; vehículos 7.811.710; maquinaria, remolques y semirremolques 244.500; total 22.476.551 | "Corte: Agosto de 2026" | HTML y una imagen estática | No indicada | Sin marca. Sin dashboard embebido: solo `grafica-parque-auomotor-marzo.png` |
| RUNT, Balance del Sector Tránsito y Transporte 2025 | https://www.runt.gov.co/sites/default/files/documentos/Balance%20del%20Sector%20Tr%C3%A1nsito%20y%20Transporte%202025%20%281%29_0.pdf | 2026-10-10 | Nacional | Stock (total) y flujo (traspasos) | Texto legible: parque total 21.345.925 (63 % motos), ranking de municipios, traspasos por clase. Marca: **No verificado** | Año 2025 | PDF de 6,9 MB | No indicada | Las gráficas son imágenes y no se pudieron convertir (falta `pdftoppm`). La cifra de la p. 3 (21.113.175) no cuadra con la de la p. 1 y el texto no lo explica |
| RUNT, Balance 2024 | https://www.runt.gov.co/sites/default/files/documentos/Balance%20del%20Sector%20Tr%C3%A1nsito%20y%20Transporte%202024_0.pdf | 2026-10-10 | Nacional | No verificado | **No verificado** | 2024 | PDF de 2,3 MB (unas 5 páginas) | No indicada | Texto comprimido (FlateDecode), no se pudo extraer |
| RUNT, Balance 2023 | https://www.runt.gov.co/sites/default/files/documentos/Balance%20de%20cifras%20del%20sector%202023%20RUNT.pdf | No abierto | Nacional | No verificado | No verificado | 2023 | PDF | No indicada | No se abrió |
| MinTransporte, Transporte en cifras | https://www.mintransporte.gov.co/publicaciones/9443/transporte-en-cifras/ ; app https://mintransporte.shinyapps.io/transporteencifrasapp2025/ | 2026-10-10 | Nacional | No verificado | No verificado | 2024–2025 | App Shiny | No indicada | La app solo mostró "Please Wait" (requiere JavaScript). La página no trae datos |
| Fasecolda, ramo de automóviles | https://www.fasecolda.com/ramos/automoviles/ | 2026-10-10 | Nacional | Stock (total) | "A cierre de 2024, el país alcanzó cerca de 20 millones de vehículos registrados", 62 % motos y 37 % autos y camionetas; "Solo el 12,2% de los vehículos en el país tiene un seguro voluntario" | Cierre de 2024 | HTML | No indicada | Sin marca. No cita la fuente original |
| Fasecolda, guía de valores | https://www.fasecolda.com/guia-de-valores/ | 2026-10-10 | Nacional | Ninguno (catálogo de precios, Inferencia) | No legible | n/a | App con JavaScript | No indicada | Sin contenido legible. Aunque fuera legible, son valores comerciales, no conteos de parque |
| Socrata, búsqueda "Fasecolda" | https://www.datos.gov.co/api/catalog/v1?q=Fasecolda&limit=20 | 2026-10-10 | n/a | n/a | n/a | n/a | n/a | n/a | 0 resultados |
| Socrata, búsqueda "SOAT" | https://www.datos.gov.co/api/catalog/v1?q=SOAT&limit=40 | 2026-10-10 | Municipal | Stock (municipal) | Solo municipios con `marca` (Envigado, Barbosa, Caldas, Malambo) | Varios | API | Varias | Ningún dataset nacional de SOAT por marca. `e967-4a8r` (Superfinanciera, Formato 290) es financiero, sin marca |
| ANDI, Cámara Automotriz | https://www.andi.com.co/Home/Camara/4-automotriz | 2026-10-10 | Nacional | Flujo (ver `08`, Obj. 1b) | Matrículas nuevas por marca (informes ANDI-FENALCO) | Hasta 2025 | PDF | No indicada | En lo leído no hay parque por marca. La página es muy larga y se leyó parcialmente |
| **Boyacá `em3d-hmim`** (Gobernación de Boyacá) | https://www.datos.gov.co/api/views/em3d-hmim.json | 2026-10-10 | **Departamental** (Boyacá); autos y motos; servicio particular según la descripción (181.878 de 182.379 filas; 501 de otros servicios, 35 PUBLICO) | **Stock** (parque activo) | Una fila por vehículo: `marca`, `linea`, `modelo`, `clase`, `cilindraje`, `cod_dane`, `municipio`, `estado`, `importado` | "vigencia 2024"; filas actualizadas el 2024-08-30; frecuencia declarada semestral | API SODA | CC BY-SA 4.0 | Un solo departamento y un solo corte, sin actualizar desde 2024-08-30. Casi sin servicio público (35 filas). Sin placa: no se puede verificar que no haya duplicados |
| Caldas, Antioquia `dkxf-ikd7` | https://www.datos.gov.co/api/views/dkxf-ikd7.json | 2026-10-10 (catálogo) | Municipal | Stock | Por placa, con `marca` y `modelo` | Actualizado 2026-09-19 | API | No revisada | Municipal |
| Risaralda `x9pp-pcn5` | Catálogo Socrata | 2026-10-10 (catálogo) | Departamental | Stock (registrado) | Por placa, con `marca`, `linea` y `modelo` | Actualizado 2026-07-06 | API | No revisada | No dice si incluye vehículos inactivos. No inspeccionado |
| Fusagasugá `aj2e-7jwg`, Barbosa `5in3-nedb` / `syiu-8mvf` / `wvky-zsdn`, Envigado `fqwq-ik2w`, Floridablanca `g7i9-xkxz`, AMCO Pereira `fvnt-frpb` (este último: transporte público) | Catálogo Socrata | 2026-10-10 (catálogo) | Municipal | Stock | Con `marca` | Varios (Envigado hasta 2018) | API | No revisadas | Municipales. Inferencia: no sirven como proxy nacional |
| Atlántico `n4ic-hiug` | Ver `08`, Ficha 5 | 2026-10-03 | Departamental | No claro: "Vehículos Registrados" anuales (Inferencia: podría ser flujo anual) | `anio`, `marca`, `clase`, `cantidad` | Hasta 2022 | API | Ver `08` | Sin actualizar desde 2022 |
| Medellín, "Parque automotor" (federado `3fqj-86mk`) | http://medata.gov.co/sites/default/files/distribution/1-023-25-000093/parque_automotor.csv ; diccionario: .../Parque_Automotor.json | 2026-10-10 | Municipal | Stock | Diccionario: `Clase`, `Servicio`, `Cantidad`. **Sin marca** | Registro actualizado 2025-08-05 | CSV | CC BY-SA 4.0 | Sin marca. Se leyó el diccionario, no el CSV |
| Cali, "Parque automotor activo" (federado `uqh6-yk4h`) | https://datos.cali.gov.co/dataset/95c5089c-7cd0-4979-976b-c49d3aa57e97/resource/ac3245e9-dc33-4651-8514-c664d6f1baf4/download/parque-automotor-activo-a-2012-2025.csv | 2026-10-10 | Municipal | Stock | `CODIGO`, `CLASE`, `AÑO` (año de fabricación), `CANTIDAD`. **Sin marca** | 2012 al 1-mar-2025 | CSV (40,1 KiB) | Datos.gov.co: CC0. Portal de Cali: CC BY (no coinciden) | Sin marca |
| Bogotá, CKAN datosabiertos.bogota.gov.co | https://datosabiertos.bogota.gov.co/api/3/action/package_search?q=parque%20automotor | 2026-10-10 | Bogotá | n/a | 0 resultados con "parque automotor" | n/a | API CKAN | n/a | Con "vehiculos" solo hay impuesto, terminales y conteos de tráfico |
| Bogotá, SDH "Contribuyentes Vehículos" | https://datosabiertos.bogota.gov.co/dataset/2cc4ec66-d637-4215-a661-4efd9e5712e2/resource/73b9d5d7-b091-4ec4-a8ad-c31b2218e5fb/download/14.-contribuyentes-vehiculos_2000_2023.csv | 2026-10-10 | Bogotá | Proxy de stock (contribuyentes del impuesto vehicular, Inferencia) | `ID;IMPUESTO;AÑO_PRESENTACION;CODIGO_VIGENCIA;CONTRIBUYENTES`. **Sin marca** | 2000–2023 | CSV | CC BY 4.0 | Sin marca |
| Bogotá, Observatorio y portal de datos de la SDM | https://observatorio.movilidadbogota.gov.co/ ; https://datos.movilidadbogota.gov.co/api/search/v1/collections/all/items?q=parque%20automotor | 2026-10-10 | Bogotá | n/a | 0 resultados en la búsqueda del Hub | n/a | ArcGIS Hub | n/a | Los tableros del Observatorio no se revisaron |
| UPME, DIAN, CCS, repositorios académicos | No intentado | — | — | — | — | — | — | — | No intentado (límite de uso de la sesión). DIAN serían importaciones (flujo) aunque tuvieran marca |

## Hallazgos

1. **Hecho:** ninguna búsqueda en el catálogo de datos.gov.co devolvió un dataset **nacional** con marca. Los únicos datasets nacionales del RUNT son `u3vn-bdcy` (parque sin marca), `ntxy-q9ix` (eléctricos e híbridos, sin marca), `akpq-tuqi` (trámites) y `6jmc-vaxk` (vehículos en accidentes, con `marca_vehiculo`). Este último es siniestralidad, no parque.
2. **Hecho:** RUNT en cifras publica el parque nacional solo en totales (22.476.551, corte agosto de 2026). No hay dashboard ni archivo por marca en la página.
3. **No verificado:** los Balances del Sector 2023, 2024 y 2025 del RUNT podrían traer gráficas por marca. El texto legible del de 2025 no las trae, y los de 2023 y 2024 no se pudieron leer.
4. **Hecho:** Fasecolda publica solo totales del parque (cerca de 20 millones a cierre de 2024) y no cita la fuente.
5. **Hecho, Boyacá `em3d-hmim`:** parque activo, casi todo de servicio particular (181.878 de 182.379 filas) (`count(*)` SODA, 2026-10-10). Top 10 de `marca` por número de filas: CHEVROLET 33.917, RENAULT 28.146, YAMAHA 11.411, SUZUKI 9.230, NISSAN 8.692, MAZDA 8.270, TOYOTA 8.218, BAJAJ 7.107, AKT 7.048, FORD 6.984. Por clase (estado ACTIVO): AUTOMOVIL 69.735, MOTOCICLETA 51.584, CAMIONETA 34.460, CAMPERO 19.505, CAMION 3.476, entre otras.
   - Inferencia: en Boyacá, Chevrolet y Renault dominan el parque. Esto concuerda con la hipótesis de marcas de carros de `08`, pero solo en un departamento con un 28 % de motos, muy por debajo del 63–64 % nacional (RUNT). No es representativo del país.
6. **Hecho:** varios municipios publican parque con marca por placa (Caldas, Antioquia, actualizado en 2026-09; Risaralda, en 2026-07; Fusagasugá, en 2026-06). Cada uno tiene su propio esquema y la palabra "parque" significa cosas distintas: activo, registrado o matriculado.
   - Inferencia: sumarlos no da una muestra nacional y tendría sesgo geográfico.
7. **Hecho:** Medellín y Cali publican parque sin marca (solo clase, servicio y año). En Bogotá no se encontró parque por marca en los portales consultados.

## Conclusión

- **Nacional: No encontrado.** No hay fuente pública, real y verificable del parque nacional por marca o modelo en las fuentes intentadas.
- **Subnacional: Parcial.** Hay parque real por marca y línea en Boyacá (`em3d-hmim`, corte 2024) y en algunos municipios.
- **Pendiente (No verificado):** gráficas de los Balances 2023–2025 del RUNT, app de Transporte en cifras de MinTransporte, tableros del Observatorio de Bogotá, UPME y DIAN.

## Implicación para D48

- D48 se sostiene. La demanda sigue midiéndose con RUNT `u3vn-bdcy` (stock por clase y geografía), y el desglose por marca y modelo sigue siendo sintético.
- Mejora posible, que requiere una D nueva aprobada por Henry (no aplicada): usar Boyacá `em3d-hmim` como **insumo de calibración** del sintético. Es stock real con marca y línea, así que es mejor insumo que las matrículas nuevas (flujo) que hoy usa D48. Habría que ajustarlo por la mezcla de clases nacional de `u3vn-bdcy` (Boyacá tiene un 28 % de motos frente al 63–64 % nacional) y marcarlo como regional en su procedencia.
- No hay fila D en borrador: no apareció una fuente nacional de parque por marca que reemplace el sintético.

## Implicación para D50

D50 descarta el derecho de petición a MinTransporte y deja la Fase 2 con fuentes públicas existentes más el sintético de D48. Esta investigación respalda esa decisión: a nivel nacional no hay fuente pública de parque por marca, y lo único disponible es regional o municipal (insumo posible de calibración, no reemplazo).

## Preguntas de dominio para Henry

1. ¿Te sirve un parque regional real (Boyacá, casi solo servicio particular) como calibración del sintético, o prefieres seguir con matrículas nuevas de ANDI-FENALCO?
2. Para repuestos, ¿pesa más la marca o la línea (por ejemplo, Chevrolet Spark frente a Chevrolet en general)? `em3d-hmim` trae `linea`.
3. ¿El servicio público (taxis, buses) es un segmento comprador relevante? Boyacá casi no lo incluye (35 filas).
4. ¿Conoces algún informe gremial (FENALCO, Asopartes, Fasecolda) que publique parque por marca, aunque sea en PDF?

## Segunda ronda (2026-10-10)

- Fecha de consulta: 2026-10-10. Todas las cifras se obtuvieron con `curl -sG --data-urlencode` contra SODA (`https://www.datos.gov.co/resource/<id>.json`) y los metadatos con `https://www.datos.gov.co/api/views/<id>.json`. Las cifras de esta sección prevalecen sobre las de la primera ronda donde difieran (ver sección 6).
- **Dato** = leído en la fuente. **Inferencia** = deducción mía, marcada como tal.
- `rowsUpdatedAt` = fecha de actualización de los **datos**. `viewLastModified` (el `updatedAt` del catálogo) = última modificación de los **metadatos**; no indica frescura de los datos.

### 1. Tabla por fuente

| Fuente | URL / dataset | Consulta | Corte (`rowsUpdatedAt`) vs metadatos (`viewLastModified`) | Cobertura autos / motos | Stock o flujo | Columnas reales | Licencia | Limitaciones |
|---|---|---|---|---|---|---|---|---|
| RUNT `u3vn-bdcy` (MinTransporte) | https://www.datos.gov.co/resource/u3vn-bdcy.json | 2026-10-10 | Datos 2026-10-05 17:22 UTC; metadatos 2026-10-05 17:20 UTC. Corte de publicación: OCTUBRE 2026 | Nacional. AUTOMOVIL 4.059.090; MOTOCICLETA 14.523.793 (64,1 % de 22.655.040) | Stock (parque por clase, servicio, estado y municipio; frecuencia mensual según metadatos) | `nombre_departamento`, `nombre_municipio`, `nombre_servicio`, `estado_del_vehiculo`, `nombre_de_la_clase`, `fecha_de_registro`, `cantidad`, `mes_de_publicacion`, `a_o_de_publicacion`. **Sin marca** | CC BY-SA 4.0 (`CC_40_BY_SA`) | Sin marca ni modelo. Clases duplicadas por tilde (`CAMION` / `CAMIÓN`). Ver sección 3 |
| Risaralda `x9pp-pcn5` | https://www.datos.gov.co/resource/x9pp-pcn5.json | 2026-10-10 | Datos 2026-07-06; metadatos 2026-07-06 | Departamental. 453.925 filas: MOTOCICLETA 251.757 (55,5 %), AUTOMOVIL 110.290 (24,3 %) | Stock ("registrado": una fila por placa, Inferencia; sin estado, no se distingue activo de inactivo) | `clase`, `placa`, `marca`, `modelo`, `linea`, `cilindraje`. **Sin `servicio` ni `estado`** | CC BY-SA 4.0 | No se puede filtrar por servicio ni por estado. El parque "registrado" puede incluir vehículos inactivos |
| Boyacá `em3d-hmim` | https://www.datos.gov.co/resource/em3d-hmim.json | 2026-10-10 | Datos 2024-08-30; metadatos 2026-05-18 | Departamental, casi solo servicio particular (181.878 de 182.379 filas). AUTOMOVIL 69.735; MOTOCICLETA 51.584 (28,3 %) | Stock (`estado` = ACTIVO en todas las filas) | `n`, `motivo_ingreso`, `cod_dane`, `dane_mun`, `provincia`, `municipio`, `clase`, `marca`, `linea`, `modelo`, `carroceria`, `pasajeros`, `tonelaje`, `cilindraje`, `servicio`, `estado`, `blindaje`, `importado` | CC BY-SA 4.0 | Corte de agosto de 2024 (dos años de antigüedad). `servicio`: PARTICULAR 181.878, OFICIAL 396, PUBLICO 35, OTRO 33, MIXTO 22, NA 13, DIPLOMATICO 2. `AUTECO` es una marca de distribuidor, no de fabricante (sección 5) |
| Floridablanca `g7i9-xkxz` | https://www.datos.gov.co/resource/g7i9-xkxz.json | 2026-10-10 | Datos 2023-02-10; metadatos 2026-05-18 | Municipal. 177.969 filas: MOTOCICLETA 116.527, AUTOMOVIL 28.655 | Stock ("Vehiculos activos" según el título, Inferencia) | `placa`, `clase`, `marca`, `modelo`, `servicio`, `cilindraje`. Sin `linea` | CC BY-SA 4.0 | Datos de 2023. `servicio`: PARTICULAR 153.515, PUBLICO 22.326, OTRO 1.804, OFICIAL 324. Marcas de AUTOMOVIL PUBLICO (4.863 filas): HYUNDAI 3.328 (68,4 %), KIA 626 (12,9 %), CHEVROLET 513 (10,5 %), RENAULT 174, DAEWOO 142 (Dato). Inferencia: es el perfil del taxi urbano, no del parque general |
| AMCO (Pereira) `fvnt-frpb` | https://www.datos.gov.co/resource/fvnt-frpb.json | 2026-10-10 | Datos 2020-11-07; metadatos 2026-05-18 | Solo transporte público (4.390 filas) | Stock (`estado_activo_1_inactivo`: activo 3.613, inactivo 777) | `placa`, `lateral`, `tipo_de_vehiculo`, `modelo`, `marca`, `n_mero_de_pasajeros`, `tipo_de_carrocer_a`, `estado_activo_1_inactivo` | CC BY-SA 4.0 | Datos de 2020. Solo flota de transporte público; no sirve para el parque general |
| Fusagasugá `aj2e-7jwg` | https://www.datos.gov.co/resource/aj2e-7jwg.json | 2026-10-10 | Datos 2026-06-01; metadatos 2026-06-01. Máxima `fechamatricula`: 2026-01-30 | Municipal. 48.636 filas: MOTOCICLETA 30.594, AUTOMOVIL 5.946. Top automóvil: CHEVROLET 2.770, RENAULT 1.161, MAZDA 479 | Stock ("matriculados" según el título; no hay columna de estado, Inferencia) | `fechamatricula`, `modelo`, `servicio`, `marca`, `color`, `combustible`, `tipo`, `cilindraje`, `carroceria`, `linea` | CC BY-SA 4.0 | Hay filas con `marca` = `SIN INFORMACIÓN` y `modelo` con separador de miles (`1.936`). Muestra pequeña |
| Barranquilla `g4h5-prph` | https://www.datos.gov.co/resource/g4h5-prph.json | 2026-10-10 | Datos 2026-07-28; metadatos 2026-07-28. Último periodo: junio de 2026 (`a_o_corte` 2026, `mes_corte` 6) | Municipal, agregado por clase y servicio. **Sin marca** | Stock (acumulado mensual) | `registro`, `servicio_vehiculos`, `clase_vehiculos`, `combustible_vehiculos`, `a_o_corte`, `mes_corte`, `tipo_registro`, `cantidad_vehiculos` | CC BY-SA 4.0 | Sin marca. Mezcla `Automotor` y `No Automotor` en `tipo_registro`: no sumar sin filtrar |
| Caldas, Antioquia `dkxf-ikd7` | https://www.datos.gov.co/resource/dkxf-ikd7.json | 2026-10-10 | Datos **2020-10-05**; metadatos 2026-09-19 | Municipal. 5.415 filas | Stock (corte antiguo) | `placa`, `a_o_de_registro`, `clase`, `marca`, `modelo`, `servicio`, `carroceria`, `cilindraje`, `capacidad_de_pasajeros`, `capacidad_de_carga`, `tipo_de_combustible`, `peso`, `revisi_n_tecnico_mecanica`, `soat_vigente` | CC BY-SA 4.0 | Datos de 2020; máximo `a_o_de_registro` = 2020. Ver sección 6 |
| Barbosa, Antioquia `syiu-8mvf` | https://www.datos.gov.co/resource/syiu-8mvf.json | 2026-10-10 | Datos **2020-01-16**; metadatos 2026-09-12 | Municipal. 4.242 filas. Título: "al año 2018" | Stock (corte antiguo) | `a_o_de_registro`, `autoridad_de_tr_nsito`, `cilindraje`, `capacidad_de_pasajeros`, `capacidad_de_carga`, `clase`, `carrocer_a`, `marca`, `tipo_de_combustible`, `modelo`, `peso`, `revisi_n_tenico_mec_nica`, `servicio`, `soat_vigente`, `placa` | CC BY-SA 4.0 | Datos de 2018 publicados en 2020; máximo `a_o_de_registro` = 2018. Ver sección 6 |

Inferencia: Risaralda es el único dataset de la tabla con parque grande (más de 450.000 filas), vigente (2026-07) y con `linea`. Boyacá tiene `servicio` y `estado`, pero su corte es de 2024.

### 2. No encontrado (consultas intentadas)

Catálogo usado: `https://api.us.socrata.com/api/catalog/v1?domains=www.datos.gov.co&q=<consulta>`, con estas consultas: `parque automotor`, `marca vehiculo`, `parque vehicular`, `vehiculos matriculados`, `RUNT`, `transito vehiculos registrados`, `taxis`, `Antioquia vehiculos marca`, `Valle del Cauca parque automotor`, `Medellin movilidad vehiculos`, `Bucaramanga vehiculos`, `Santander parque automotor`.

| Objetivo | Intentado | Resultado |
|---|---|---|
| Parque nacional por marca | Todas las consultas anteriores | No encontrado (se mantiene la conclusión de la primera ronda) |
| Bucaramanga / Santander departamental | Catálogo: `Bucaramanga vehiculos`, `Santander parque automotor` | No encontrado |
| Bogotá, parque por marca | CKAN `https://datosabiertos.bogota.gov.co/api/3/action/package_search` con `q=vehiculos marca` (0 resultados), `q=parque automotor matriculado` (0), `q=flota` (3, sin marca; incluye `flota-vinculada-del-sitp`), `q=taxis` (tiempo de espera agotado) | No encontrado. SITP es flota de transporte público sin marca |
| Medellín (MEData) | API `package_search` (404); el buscador web requiere JavaScript | No encontrado / No verificado |
| Antioquia departamental | Catálogo: solo trámites (`b7g5-7znb`) y accidentes | No encontrado |
| Atlántico `n4ic-hiug` | Metadatos y consulta SODA | Datos solo hasta 2022 |
| Valle del Cauca, Cali, Palmira | Catálogo | Sin marca de parque |

### 3. RUNT `u3vn-bdcy`: valores reales, servicio x clase y cambio de corte

Consultas (todas con `curl -sG https://www.datos.gov.co/resource/u3vn-bdcy.json` y `--data-urlencode`):

- Servicio: `$select=nombre_servicio,count(*),sum(cantidad)&$group=nombre_servicio&$order=nombre_servicio`
- Clase: `$select=nombre_de_la_clase,count(*),sum(cantidad)&$group=nombre_de_la_clase&$order=nombre_de_la_clase&$limit=200`
- Corte: `$select=a_o_de_publicacion,mes_de_publicacion,estado_del_vehiculo,count(*),sum(cantidad)&$group=a_o_de_publicacion,mes_de_publicacion,estado_del_vehiculo`
- Servicio x clase (ACTIVO): `$select=nombre_de_la_clase,nombre_servicio,sum(cantidad)&$where=estado_del_vehiculo='ACTIVO'&$group=nombre_de_la_clase,nombre_servicio`

**Corte.** Dato: hay un solo corte, 2026 OCTUBRE: ACTIVO 22.613.691 (183.261 filas) e INCONSISTENTE 41.349 (8.661 filas). Total 22.655.040. El corte AGOSTO 2026 citado en `08` y `03` ya no existe en el dataset. Inferencia: SODA solo conserva el corte vigente, así que una cifra de un corte anterior no se puede reproducir con esta fuente.

**`nombre_servicio`** (5 valores; suma de `cantidad`, todos los estados):

| Valor | Filas | Suma `cantidad` |
|---|---|---|
| NO REGISTRA | 13.910 | 234.737 |
| OFICIAL | 20.753 | 209.588 |
| OTROS | 858 | 2.948 |
| PARTICULAR | 91.265 | 21.107.056 |
| PÚBLICO | 65.136 | 1.100.711 |
| Total | 191.922 | 22.655.040 |

**`nombre_de_la_clase`** (99 valores; suma de `cantidad`, todos los estados):

ABONADORA 10 | ALZADORA DE CAÑA 79 | APILADOR 79 | APLANADORA 169 | AUTOHORMIGONERA 489 | AUTOMOVIL 4.059.090 | BARREDORA 32 | BULDOZER 4.497 | BUS 85.065 | BUSETA 34.706 | CAMBIADORA DE RIEL 4 | CAMION 322.288 | CAMIÓN 437 | CAMION CARGA EXTENSA 7 | CAMION CISTERNA 2 | CAMIÓN DE RESCATE 1 | CAMIÓN ESCALERA 1 | CAMIÓN ESTÉRIL 7 | CAMIONETA 2.166.093 | CAMIÓN GRÚA 280 | CAMIÓN TIJERA 2 | CAMPERO 782.026 | CARGADOR 7.601 | CARGADORA FRONTAL 271 | CARRETILLA APILADORA 195 | CARRETILLA ELEVADORA 341 | CICLOMOTOR 15.698 | COMPACTADOR 1.061 | COMPOSTADORA 3 | CORTADORA 15 | COSECHADORA 2.659 | CRIBAS 59 | CUADRICICLO 1.877 | CUATRIMOTO 18.350 | DISTRIBUIDOR AUTOPROPELIDO DE FERTILIZANTES 3 | DRAGA 16 | DUMPER (VOLQUETA ARTICULADA) 498 | EQUIPO DE DEMOLICION 2 | EQUIPO DE TRANSFERENCIA DE MATERIAL 1 | EXCAVADORA 25.257 | FERTILIZADORA 1 | FINICHER 18 | FRESADORA 140 | FUMIGADORA 7 | GATOR 53 | GRUA 724 | HORMIGONERA PARA TÚNELES 22 | IRRIGADOR 2 | JUMBO DE PERFORACION 65 | MANIPULADOR CARGADOR TELESCOPICO 34 | MANIPULADOR TELESCOPICO 465 | MAQ. AGRICOLA 7.141 | MAQ. CONSTRUCCION O MINERA 1 | MAQ. INDUSTRIAL 4.587 | MAQUINA BARREDORA 43 | MAQUINA TRAZADORA 2 | MICROBUS 82.986 | MINICARGADOR 8.441 | MINI EXCAVADORA 2.008 | MINI RETROEXCAVADORA 120 | MONTACARGAS 8.353 | MOTOCARRO 183.365 | MOTOCICLETA 14.523.793 | MOTONIVELADORA 2.989 | MOTOTRAÍLLA 8 | MOTOTRICICLO 963 | PALA DRAGA 33 | PALA FRONTAL 8 | PAVIMENTADORA 314 | PENETROMETRO AUTOPROPULSADO 2 | PERFILADORA DE PAVIMENTO EN FRIO 8 | PERFORADORA 448 | PILOTEADORA 149 | PLANTA DE ASFALTO CONTRAFLUJO 3 | PLATAFORMA DE ELEVACION 380 | PRENSA HIDRAULICA 2 | PULVERIZADOR AGRICOLA 27 | RECICLADORA 18 | RECICLADORA DE LODO 2 | RECICLADORA DE PAVIMENTOS 5 | REMOLQUE 3.270 | RETROCARGADOR 1.045 | RETROEXCAVADORA 14.087 | SEMIREMOLQUE 127.741 | SIN CLASE 58 | TALADRO 60 | TALADRO PERFORACION POZO PETROLERO 100 | TRACTOCAMION 72.391 | TRACTOR 15.480 | TRACTOR SOBRE ORUGA 208 | TRANSPLANTADORA 14 | TRICIMOTO 687 | TRITURADORA 131 | UTILERO 5 | VIBROCOMPACTADORA 3.556 | VOLCO 24 | VOLQUETA 59.148 | VOLQUETA SOBRE ORUGA 16 | ZANJADORA 18

La suma de las 99 clases coincide con el total de servicio (22.655.040). Dato: `CAMION` (322.288) y `CAMIÓN` (437) son la misma clase escrita con y sin tilde; hay que normalizarlas antes de agrupar (regla candidata para `stg`, no aplicada). Las clases `CAMIÓN ...` (`CAMIÓN GRÚA`, `CAMIÓN ESCALERA`, etc.) mezclan tilde y sin tilde con `CAMION CARGA EXTENSA` y `CAMION CISTERNA`.

**Servicio x clase, estado ACTIVO** (clases principales; suma de `cantidad`):

| Clase | PARTICULAR | PÚBLICO | OFICIAL | OTROS | NO REGISTRA |
|---|---|---|---|---|---|
| MOTOCICLETA | 14.396.766 | 8 | 114.011 | 2.200 | 9 |
| AUTOMOVIL | 3.794.661 | 234.003 | 15.676 | 284 | 20 |
| CAMIONETA | 1.821.047 | 298.172 | 41.469 | 144 | 5 |
| CAMPERO | 736.448 | 24.349 | 15.541 | 169 | 2 |
| CAMION (sin tilde) | 67.694 | 240.664 | 11.597 | 39 | 0 |

Dato: motos en servicio PÚBLICO = 8 y OFICIAL = 114.011. Inferencia: el servicio público (taxis, buses, camiones de carga) pesa en AUTOMOVIL, CAMIONETA y CAMION, y casi nada en moto. Importa si el parque por marca se pondera por servicio.

### 4. Comparación Boyacá vs Risaralda (participación por marca)

Denominador: filas de la clase (Boyacá: `estado='ACTIVO'`; Risaralda: todas las filas de la clase, sin estado). Consulta: `$select=marca,count(*)&$where=clase='AUTOMOVIL'&$group=marca&$order=count DESC` (y lo mismo con `MOTOCICLETA`).

**AUTOMOVIL** (Boyacá 69.735 filas; Risaralda 110.290):

| Marca | Boyacá | % | Risaralda | % |
|---|---|---|---|---|
| RENAULT | 24.378 | 35,0 | 24.341 | 22,1 |
| CHEVROLET | 22.260 | 31,9 | 32.074 | 29,1 |
| MAZDA | 4.949 | 7,1 | 16.408 | 14,9 |
| KIA | 3.285 | 4,7 | 9.151 | 8,3 |
| NISSAN | 2.446 | 3,5 | 5.375 | 4,9 |
| VOLKSWAGEN | 1.913 | 2,7 | 3.481 | 3,2 |
| HYUNDAI | 1.443 | 2,1 | 7.251 | 6,6 |
| FORD | 1.433 | 2,1 | 2.264 | 2,1 |

**MOTOCICLETA** (Boyacá 51.584 filas; Risaralda 251.757). Orden: conteo descendente de Boyacá; las marcas fuera del top 12 de Boyacá van al final, por conteo de Risaralda:

| Marca | Boyacá | % | Risaralda | % |
|---|---|---|---|---|
| YAMAHA | 11.364 | 22,0 | 43.858 | 17,4 |
| BAJAJ | 6.983 | 13,5 | 36.609 | 14,5 |
| AKT | 6.660 | 12,9 | 46.979 | 18,7 |
| AUTECO | 5.818 | 11,3 | 1.890 | 0,8 |
| SUZUKI | 5.497 | 10,7 | 36.862 | 14,6 |
| HONDA | 2.933 | 5,7 | 34.623 | 13,8 |
| TVS | 2.199 | 4,3 | 7.069 | 2,8 |
| SIGMA | 1.985 | 3,8 | fuera del top 12 | n/d |
| VICTORY | 1.658 | 3,2 | 9.191 | 3,7 |
| UNITED MOTORS | 955 | 1,9 | fuera del top 12 | n/d |
| AUTECO BAJAJ | 821 | 1,6 | fuera del top 12 | n/d |
| KYMCO | fuera del top 12 | n/d | 10.578 | 4,2 |
| HERO | fuera del top 12 | n/d | 7.021 | 2,8 |

Lectura (Inferencia, a partir de las tablas anteriores):

- En automóvil, Chevrolet y Renault suman 66,9 % en Boyacá y 51,2 % en Risaralda. Mazda pesa el doble en Risaralda (14,9 % frente a 7,1 %). La mezcla de marcas cambia mucho entre departamentos; una sola región no sirve de calibración nacional.
- En moto, el top 5 de Risaralda (AKT, Yamaha, Suzuki, Bajaj, Honda) suma 79,0 %. Honda pesa 13,8 % en Risaralda frente a 5,7 % en Boyacá.
- En Boyacá, 11,3 % de las motos están bajo `AUTECO`, una etiqueta de distribuidor (sección 5). Si se asignan a Bajaj las líneas que la sección 5 mapea a Bajaj, solo en `clase='MOTOCICLETA'` (5.181 Dato + 50 Inferencia = 5.231 filas, sin contar `AUTECO BAJAJ`), Bajaj sumaría 12.214 filas de moto (6.983 + 5.231; 23,7 % de 51.584) y quedaría por encima de Yamaha (22,0 %). Nota: las 5.221 (Dato) + 51 (Inferencia) = 5.272 filas Bajaj de la tabla de la sección 5 cubren todas las clases; incluyen 41 filas fuera de moto (MOTOCARRO 25 + 1, AUTOMOVIL 14, MOTOTRICICLO 1). Usar la columna `marca` tal cual sesga cualquier calibración.
- Boyacá es casi solo servicio particular, con corte 2024-08; Risaralda no tiene `servicio` ni `estado`, con corte 2026-07. No son directamente comparables en alcance.

La calibración multirregión Boyacá + Risaralda fue aprobada por Henry como D55 (ver `05_decisions_log.md`).

### 5. Mapeo AUTECO a marca real por línea (Boyacá `em3d-hmim`)

Henry decidió "asignar a marca real cada uno". Dato: en Boyacá hay 5.862 filas con `marca` = `AUTECO` (MOTOCICLETA 5.818; MOTOCARRO 29; AUTOMOVIL 14; MOTOTRICICLO 1), en 555 valores distintos de `linea` (565 combinaciones `linea`+`clase`). Consulta: `$select=linea,clase,count(*)&$where=marca='AUTECO'&$group=linea,clase&$limit=5000`. Existen además las marcas `AUTECO BAJAJ` (821 filas de moto) y `AUTECO VICTORY`, que ya traen la marca real y no necesitan mapeo.

**Fuente pública de la asignación.**

- Wikipedia, "Auteco" (https://es.wikipedia.org/wiki/Auteco, consultada 2026-10-10): desde 2019 Auteco Mobility ensambla y distribuye Kawasaki, Kymco, Stärker y la marca propia Victory; Auteco S.A.S. ensamblaba y distribuía Bajaj, KTM y Husqvarna; en septiembre de 2020 se anunció el fin de la relación con Bajaj y la alianza con TVS. El artículo cita "Bajaj Boxer CT 100" y "Bajaj Pulsar 180".
- Sitio oficial (https://www.auteco.com.co/, consultado 2026-10-10): la barra de marcas lista TVS, Victory, Kymco, Benelli, Kawasaki, Zontes, Ceronte. No lista Bajaj ni KTM.

**Evidencia de la propia tabla (Dato).** Las mismas familias de `linea` aparecen en Boyacá bajo la marca real. Filas por `marca` para cada patrón (`$where=linea like '%<patrón>%'`, 2026-10-10):

| Patrón de `linea` | Marcas en Boyacá (filas) |
|---|---|
| PULSAR | BAJAJ 6.149; AUTECO 4.532; AUTECO BAJAJ 547; AKT 9; PULSAR 5; otras 3 marcas con 1 fila c/u (BAER BAGULET, HONDA, SPORT) |
| DISCOVER | AUTECO 542; BAJAJ 268; AUTECO BAJAJ 54; RENAULT 17; LAND ROVER 10 |
| DOMINAR | BAJAJ 306; AUTECO 32 |
| BOXER | BAJAJ 146; AUTECO 9; YAMAHA 1 |
| AVENGER | BAJAJ 13; AUTECO 5 |
| RE 4S (motocarro) | BAJAJ 22; AUTECO 13; AUTECO BAJAJ 8 |
| FURAX | AUTECO 60; VICTORY 6; AUTECO VICTORY 2 |
| MRX | VICTORY 641; AUTECO 6; SUZUKI 2 |
| AGILITY CITY | AUTECO 11; KYMCO 7 |
| KLX (prefijo) | KAWASAKI 208; VICTORY 1; YAMAHA 1; AUTECO 1 |
| DUKE | KTM 275; AUTECO 1 |
| CBF 150 | HONDA 125; AUTECO 1 |
| SG 150 (igualdad exacta) | SIGMA 67; AUTECO 1 |
| PLUS (prefijo) | AUTECO 75; AUTECO BAJAJ 1 (ninguna otra marca) |

Las filas RENAULT y LAND ROVER de DISCOVER son ruido (modelos de automóvil con nombre parecido), no Auteco.

**Tabla de mapeo** (reglas sobre las 5.862 filas `AUTECO`; Dato = la familia aparece con prefijo de marca o bajo esa marca en la misma tabla; Inferencia = deducción mía):

| Líneas (`linea`) | Marca real | Tipo | Filas | % de AUTECO |
|---|---|---|---|---|
| PULSAR (todas las variantes: 135 LS, 180 UG, NS 160, 200 NS, RS 200, AS 200, 220, etc.), DISCOVER / DISCOVERY (150 ST, Supreme, 135, Sport), BOXER, DOMINAR (400, D250), AVENGER 220, RE 4S / RE 205 / RE MAXIMA (motocarro), cualquier `linea` con prefijo `BAJAJ` o `MOTOCICLETA - BAJAJ` | BAJAJ | Dato | 5.221 | 89,1 |
| Variantes mal escritas de PULSAR (`PYULSAR`, `PUSAR`, `PILSAR`, `PUILSAR`, `PULSRA`, `PULSA ...`), `RE ASRE205C`, `SPEED` / `SPEED BSIV` / `SPEED 135` sin prefijo | BAJAJ | Inferencia (typos de PULSAR; SPEED se lee como Pulsar Speed, que aparece como `PULSAR SPEED` y `BAJAJ PULSAR SPEED`) | 51 | 0,9 |
| FURAX, MRX150, `VICTORY ...` | VICTORY | Dato | 68 | 1,2 |
| AGILITY CITY 150 (y variantes), `KYMCO` | KYMCO | Dato | 14 | 0,2 |
| KLX 150L | KAWASAKI | Dato | 1 | 0,0 |
| KTM 200 DUKE | KTM | Dato | 1 | 0,0 |
| CBF 150 PREMIUM | HONDA | Inferencia (la familia CBF 150 aparece 125 veces bajo HONDA) | 1 | 0,0 |
| SG 150 / SG-150 | SIGMA | Inferencia (67 filas `SG 150` bajo SIGMA) | 2 | 0,0 |
| `SIN LINEA`, `NA` | Sin asignar | La línea no informa la marca | 398 | 6,8 |
| PLUS 150, PLUS POWER 150, PLUS CLASSIC 150, `PLUS` | Sin asignar | Solo aparece bajo AUTECO; Wikipedia cita "la Plus" de Auteco (1993) sin decir la marca | 75 | 1,3 |
| `L 150`, `AUTECO`, `TURISMO`, `SPORT`, `BLACK`, `ABM 150`, `PICK UP VAN 173`, `AK 200TTR`, `MOTOCICLETA - LINEAS Y CILINDR`, fragmentos (`135SLS`, `200NS`, `150NS`, `200`) y otros typos aislados | Sin asignar | Sin evidencia suficiente | 30 | 0,5 |
| **Total** | | | **5.862** | **100,0** |

Cálculo: 5.221 + 51 + 68 + 14 + 1 + 1 + 1 + 2 + 398 + 75 + 30 = 5.862. Quedan 5.359 filas (91,4 %) asignadas a una marca real y 503 (8,6 %) "Sin asignar".

Notas:

- Inferencia: el fabricante de Pulsar, Discover, Boxer, Dominar, Avenger y RE es Bajaj. La evidencia directa es que las mismas líneas aparecen con prefijo `BAJAJ` o bajo `marca` = `BAJAJ` / `AUTECO BAJAJ` en la propia tabla; Wikipedia solo cita de forma explícita Boxer CT 100 y Pulsar 180.
- El sitio actual de Auteco ya no lista Bajaj, lo que concuerda con el fin de la relación en 2020 (Wikipedia). Esos vehículos siguen en el parque porque el parque es stock, no ventas (regla 5 del proyecto).
- Si se implementa, el mapeo debe ir como seed de dbt con las líneas exactas (555 valores distintos de `linea`) y no como una regex opaca; las regex de arriba son las reglas con que se calcularon los conteos.
- Risaralda `x9pp-pcn5`: `AUTECO` pesa 0,8 % (1.890 filas). Sus líneas más frecuentes (Dato): PULSAR 349, PLUS 150 302, PULSAR 180 293, BOXER 99.35 208, DISCOVER 122, PULSAR BLACK 77, DISCOVER SUPREME 70, ACTIVE 110 69, AGILITY 58, PLUS POWER 57, PLATINO 55, FURAX 150 45, SIN LINEA 34, LEGEND 19. El mapeo de arriba cubre casi todas; `ACTIVE 110`, `PLATINO` y `LEGEND` no están en Boyacá y quedarían "Sin asignar" (No verificado más allá del top 15), y `AGILITY` sería KYMCO (Inferencia).

### 6. Nota de corrección: Caldas y Barbosa

En la tabla de fuentes de la primera ronda, la fila de Caldas `dkxf-ikd7` dice "Actualizado 2026-09-19", y el Hallazgo 6 dice "Caldas, Antioquia, actualizado en 2026-09". Esa fecha es `viewLastModified` (metadatos), no la fecha de los datos. Corrección (Dato, 2026-10-10):

- Caldas `dkxf-ikd7`: `rowsUpdatedAt` = 2020-10-05; el máximo de `a_o_de_registro` es 2020. Los metadatos se modificaron el 2026-09-19.
- Barbosa `syiu-8mvf`: `rowsUpdatedAt` = 2020-01-16; el título dice "al año 2018" y el máximo de `a_o_de_registro` es 2018. Los metadatos se modificaron el 2026-09-12.

Consecuencia: ni Caldas ni Barbosa son parque vigente. La fecha "actualizado" del catálogo de Socrata no es la frescura de los datos; hay que comparar `rowsUpdatedAt` con `viewLastModified`. Pasa lo mismo con Boyacá (datos 2024-08-30; metadatos 2026-05-18), Floridablanca (datos 2023-02-10; metadatos 2026-05-18) y AMCO (datos 2020-11-07; metadatos 2026-05-18). Las fechas de Fusagasugá (2026-06-01) y Risaralda (2026-07-06) de la primera ronda siguen siendo correctas: ahí `rowsUpdatedAt` y `viewLastModified` coinciden.

Corrección sobre RUNT: la primera ronda cita "corte agosto de 2026" para RUNT en cifras (página web), y `08` / `03` lo citan para `u3vn-bdcy`. La consulta SODA del 2026-10-10 devuelve únicamente el corte OCTUBRE 2026 (sección 3). La cifra de RUNT en cifras (22.476.551, agosto) y la de SODA (22.655.040 con todos los estados, octubre) son de cortes distintos y no deben compararse como si fueran el mismo.

### 7. Comparación con la corrida regional real (2026-10-14)

Fuente: corrida real del hito A de marca (`06_status.md` §3; `05` sección E-8), ejecutada por el orquestador el 2026-10-14. Son cifras de Boyacá (`em3d-hmim`, datos de 2024-08-30) y Risaralda (`x9pp-pcn5`, datos de 2026-07-06), ponderadas por el parque RUNT de cada departamento. **No son dato nacional** y no reemplazan las secciones anteriores ni la brecha de parque nacional por marca (`06_status.md` §1).

**AUTECO en Boyacá (diferencia de conteos).** La sección 5 documenta 5.862 filas AUTECO, con BAJAJ 5.272 y SIN ASIGNAR 503. La seed `auteco_line_brand_map` (D139), generada con las reglas de la tabla de mapeo, da BAJAJ 5.276 y SIN ASIGNAR 499; el resto (VICTORY 68, KYMCO 14, SIGMA 2, HONDA 1, KAWASAKI 1, KTM 1) suma 5.862 con esos dos. La diferencia es de 4 filas: typos aislados que la investigación dejó sin asignar y que la seed asigna a BAJAJ por inferencia (`evidence` = `inferencia`). Pendiente: revisión de Henry en el PR.

**AUTECO en Risaralda.** La sección 4 cita 1.890 filas (0,8 %), pero esa cifra corresponde solo a MOTOCICLETA (tabla de motos de la sección 4). La seed cuenta 1.897 filas AUTECO en todas las clases: BAJAJ 1.137, SIN ASIGNAR 640, KYMCO 62 y VICTORY 58. Inferencia, no verificada clase por clase: las 7 filas de diferencia son de clases distintas de moto.

**Participaciones pooled (corrida, ponderadas por el RUNT).** Participación sobre las regiones que tienen la clase:

- AUTOMOVIL: CHEVROLET 30,36 %; RENAULT 27,91 %; MAZDA 11,36 %; KIA 6,68 %; HYUNDAI 4,54 %; NISSAN 4,26 %.
- MOTOCICLETA: YAMAHA 19,02 %; BAJAJ 18,85 %; AKT 16,65 %; SUZUKI 13,25 %; HONDA 10,92 %; VICTORY 3,56 %.
- SIN ASIGNAR pooled: MOTOCICLETA 0,50 %; MOTOCARRO 0,22 %; MOTOTRICICLO 2,34 %.

Comparación con la sección 4, que da participaciones por departamento sin ponderar. Derivado de cifras ya publicadas, sin recalcular la base: en AUTOMOVIL, CHEVROLET y RENAULT suman 66,9 % en Boyacá y 51,2 % en Risaralda; la pooled suma 58,27 % (30,36 + 27,91), entre los dos valores, como corresponde a un promedio ponderado. En MOTOCICLETA, el top 5 de Risaralda de la sección 4 (AKT, Yamaha, Suzuki, Bajaj y Honda) suma 79,0 %; la pooled de esas cinco marcas suma 78,69 %. No es una diferencia de la misma base: la sección 4 no pondera. No se calculó una diferencia por marca; si hace falta, debe hacerse con la misma base.

Alcance: estas participaciones son regionales y no son participación nacional de parque por marca. Ninguna de estas cifras se usa como calibración nacional.
