# delivery-evidence Specification

## Purpose
Define la **entrega** del TP como un artefacto verificable: cada caso C-01 a C-19 tiene evidencia ejecutable y localizable, la matriz de paridad la enlaza con su prueba automatizada, y la entrega se comprueba de punta a punta con un procedimiento reproducible (suite, ciclo Alembic sobre base vacía, seed idempotente y ausencia de credenciales en el repositorio). El objetivo es que un corrector pueda abrir `test/`, encontrar el caso que busca y volver a correr la evidencia sin leer el código.

## Requirements

### Requirement: Cada caso C-01 a C-19 tiene evidencia ejecutable localizable

La carpeta `test/` SHALL contener evidencia ejecutable para los 19 casos de la consigna: bloques `.http` con la petición, el código y el cuerpo esperado en comentarios, y `test/solo_agregado.sql` para el caso C-14. La evidencia MUST NOT duplicar bloques que ya existen: se agrega sólo lo que falta y la matriz referencia el archivo y el bloque donde vive cada caso.

#### Scenario: Evidencia HTTP de un caso

- **WHEN** se busca el caso C-02 en `test/`
- **THEN** `test/auth.http` tiene un bloque ejecutable con la petición y la respuesta esperada (`409` + mensaje propio) en comentarios, y la matriz lo referencia

#### Scenario: Caso que no se demuestra sólo con HTTP

- **WHEN** un caso requiere un paso previo (C-09: vaciar el catálogo por psql; C-15: contar consultas con `SQL_ECHO`) o no pasa por HTTP (C-14)
- **THEN** la evidencia incluye el comando previo y la salida esperada en comentarios, y la matriz dice explícitamente qué parte cubre el `.http`/`.sql` y qué parte la prueba automatizada

#### Scenario: Evidencia sin cookie no concluyente

- **WHEN** un bloque afirma que `Authorization: Bearer` no autentica (C-03)
- **THEN** el bloque indica que hay que llegar sin cookie, porque con la cookie del login la respuesta correcta es 200 y el bloque no probaría nada

### Requirement: La matriz de paridad enlaza cada caso con su evidencia y su prueba

`test/MATRIZ_CASOS.md` SHALL listar los 19 casos con las columnas **Caso | Qué verifica | Evidencia `.http` (archivo + bloque) | Prueba pytest (archivo::test) | Estado**, y MUST NOT dejar celdas vacías: un caso sin `.http` o sin test se justifica en el mismo documento.

#### Scenario: Los 19 casos están en la matriz

- **WHEN** se revisa `test/MATRIZ_CASOS.md`
- **THEN** están las 19 filas C-01..C-19, cada una con al menos un archivo de evidencia y al menos un test (o la justificación de por qué no aplica)

#### Scenario: Caso C-14

- **WHEN** se busca C-14 en la matriz
- **THEN** la evidencia apunta a `test/solo_agregado.sql` (bloques 1/6 a 6/6 y el `INSERT` con la FK) y la prueba a `test/test_solo_agregado.py`, con la nota de que no existe `.http` porque el disparador se demuestra en la base

#### Scenario: Caso C-15

- **WHEN** se busca C-15 en la matriz
- **THEN** la evidencia apunta al bloque con `SQL_ECHO` de `test/ordenes.http` y la prueba a `test/test_detalle.py::test_c15_detalle_mantiene_el_conteo_con_2_y_4_items`

### Requirement: La matriz incluye el checklist de los 8 criterios de evaluación

`test/MATRIZ_CASOS.md` SHALL reproducir los ocho criterios de `knowledge-base/01_vision_y_objetivos.md` §Métricas de éxito con su peso, el lugar donde se cumple y el comando o test con el que se verificó.

#### Scenario: Criterio con evidencia

- **WHEN** se revisa el checklist
- **THEN** cada uno de los ocho criterios (8 %, 14 %, 10 %, 16 %, 14 %, 20 %, 10 %, 8 %) tiene al menos un archivo o sección y un test o comando asociado

#### Scenario: Condición dura de arranque

- **WHEN** se revisa el criterio de proyecto, configuración y ciclo de vida
- **THEN** menciona la condición dura (levanta, crea el esquema con `alembic upgrade head` sobre base vacía y no contiene credenciales reales) y cómo se comprobó

### Requirement: La entrega se verifica de punta a punta

La entrega SHALL verificarse con: la suite completa en verde contra PostgreSQL real, el ciclo `alembic upgrade head → downgrade base → upgrade head` sobre una base **vacía y descartable**, `seed.py` corrido dos veces con los mismos conteos, y la comprobación de que `SECRET_KEY` y `POSTGRES_PASSWORD` son obligatorios y que el repositorio no versiona credenciales.

#### Scenario: Suite completa

- **WHEN** se ejecuta `python -m pytest test/ -q` desde la raíz
- **THEN** todos los tests pasan y el total incluye los tests previos más los de esta entrega (207)

#### Scenario: Esquema desde cero

- **WHEN** se crea una base vacía y se corre `alembic upgrade head`, luego `alembic downgrade base` y luego `alembic upgrade head`
- **THEN** los tres comandos terminan con código 0, la base queda en la revisión `0002` con 13 tablas de dominio y 3 disparadores de sólo agregado

#### Scenario: Seed reproducible

- **WHEN** se corre `python seed.py` dos veces sobre la misma base
- **THEN** los conteos de las trece tablas son idénticos en ambas corridas (no duplica filas ni deja residuos)

#### Scenario: Sin secretos por defecto

- **WHEN** se inspeccionan `Settings` y el repositorio
- **THEN** `SECRET_KEY` y `POSTGRES_PASSWORD` son obligatorios (instanciar sin entorno ni `.env` produce un `ValidationError` con dos errores), `.env` está ignorado por git y `git ls-files` no incluye `.env`, claves ni credenciales
