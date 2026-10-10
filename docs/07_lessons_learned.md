# 07 — Bitácora de lecciones

Última actualización: 2026-10-09

Objetivo: convertir errores, decisiones y descubrimientos del proyecto en conocimiento reutilizable. Cada lección debe responder, idealmente, **qué pasó, por qué importa y qué hacer la próxima vez**.

## Proyecto anterior — Ecommerce Returns & Profitability

| # | Lección | Contexto / acción |
|---|---|---|
| 1 | Nunca asumir nombres de columnas | Se asumió `products.product_id`; la columna real era `products.id`. Inspeccionar schema primero. |
| 2 | `git push` no ejecuta SQL | Subir un `.sql` no cambia Postgres. Separar versionado de ejecución/deploy. |
| 3 | Los metadatos de herramientas pueden quedar desactualizados | Refrescar DBeaver/Metabase después de cambios de schema. |
| 4 | La granularidad determina qué se puede filtrar | Un mart agregado por producto perdió fecha/canal. Definir grano antes de crear el mart. |
| 5 | Los tipos de datos importan | `is_returned` era 0/1 y no boolean. Validar tipos antes de escribir filtros. |
| 6 | Expresiones row-level y agregadas no son equivalentes | Una suma no pertenece a una expresión por fila. Entender el nivel de cálculo. |
| 7 | Los notebooks crean estado oculto | `NameError` por ejecutar celdas fuera de orden. Favorecer módulos/scripts reproducibles. |
| 8 | Las warnings anticipan deuda | Warnings de pandas y zonas horarias no deben ignorarse sistemáticamente. |
| 9 | La materialidad importa | Tasas altas con muestras mínimas generan ruido. Agregar umbrales de volumen. |
| 10 | Correlación no es causalidad | Una correlación casi cero no justifica una historia causal. |
| 11 | Row count no prueba que el cambio ocurrió | Una nueva columna 1:1 puede conservar el mismo número de filas. Verificar schema/valores. |
| 12 | `LIMIT` antes de filtrar cambia la pregunta | Un top global filtrado después no equivale al top dentro de la categoría. |

## Proyecto actual — Data Platform para marketplace de repuestos

