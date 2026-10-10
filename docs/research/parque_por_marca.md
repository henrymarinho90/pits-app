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
