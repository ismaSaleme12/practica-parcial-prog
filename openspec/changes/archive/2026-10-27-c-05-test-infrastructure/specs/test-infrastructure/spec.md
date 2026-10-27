# Spec Delta

## Purpose

Define el andén de pruebas automatizadas del proyecto: cómo se fija el entorno, cómo se prepara la base de test, cómo se restaura el estado conocido antes de cada test, cómo se ejercita la aplicación asincrónica y cómo se autentican los roles, todo dentro de `test/` y contra PostgreSQL real.

## ADDED Requirements

### Requirement: La suite se ejecuta desde la raíz del repositorio

Ejecutar `python -m pytest test/` desde la raíz SHALL recolectar los tests de `test/` y resolver `app`, `main` y `seed` desde la raíz del repositorio, sin variables de entorno ni pasos manuales previos.

#### Scenario: Los imports resuelven contra la raíz

- **WHEN** se corre `python -m pytest test/` (o `pytest test/`) desde la raíz del repo
- **THEN** `import app`, `import main` y `import seed` funcionan y los tests se recolectan sin errores de importación

#### Scenario: La configuración no cambia la estructura obligatoria de la raíz

- **WHEN** se inspecciona la raíz del repositorio
- **THEN** no hay archivos de configuración de pytest agregados allí y todas las piezas del andén (`pytest.ini`, `conftest.py`, `test_*.py`) viven dentro de `test/`

#### Scenario: El camino relativo equivocado falla de forma visible

- **WHEN** el `pythonpath` del andén apunta a `test/` en vez de a la raíz
- **THEN** el arranque falla con un error de importación en lugar de correr tests contra módulos equivocados

### Requirement: La base de test es propia y se prepara sola

La suite SHALL usar una base de datos distinta de la de desarrollo, crearla si no existe y aplicarle `alembic upgrade head` una sola vez por corrida; SHALL NOT crear tablas por otra vía ni escribir en la base de desarrollo.

#### Scenario: Base ausente

- **WHEN** la base de test no existe y se corre la suite
- **THEN** se crea, se migra con Alembic y los tests corren contra ella

#### Scenario: Base ya migrada

- **WHEN** la base de test existe y ya está en la última revisión
- **THEN** la preparación es un no-op y la corrida continúa sin recrear el esquema

#### Scenario: La base de desarrollo queda intacta

- **WHEN** la suite termina
- **THEN** `taller_mecanico` conserva sus tablas y sus datos, y la configuración de la aplicación dentro de los tests apunta a la base de test

#### Scenario: El esquema nace sólo de Alembic

- **WHEN** se prepara la base de test
- **THEN** las trece tablas, sus índices y los disparadores de sólo agregado provienen de las migraciones, nunca de `create_all`

### Requirement: Cada test arranca del estado conocido del seed

Antes de cada test SHALL restaurarse el estado inicial re-corriendo el seed (vaciar y recargar), de modo que ninguna prueba dependa de lo que hizo la anterior.

#### Scenario: Un test ensucia y el siguiente no lo ve

- **WHEN** un test modifica o borra datos y termina
- **THEN** el test siguiente encuentra los conteos y valores que deja el seed

#### Scenario: La restauración no choca con el sólo agregado

- **WHEN** se restaura el estado de las tablas de auditoría cuyos registros no se pueden borrar fila por fila
- **THEN** la restauración se completa sin violar la protección de sólo agregado

### Requirement: La aplicación se ejercita de forma asincrónica con su ciclo de vida

Las pruebas de extremo a extremo SHALL usar un cliente HTTP asincrónico contra la aplicación ASGI y SHALL ejecutar el ciclo de vida real de la aplicación, de modo que el motor de base de datos y la fábrica de sesiones existan durante la prueba y se liberen al terminar.

#### Scenario: Petición contra la app real

- **WHEN** un test pide un endpoint con el cliente del andén
- **THEN** la petición corre por el handler asincrónico real, con el motor creado por el ciclo de vida

#### Scenario: El ciclo de vida se cierra

- **WHEN** el test termina
- **THEN** el ciclo de vida de la aplicación se cierra y los recursos de base de datos se liberan

#### Scenario: No se agrega infraestructura de pruebas al stack

- **WHEN** se inspeccionan las dependencias declaradas y los imports del andén
- **THEN** sólo aparecen `pytest`, `pytest-asyncio` y `httpx` como agregados, sin `asgi-lifespan`, `factory-boy`, `respx`, sqlite, repositorios falsos ni contenedores

### Requirement: La autenticación se obtiene una vez por rol

El andén SHALL ofrecer un helper de inicio de sesión que devuelva la cookie `access_token` y fixtures listas para ADMIN, RECEPCION, MECANICO y CLIENTE, usando los usuarios del seed.

#### Scenario: Login devuelve la cookie

- **WHEN** el helper inicia sesión con un usuario del seed y su contraseña conocida
- **THEN** devuelve la cookie `access_token` y las peticiones siguientes del mismo cliente viajan autenticadas

#### Scenario: El token no viaja en el cuerpo

- **WHEN** se inicia sesión
- **THEN** el token se toma de la cookie, nunca de un header Authorization ni del cuerpo de la respuesta

#### Scenario: Fixtures por rol disponibles

- **WHEN** un test pide la fixture de un rol
- **THEN** obtiene una sesión iniciada con el usuario que el seed asigna a ese rol

### Requirement: Cobertura mínima del andén

El andén SHALL incluir las pruebas de salud del único endpoint existente: `GET /health/live` y `GET /health/ready` en sus dos resultados.

#### Scenario: Liveness

- **WHEN** se pide `GET /health/live`
- **THEN** responde 200 y no consulta la base

#### Scenario: Readiness con la base disponible

- **WHEN** se pide `GET /health/ready` contra PostgreSQL real
- **THEN** responde 200 e informa la base conectada

#### Scenario: Readiness con la base caída

- **WHEN** la base de datos no responde
- **THEN** responde 503