| # | Lección | Contexto / acción |
|---|---|---|
| 13 | Medir el consumo real, no solo leer specs | Linux puede mostrar poca RAM `free` y mucha `available`. Medir antes de dimensionar. |
| 14 | Un contenedor sin límite puede afectar todo el host | El VPS tenía servicios sin límite de memoria. Aplicar límites y volver a medir. |
| 15 | Search Console solo representa un sitio propio | No puede usarse como proxy general del mercado sin un sitio propio con tráfico. |
| 16 | Scraping de metadatos no equivale a permiso para extraer contenido | Revisar términos y `robots.txt` por fuente antes de construir extractores. |
| 17 | Una fuente citada no es automáticamente una buena evidencia | Blogs/redes pueden servir para ideas de catálogo, no para estimar frecuencia de mercado. |
| 18 | Las fórmulas de negocio deben tener límites y casos de prueba | `rating x reviews` no tiene techo. Acotar y probar bordes antes de adoptar un score. |
| 19 | Si un estado depende de un valor cambiante, a veces necesitas un snapshot | Guardar condición del contributor al enviar evita que eventos históricos cambien retroactivamente. |
| 20 | El mismo nombre de negocio puede esconder conceptos distintos | “Reputación” técnica del contributor y reputación comercial no deben compartir score. Nombrar la semántica primero. |
| 21 | Si el producto promete una interacción, el modelo debe tener el evento que la representa | El producto hablaba de marketplace, pero no existían ofertas. Agregar `negotiation`/`offer_event`. |
| 22 | El grano debe contener todas las dimensiones que distinguen una fila | `listing` no puede ser único por seller+part+condition si el mismo seller tiene varias ciudades. |
| 23 | “Raw” significa poder volver a la entrada original | Convertir inmediatamente a parquet puede perder detalles. Guardar primero el payload original. |
| 24 | Lineage empieza en la ingesta, no en el dashboard | Batch ID, source ID, timestamp y raw path permiten explicar de dónde salió un dato. |
| 25 | Cerrar una fase no significa que el documento esté terminado para siempre | Una revisión de producto puede reabrir decisiones. Versionar y registrar reemplazos en vez de esconderlos. |
| 26 | El alcance de datos y el alcance de interfaz son cosas diferentes | Se puede modelar órdenes/ofertas para aprender DE sin construir pagos o frontend. |
| 27 | Las identidades de negocio no deben duplicarse por rol | Una tienda puede comprar y vender. `account` + roles evita duplicidad de identidad. |
| 28 | Un audit log necesita representar el cambio completo | `old_value/new_value` era insuficiente para una entidad multicolumna. Usar snapshot/payload validado. |
| 29 | Primero hechos, después scores | La fórmula de reputación comercial debe diseñarse después de tener órdenes, reviews y cancelaciones modeladas. |
| 30 | Instalar una herramienta no demuestra dominio de Data Engineering | Cada fase debe producir evidencia: idempotencia, backfill, tests, lineage, recovery o performance. |
| 31 | Una transacción necesita participantes explícitos en su grano | Si `sales_order` no identifica seller, reviews y revenue pueden quedar ambiguos. Una orden = buyer + seller. |
| 32 | Cambiar de fórmula según una condición puede crear saltos | Al pasar del test al historial, acertar la primera edición bajaba el puntaje de 27,0 a 5,3. Probar la transición, no solo los casos aislados. (Restaurada: se perdió en la revisión v2.) |
| 33 | Revisar el puntaje máximo alcanzable por cada tipo de usuario | Un contribuidor de comunidad tenía tope de 30 y nunca llegaba al umbral de 50. (Restaurada.) |
| 34 | Al corregir una exclusión, verificar que la solución no abra otra puerta | Renormalizar el puntaje de comunidad daba 100 puntos a un usuario nuevo solo por el test. (Restaurada.) |
| 35 | Una revisión que reescribe documentos puede borrar evidencia | La revisión v2 eliminó los casos de prueba verificados de las fórmulas y tres lecciones. Comparar contra la versión anterior antes de aceptar una reescritura. |
| 36 | Una clasificación ubicada en una tabla opcional deja filas sin clasificar | `buyer_type` en `business_profile` dejaba sin tipo a las cuentas individuales (`driver`). |
| 37 | Un trabajo largo debe poder retomarse sin rehacerlo | La investigación EE. UU. se cortó por el límite de sesión. Un archivo por ítem más `progress.json` permitió retomar solo lo pendiente. Diseñar los pipelines igual: checkpoint por unidad de trabajo, idempotente. |
| 38 | Una API pública puede cambiar sus requisitos de acceso | La Census API respondió "Missing Key" (2026-10-09). Tratar las credenciales, aunque sean gratuitas, como dependencia: secret en el entorno, nunca en el código ni en los logs. |
| 39 | Un resumen automático puede sumar mal | WebFetch sumó mal una consulta agrupada de NY (12.545.280); una segunda lectura cuadró con el `count(*)`. Verificar los totales con una consulta independiente antes de publicar. |
| 40 | Las series oficiales pueden tener huecos por causas externas | El CPI de BLS no tiene octubre 2025 ("lapse in appropriations"). Los tests de completitud deben permitir huecos documentados en vez de fallar o interpolar. |
| 41 | Una reclasificación de códigos rompe joins históricos | NAICS 2022 movió 441310→441330 y fusionó 811112/811113/811118 en 811114, mientras CBP 2023 sigue en NAICS 2017. Una dimensión de equivalencias (`dim_naics`) con edición y vigencia evita mezclar ediciones. |
| 42 | Unidades con el mismo nombre no siempre son comparables | "Establecimiento" en RUES (matrícula mercantil) no es igual a "establishment" en CBP (con nómina). Documentar la unidad antes de comparar países. |

## Formato para nuevas lecciones

Agregar una fila solamente cuando exista una observación concreta del proyecto.

Buena lección:

```text
Problema observado -> principio general -> acción para prevenirlo/repetirlo.
```

Evitar convertir opiniones no probadas en “lecciones aprendidas”.
