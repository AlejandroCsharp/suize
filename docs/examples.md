# Ejemplos de uso

Salidas reales de Suize (sin colores, terminal de 92 columnas). Los resultados de escaneo y
de logs provienen de los fixtures del proyecto (`tests/fixtures/`), así que puedes
reproducirlos con los tests o comparar con lo que ves en tu máquina.

- [Menú interactivo](#menú-interactivo)
- [Escaneos](#escaneos)
- [Logs](#logs)
- [Correlación](#correlación)
- [Salida JSON y jq](#salida-json-y-jq)
- [Errores y avisos](#errores-y-avisos)
- [Recetas](#recetas)

## Menú interactivo

```
$ suize
╭────────────────────────────────────────────────╮
│  Suize v0.1.0                                  │
│  Navaja suiza de terminal · Nmap + journalctl  │
╰────────────────────────────────────────────────╯
? ¿Qué quieres hacer? (Use arrow keys)
```

Debajo de la pregunta aparecen las cuatro opciones: *Escanear host con Nmap*, *Analizar logs
del sistema*, *Escanear + ver logs correlacionados* y *Salir*. Si falta una dependencia, Suize lo avisa en un panel al arrancar y deshabilita solo las
opciones que la necesitan; el resto del menú sigue disponible.

### Analizar logs

Cada pregunta tiene un valor por defecto, así que con `Enter` repetido obtienes "todo lo de la
última hora":

```
? Rango temporal: Última hora
? Prioridad: 3 · err  (incluye 0-3)
? Unidad systemd (vacío = todas, Tab para autocompletar): ssh.service
? Buscar texto (expresión regular, vacío = sin filtro):
? Número máximo de entradas: 200
```

Con **Personalizado (fecha exacta)** se piden dos fechas:

```
? Rango temporal: Personalizado (fecha exacta)
? Desde (AAAA-MM-DD, AAAA-MM-DD HH:MM o AAAA-MM-DD HH:MM:SS): 2026-01-15 08:00
? Hasta (vacío = ahora): 2026-01-15 09:30
```

Las respuestas se validan mientras escribes: una fecha mal formada o una unidad con caracteres
inválidos no te deja avanzar.

### Escanear

```
? Objetivo (IP, hostname, red CIDR o rango): 127.0.0.1
? Tipo de escaneo: Estándar: los 1000 puertos más comunes
⠋ Escaneando 127.0.0.1 con Nmap… (Ctrl+C para cancelar)
```

Tras la tabla de puertos, si hay alguno abierto:

```
? ¿Ver los logs de los servicios detectados? (y/N)
```

`Ctrl+C` en cualquier pregunta o durante el escaneo cancela esa operación y vuelve al menú.

## Escaneos

```
$ suize scan 192.168.1.0/24
127.0.0.1  localhost
╭────────┬───────────┬────────┬──────────┬─────────────────────────────────────────────────╮
│ Puerto │ Protocolo │ Estado │ Servicio │ Versión                                         │
├────────┼───────────┼────────┼──────────┼─────────────────────────────────────────────────┤
│     22 │ tcp       │ open   │ ssh      │ OpenSSH 9.6p1 Ubuntu 3ubuntu13.5 (Ubuntu Linux; │
│        │           │        │          │ protocol 2.0)                                   │
│     80 │ tcp       │ open   │ http     │ nginx 1.24.0 (Ubuntu)                           │
│   3306 │ tcp       │ open   │ mysql    │ MySQL 8.0.36-0ubuntu0.24.04.1                   │
╰────────┴───────────┴────────┴──────────┴─────────────────────────────────────────────────╯
192.168.1.20  router.lan  MAC AA:BB:CC:11:22:33
╭────────┬───────────┬────────┬──────────┬─────────────────╮
│ Puerto │ Protocolo │ Estado │ Servicio │ Versión         │
├────────┼───────────┼────────┼──────────┼─────────────────┤
│     53 │ tcp       │ open   │ domain   │ dnsmasq 2.90    │
│    443 │ tcp       │ open   │ ssl/http │ lighttpd 1.4.76 │
│   9100 │ tcp       │ open   │ —        │ —               │
╰────────┴───────────┴────────┴──────────┴─────────────────╯
  192.168.1.30: down
```

La MAC solo aparece si Nmap corre como root y el host está en tu red local. Un `—` significa
que Nmap no pudo identificar el servicio o su versión.

### Perfiles

| Perfil     | Opción de Nmap | Puertos           | Cuándo usarlo                          |
|------------|----------------|-------------------|----------------------------------------|
| `fast`     | `-F`           | 100 más comunes   | redes enteras, primer vistazo          |
| `standard` | —              | 1000 más comunes  | un host concreto (por defecto)         |
| `full`     | `-p-`          | los 65535 TCP     | auditoría a fondo; puede tardar mucho  |

```bash
suize scan 192.168.1.0/24 --profile fast
suize scan 192.168.1.1-50                  # rango en formato de Nmap
suize scan servidor.lan --profile full --save-xml servidor.xml
```

Con `--save-xml` se guarda el XML original de Nmap, útil para abrirlo luego con otras
herramientas (`xsltproc`, Zenmap, etc.).

## Logs

```
$ suize logs --since 24h
╭───────────────────────────── Resumen ──────────────────────────────╮
│ Total: 10 entradas   ·   2026-01-15 10:30:00 → 2026-01-15 10:34:30 │
│ Filtro temporal: Últimas 24 horas (2026-01-14 10:40:00 → ahora)    │
│                                                                    │
│ Prioridad  Nº                              Top unidades   Nº       │
│  CRIT       1  █████                       ssh.service     3       │
│  ERR        1  █████                       nginx.service   2       │
│  WARN       1  █████                       kernel          1       │
│  NOTICE     1  █████                       cron.service    1       │
│  INFO       5  ████████████████████████    backup-script   1       │
│  DEBUG      1  █████                                               │
╰────────────────────────────────────────────────────────────────────╯

  Fecha y hora          Prioridad   Unidad                     Mensaje
 ──────────────────────────────────────────────────────────────────────────────────────────
  2026-01-15 10:30:00    INFO       ssh.service                Server listening on 0.0.0.0
                                                               port 22.
  2026-01-15 10:30:30    NOTICE     ssh.service                Failed password for invalid
                                                               user admin from
                                                               203.0.113.45 port 51234
                                                               ssh2
  2026-01-15 10:31:00    ERR        nginx.service              2026/01/15 10:31:00 [emerg]
                                                               1201#1201: bind() to
                                                               0.0.0.0:80 failed (98:
                                                               Address already in use)
  2026-01-15 10:32:00    WARN       kernel                     usb 1-1: device descriptor
                                                               read/64, error -71
  2026-01-15 10:33:30    CRIT       systemd-coredump@0-3050…   Process 3044 (python3) of
                                                               user 1000 dumped core.
  ...
```

En la terminal, cada prioridad tiene su color: `EMERG`/`ALERT` en blanco sobre rojo, `CRIT` en
rojo intenso, `ERR` en rojo, `WARN` en amarillo, `NOTICE` en cian, `INFO` en verde y `DEBUG`
atenuado. Los mensajes graves (0-4) también se colorean para que resalten al hacer scroll.

La unidad sale de `_SYSTEMD_UNIT`; si la entrada no viene de un servicio (el kernel o un script
que usa `logger`), se muestra su `SYSLOG_IDENTIFIER`, como `kernel` o `backup-script`.

### Filtros combinables

Todos los filtros se suman (AND), igual que en journalctl:

```bash
suize logs -u ssh -p warning --since today          # SSH, warning o más grave, hoy
suize logs -u nginx -u php8.3-fpm --since 1h        # varias unidades a la vez
suize logs -p 0..3 --since 7d                       # solo emerg, alert, crit y err
suize logs -g "Failed password|Invalid user" -u ssh --since 24h
suize logs --since "2026-01-15 08:00" --until "2026-01-15 09:30"
suize logs -n 1000 --since yesterday
```

`-u ssh` equivale a `-u ssh.service`: journalctl completa el sufijo solo.

### Cómo se traducen los rangos

Suize resuelve los presets a fechas absolutas en el momento de la consulta. Si ahora fueran las
`2026-01-15 10:40`:

| `--since`                    | Se muestra como                                      | Se le pasa a journalctl                                        |
|------------------------------|------------------------------------------------------|----------------------------------------------------------------|
| `15m`                        | Últimos 15 minutos (2026-01-15 10:25:00 → ahora)     | `--since=2026-01-15 10:25:00`                                  |
| `1h`                         | Última hora (2026-01-15 09:40:00 → ahora)            | `--since=2026-01-15 09:40:00`                                  |
| `today` / `hoy`              | Hoy (2026-01-15 00:00:00 → ahora)                    | `--since=2026-01-15 00:00:00`                                  |
| `yesterday` / `ayer`         | Ayer (2026-01-14 00:00:00 → 2026-01-15 00:00:00)     | `--since=2026-01-14 00:00:00 --until=2026-01-15 00:00:00`      |
| `2d`                         | Últimos 2d (2026-01-13 10:40:00 → ahora)             | `--since=2026-01-13 10:40:00`                                  |
| `"2026-01-15 08:00"` + `--until "2026-01-15 09:30"` | Personalizado (2026-01-15 08:00:00 → 2026-01-15 09:30:00) | `--since=… --until=…` |

Sin `--since` no hay filtro temporal: se muestran las últimas `-n` entradas (200 por defecto).

## Correlación

La correlación responde a la pregunta: *"veo el puerto 80 abierto, ¿qué dicen los logs del
servicio que lo atiende?"*

```
$ suize scan 127.0.0.1 --correlate --since 6h
...tabla de puertos...

╭───────────┬──────────┬──────────┬───────────────────────┬──────────────────────────╮
│ Host      │   Puerto │ Servicio │ Candidatos            │ Unidades en este sistema │
├───────────┼──────────┼──────────┼───────────────────────┼──────────────────────────┤
│ 127.0.0.1 │   22/tcp │ ssh      │ ssh, sshd             │ ssh                      │
│ 127.0.0.1 │   80/tcp │ http     │ nginx, apache2, httpd │ nginx                    │
│ 127.0.0.1 │ 3306/tcp │ mysql    │ mysql, mariadb        │ — ninguna —              │
╰───────────┴──────────┴──────────┴───────────────────────┴──────────────────────────╯
╭──── Resumen ────╮
...
...tabla de logs de nginx.service y ssh.service...
```

Cómo leer la tabla:

- **Candidatos**: las unidades que *podrían* atender ese puerto, según el número de puerto y el
  nombre del servicio que detectó Nmap. Por eso SSH en el puerto 2222 también se correlaciona.
- **Unidades en este sistema**: las candidatas que existen de verdad en `systemctl list-units`.
  Solo estas se consultan en journalctl.
- **— ninguna —**: el servicio existe en la red, pero no hay una unidad con ese nombre. En el
  ejemplo, MySQL podría estar corriendo en un contenedor Docker, cuyos logs no están en el
  journal del host (se ven con `docker logs`).

Si el objetivo no es `127.0.0.1`/`localhost`, Suize avisa:

```
Los logs que se muestran son los de ESTA máquina. Si el objetivo es otro equipo, la
correlación solo es orientativa.
```

## Salida JSON y jq

`--json` imprime JSON por stdout (los avisos van a stderr), ideal para scripts. A diferencia
de la tabla, `ports` incluye **todos** los puertos que reportó Nmap, también los `closed` o
`filtered`; filtra con `select(.state == "open")` si solo te interesan los abiertos.

```bash
$ suize scan 127.0.0.1 --json -q | jq '.hosts[0]'      # (abreviado)
{
  "address": "127.0.0.1",
  "address_type": "ipv4",
  "hostnames": ["localhost"],
  "status": "up",
  "mac": "",
  "ports": [
    {
      "number": 22,
      "protocol": "tcp",
      "state": "open",
      "service": "ssh",
      "product": "OpenSSH",
      "version": "9.6p1 Ubuntu 3ubuntu13.5",
      "extra_info": "Ubuntu Linux; protocol 2.0"
    },
    ...
  ]
}
```

Con `--correlate`, el objeto trae además `correlations`, `units`, `logs` y `error` (este último
en `null` si la correlación funcionó).

```bash
$ suize logs --since 24h --json -q | jq '.summary'     # (compactado)
{
  "total": 10,
  "by_priority": { "2": 1, "3": 1, "4": 1, "5": 1, "6": 5, "7": 1 },
  "top_units": [["ssh.service", 3], ["nginx.service", 2], ["kernel", 1]],
  "first": "2026-01-15T10:30:00.123456",
  "last": "2026-01-15T10:34:30"
}
```

Cada entrada de `.entries`:

```json
{
  "timestamp": "2026-01-15T10:31:00",
  "priority": 3,
  "unit": "nginx.service",
  "message": "2026/01/15 10:31:00 [emerg] 1201#1201: bind() to 0.0.0.0:80 failed (98: Address already in use)",
  "hostname": "suize-lab",
  "pid": 1201,
  "priority_name": "err"
}
```

Consultas útiles:

```bash
# Puertos abiertos en formato "puerto servicio producto"
suize scan 192.168.1.0/24 --json -q \
  | jq -r '.hosts[] | .address as $ip | .ports[] | select(.state == "open")
           | "\($ip):\(.number) \(.service) \(.product)"'

# Solo mensajes de error, uno por línea
suize logs -p err --since today --json -q | jq -r '.entries[] | "\(.timestamp) \(.unit): \(.message)"'

# IPs que fallaron el login SSH, ordenadas por cantidad
suize logs -u ssh -g "Failed password" --since 24h -n 5000 --json -q \
  | jq -r '.entries[].message' | grep -oE 'from [0-9.]+' | sort | uniq -c | sort -rn
```

## Errores y avisos

Suize valida antes de ejecutar nada y responde con códigos de salida distintos según el caso.
En la terminal, cada mensaje va precedido de un símbolo y un color que indican su tipo (error,
aviso o información); en los ejemplos se muestra solo el texto.

```
$ suize logs -p banana
Prioridad inválida: 'banana'. Usa 0-7 o un nombre: emerg, alert, crit, err,
warning, notice, info, debug.
$ echo $?
2
```

```
$ suize scan "-oN /etc/passwd"
El objetivo no puede empezar por '-' (Nmap lo tomaría como una opción).
$ echo $?
2
```

```
$ suize scan 127.0.0.1           # con nmap sin instalar
╭───────────────────────────── Dependencias ─────────────────────────────╮
│ nmap no está instalado: se necesita para escanear hosts.               │
│    sudo apt install nmap · sudo dnf install nmap · sudo pacman -S nmap │
╰────────────────────────────────────────────────────────────────────────╯
$ echo $?
3
```

```
$ suize logs --since 1h          # en WSL sin systemd o en un contenedor
systemd no está en ejecución (¿WSL sin systemd o un contenedor?): journalctl no tendrá
logs y la correlación no podrá listar servicios. En WSL2 activa systemd en /etc/wsl.conf
(sección [boot], systemd=true) y ejecuta 'wsl --shutdown'.
No hay entradas de log para esos filtros.
```

| Código | Significado                                           |
|--------|-------------------------------------------------------|
| `0`    | todo bien                                             |
| `1`    | error al ejecutar (Nmap falló, timeout, XML inválido) |
| `2`    | uso o configuración inválidos                         |
| `3`    | falta una dependencia necesaria                       |
| `130`  | interrumpido con `Ctrl+C`                             |

`-q` oculta los avisos informativos (permisos, systemd), pero nunca los errores.

## Recetas

**Chequeo rápido de un servidor recién configurado:**

```bash
suize scan 127.0.0.1 --correlate --since 15m
```

**Revisión diaria de errores:**

```bash
suize logs -p err --since yesterday
```

**Alerta simple desde cron** (cron no tiene terminal, así que se usa un subcomando). Cron no
admite partir líneas con `\`, por eso la lógica va en un script:

```bash
#!/usr/bin/env bash
# /usr/local/bin/suize-criticos — guarda los logs críticos de la última hora, si los hubo
set -euo pipefail
if suize logs -p crit --since 1h --json -q | jq -e '.summary.total > 0' >/dev/null; then
    suize logs -p crit --since 1h --no-color >> /var/log/suize-criticos.log
fi
```

```
# /etc/cron.d/suize-criticos (cada hora, en punto)
0 * * * * root /usr/local/bin/suize-criticos
```

**Comparar dos escaneos** (por ejemplo, antes y después de cambiar el firewall):

```bash
suize scan 192.168.1.10 --json -q | jq -S '[.hosts[].ports[] | select(.state == "open") | {number, service}]' > antes.json
# ...cambios...
suize scan 192.168.1.10 --json -q | jq -S '[.hosts[].ports[] | select(.state == "open") | {number, service}]' > despues.json
diff antes.json despues.json
```

**Configuración propia para tu red** (`~/.config/suize/config.toml`):

```toml
[scan]
default_target = "192.168.1.0/24"
profile = "fast"

[logs]
default_time_preset = "today"
lines = 500
```
