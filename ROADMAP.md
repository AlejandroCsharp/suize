# Roadmap

Mejoras previstas para Suize, ordenadas por prioridad. No hay fechas comprometidas: es una
lista de trabajo, no un calendario.

El estado actual del proyecto es funcional y estable: 202 tests, verificación de tipos en modo
estricto y una cobertura del 87 %. Lo que sigue son ampliaciones y refuerzos, no correcciones
pendientes.

Cada punto tiene su issue en GitHub con la etiqueta correspondiente.

## Prioridad alta

Lo que más cambia el uso diario o lo que más cuesta diagnosticar si falla.

- [x] **Opción `-Pn` para omitir el descubrimiento de hosts.** Resuelta: `-Pn`/`--no-ping` en
  `scan`, con sugerencia automática cuando ningún host responde y reintento ofrecido en el
  menú interactivo.
- [ ] **Tests de `config/settings.py`** (cobertura actual: 77 %, sin archivo de tests propio).
  Es el módulo con la lógica más delicada del proyecto: la precedencia entre `default.toml`,
  el archivo del usuario y las variables de entorno. Un error aquí produce comportamientos
  difíciles de rastrear, porque la configuración se aplica de forma silenciosa.
- [x] **Tablas de correlación configurables.** Resuelto: viven en `[correlation]` dentro del
  TOML y se combinan entrada por entrada con las del usuario. `core/correlator.py` las recibe
  como argumento, sin importar `config/`.

## Prioridad media

- [ ] **Cobertura de `ui/prompts.py`** (actual: 33 %, el módulo más bajo del proyecto). Las
  preguntas interactivas apenas se ejercitan. Se pueden probar simulando las respuestas de
  questionary, como ya hace `tests/integration/test_cli_smoke.py` con el menú.
- [ ] **Cobertura de `utils/permissions.py`** (actual: 51 %). La detección de root y de los
  grupos con acceso al journal determina los avisos que ve el usuario al arrancar.
- [ ] **Medición de cobertura en la CI.** Añadir `pytest-cov` a las dependencias de desarrollo
  y un umbral mínimo (`--cov-fail-under`) para que la cobertura no baje con el tiempo.
- [ ] **Escaneo UDP (`-sU`).** Deja fuera servicios relevantes como DNS, DHCP, SNMP y NTP.
  Requiere privilegios de root y es notablemente más lento, así que encaja mejor como perfil
  separado que como opción del escaneo normal.
- [ ] **Modo seguimiento (`journalctl -f`).** Ver los logs en vivo mientras se reproduce un
  problema, en lugar de consultarlos después.
- [ ] **Desactivar los iconos de la interfaz.** Una opción `--no-emoji` o una clave de
  configuración, para terminales sin una fuente que incluya esos símbolos.
- [ ] **Ganchos de `pre-commit`.** Ejecutar ruff y mypy antes de cada commit, para detectar los
  fallos en local y no en la CI.
- [x] **`CHANGELOG.md` y criterio de versionado.** Resuelto: changelog en formato Keep a
  Changelog, versionado semántico y proceso de publicación documentado en el README. Un test
  comprueba que la versión del código coincide con la última del changelog.
- [x] **IPv6 por nombre de host.** Resuelto: `nmap_runner.needs_ipv6` consulta el DNS cuando
  el objetivo es un nombre y añade `-6` si solo resuelve a IPv6.
- [x] **Exportación a CSV o a un archivo.** Resuelto: `--format {table,json,csv}` y
  `--output ARCHIVO` en ambos subcomandos.
- [x] **Paginador para salidas largas.** Resuelto: la salida va a `less` cuando no cabe en
  pantalla y hay terminal; `--no-pager` lo desactiva.
- [ ] **Workflow de publicación.** Que al crear una etiqueta `vX.Y.Z` se construya el wheel y
  se adjunte automáticamente a la release de GitHub.
- [x] **Autocompletado de shell.** Resuelto con scripts propios para zsh y bash en
  `completions/`, sin dependencias, con un test que comprueba que no se desincronicen del
  parser.
- [ ] **Capturas o grabación en el README.** Una animación del menú comunica la herramienta
  mejor que un bloque de texto.
- [ ] **Publicación en PyPI.** Permitiría instalarlo con `pipx install suize`. Conviene
  esperar a que la interfaz de línea de comandos se estabilice.
- [ ] **Traducción de los mensajes.** Los textos están fijados en español dentro del código.
  Solo tiene sentido si el proyecto se dirige a usuarios de otros idiomas.

## Fuera del alcance

Decisiones tomadas, no pendientes:

- **Correlación remota.** Suize consulta siempre el journal de la máquina local. Leer los logs
  de otro equipo exigiría SSH y gestión de credenciales, lo que cambiaría por completo el
  modelo de seguridad de la herramienta.
- **Interfaz web o gráfica.** El proyecto es deliberadamente una herramienta de terminal.
