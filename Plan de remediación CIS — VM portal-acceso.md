# Plan de remediación CIS — VM portal-acceso

Oct 7, 2026 · @Pablo

## Resumen ejecutivo

La VM de portal-acceso cumple hoy 5 de los 40 controles de la matriz CIS. Se propone cerrar la mayoría de las brechas en una ventana el **sábado 10 y domingo 11 de octubre de 2026**, con corte esperado del portal de solo 1 a 3 minutos (reinicio).

|Estado|Controles|Filas|
|-|-|-|
|Cumple|5|9, 15, 33, 39, 46|
|No aplica|1|45|
|Brecha confirmada|30|7, 8, 10–12, 16–20, 22–27, 29–32, 34–38, 40–44|
|Sin verificar (requiere sudo)|4|13, 14, 21, 28|

Al cierre del fin de semana se espera dejar en **Cumple** unas 30 filas y en **Excepción** documentada otras 5 (filas 14, 21, 32, 35 y 36). Quedan fuera tres temas que dependen de terceros: la dirección del SIEM (fila 26), los servidores NTP corporativos (fila 38) y la activación de Ubuntu Pro para el escaneo USG (fila 7).

Para ejecutar se necesita, antes del viernes 9 de octubre: aprobar el plan y la ventana, aprobar las 8 excepciones de la sección correspondiente, acceso sudo para el ejecutor y un snapshot de la VM en VMware.

## Alcance y contexto

El trabajo cubre solo el sistema operativo de la VM `iacdi`, que aloja portal-acceso; las aplicaciones no se modifican.

|Dato|Valor|
|-|-|
|Activo|VM `iacdi` en VMware, 192.168.10.20 (ens33)|
|Sistema|Ubuntu 26.04.1 LTS, kernel 7.0.0-34 (7.0.0-38 instalado, pendiente de reinicio)|
|Matriz|SGSI-ATI-D07-F01 Matriz Hardening CIS, hoja Ubuntu 24.04 (filas 7–46)|
|Perfil|L2 (L1 + L2), definido por el dueño del activo: SSO interno con credenciales y datos personales|
|Revisión|7 de octubre de 2026, solo lectura y sin sudo|

**Servicios expuestos hoy.** Desde la red local solo escuchan SSH (22) y nginx (80/443). netdata (19999) escucha solo en localhost y Tailscale; postfix solo en `\[::1]:25`. Las apps del portal, PostgreSQL y los contenedores Docker escuchan en 127.0.0.1.

**Versión de la hoja.** La matriz no tiene hoja para Ubuntu 26.04. Se usa la de 24.04 y se registra como excepción mientras SGSI no publique una hoja 26.04.

## Estado actual

Desde la revisión anterior (mañana del 7 de octubre) se cerró la exposición de postfix y netdata; el resto sigue igual.

**Avances ya aplicados**

* postfix: `inet\_interfaces = loopback-only`, solo escucha en `\[::1]:25` (fila 33).
* netdata: escucha solo en 127.0.0.1 y en la IP de Tailscale 100.82.24.75 (fila 33).
* Parches parciales: docker, docker-compose y tailscale actualizados a las 08:05 (fila 8).
* Reglas de ufw modificadas a las 08:55; el contenido no se pudo leer sin sudo (fila 14).

**Controles que ya cumplen**

|Fila|Control|Evidencia|
|-|-|-|
|9|Firmas GPG|Ningún `trusted=yes`; todas las fuentes usan `signed-by`|
|15|UID 0|Solo `root` (falta confirmar contraseñas vacías con sudo)|
|33|Servicios|Solo 22, 80 y 443 hacia la LAN; justificar netdata por Tailscale|
|39|Permisos de cuentas|passwd/group 644 root:root; shadow/gshadow 640 root:shadow|
|46|Wi-Fi y Bluetooth|Sin interfaces inalámbricas ni servicio bluetooth|

**Sin verificar por falta de sudo**

* Fila 13: estado de los perfiles AppArmor (`aa-status`). El módulo está cargado.
* Fila 14: reglas de ufw. Política entrante y reenvío en DROP; salida en ACCEPT.
* Fila 21: contenido de sudoers. No existe `/var/log/sudo.log`, así que casi seguro falta `logfile`.
* Fila 28: contraseña de GRUB. Los permisos de `grub.cfg` (600 root:root) ya cumplen.
* Filas 10–12 y 18: configuración SSH efectiva (`sshd -T`) y el contenido de `50-cloud-init.conf`.

## Brechas y acción por control

Las 30 brechas confirmadas se reparten en cuatro fases; tres quedan pendientes de datos externos y no se cierran este fin de semana.

|Fila|Control|Hallazgo (7 oct)|Acción|Fase|
|-|-|-|-|-|
|7|Escaneo USG|Ubuntu Pro sin activar, `usg` no instalado|`pro attach`, `apt install usg`, `usg audit` antes y después|Pendiente (token Pro)|
|8|Parches|4 paquetes (openssh, libmp3lame0) y reinicio por kernel 7.0.0-38|`apt upgrade` y reinicio|1|
|10–12, 18|SSH|Sin `50-cis.conf`; `X11Forwarding yes`; sin AllowGroups ni cifrados fuertes|Crear `50-cis.conf` con los valores de la matriz y grupo `sshusers`|2|
|16|pwquality|No configurado|`libpam-pwquality` + `50-cis.conf` (minlen 14, minclass 4)|2|
|17|faillock|No configurado|`deny = 5`, `unlock\_time = 900`, `even\_deny\_root` (L2)|2|
|19|Historial|Sin `remember`; `nullok` en `common-auth`|`remember = 24`; quitar `nullok`|2|
|20|Vigencia|MAX 99999, MIN 0, INACTIVE -1|`login.defs` 365/1/7, `useradd -D -f 45`, `chage` a cuentas humanas|1|
|21|sudo|Sin `/var/log/sudo.log`|`50-cis` con use\_pty, logfile, timestamp\_timeout=15|2|
|22|su|`pam\_wheel` comentado|Grupo vacío `sugroup` + `pam\_wheel`|1|
|23–25|auditd (L2)|No instalado|Instalar, `audit=1` en GRUB, reglas `50-cis.rules`, `auditd.conf` sin halt|3|
|26|Registros|Sin reenvío al SIEM; logs 644/664|Journald persistente y permisos 640 ahora; reenvío cuando haya SIEM|1 (parcial)|
|27|AIDE|No instalado|Instalar, `aideinit`, timer diario|3|
|29|Módulos L1|cramfs, freevxfs, hfs, hfsplus, jffs2, usb-storage cargables|`/etc/modprobe.d/cis.conf`|1|
|35|Módulos L2|`sctp` cargado; udf, rds, tipc cargables|Agregar a `cis.conf` (squashfs = excepción)|1|
|30|Montajes|/tmp y /dev/shm sin noexec; /var/tmp y /home sin opciones|noexec en /tmp y /dev/shm; bind-mount de /var/tmp|3|
|31|Core dumps|suid\_dumpable=2; core hard infinity|sysctl, `limits.d` y `coredump.conf`|1|
|32|Red|send\_redirects, secure\_redirects, log\_martians, accept\_ra fuera de valor|`60-cis-red.conf` sin tocar ip\_forward ni rp\_filter|1|
|34|apport|Habilitado|`enabled=0` y `mask`|1|
|36|Particiones (L2)|Sin /var, /var/log, /var/log/audit separados|Excepción; aplicar en plantillas nuevas|Excepción|
|37|Clientes inseguros|telnet, inetutils-telnet, ftp, tnftp|`apt purge`|1|
|38|Hora|chrony con servidores de Ubuntu|Cambiar a NTP corporativos cuando se tengan|Pendiente (NTP)|
|40|Permisos|73 archivos con escritura para todos en /home/iacdi|`chmod o-w`|1|
|41|Sesión|Sin TMOUT ni umask 027|`/etc/profile.d/50-cis.sh` y `UMASK 027`|2|
|42|Cuentas de sistema|`postgres` con /bin/bash|Cambiar a nologin si ninguna tarea lo usa|2|
|43|cron|crontab 644, carpetas 755, sin cron.allow|600/700 y `cron.allow`/`at.allow` con root e iacdi|1|
|44|Banners|Muestran "Ubuntu 26.04.1 LTS"; sin texto legal ni /etc/motd|Texto legal aprobado en los tres archivos|1|
|45|Interfaz gráfica|Sin escritorio; arranque en graphical.target|`systemctl set-default multi-user.target`|1|
|13|AppArmor|Sin verificar|`aa-status`; L2: pasar a enforce perfil por perfil|2|
|14|Firewall|Reglas sin verificar|Respaldar y revisar reglas; documentar salida permitida|0|
|28|GRUB|Contraseña sin verificar|Contraseña PBKDF2 con `--unrestricted`|3|

## Riesgos para portal-acceso y mitigaciones

Cinco cambios podrían dejar fuera al portal o a los administradores si se aplican tal como dice la matriz; con las mitigaciones de abajo el único corte esperado son los reinicios.

|Riesgo|Control|Efecto si se aplica tal cual|Mitigación|
|-|-|-|-|
|Alto|32 `ip\_forward = 0`|Los contenedores pierden red: caen /vlan-v2/ y /starlink-sync/|No se toca; excepción por host Docker|
|Alto|14 salida de ufw en deny|Se corta el SMTP a Office 365: sin recuperación de contraseña ni avisos|Salida permitida y documentada|
|Alto|14 rehacer reglas de ufw|Portal inaccesible si se pierden 80/443|Respaldo de `ufw status numbered`; 80 y 443 se mantienen|
|Alto|25 `disk\_full\_action = halt`|La VM se apaga si se llena el disco|Usar `syslog` o `suspend` + alerta de espacio|
|Alto|10–12 AllowGroups|Un administrador queda fuera por SSH|Agregar admins a `sshusers` antes; segunda sesión abierta; consola VMware a mano|
|Medio|21 quitar NOPASSWD (L2)|Rompe despliegues y `portal-acceso-restart`|Se mantiene en las 4 reglas de despliegue (excepción)|
|Medio|32 `rp\_filter = 1`|Puede cortar acceso por Tailscale|Se deja en 2 (excepción)|
|Medio|13 AppArmor en enforce|Puede bloquear nginx o node|Perfil por perfil, primero en complain|
|Medio|17 faillock|Bloqueo de un admin por intentos fallidos|`faillock --user <u> --reset` documentado|
|Bajo|8 y 23 reinicios|Corte de 1 a 3 minutos|Ventana; los servicios están habilitados y vuelven solos|
|Bajo|30 noexec en /tmp|Un `pip` o `npm install` en un despliegue podría fallar|Probar un despliegue el domingo; `TMPDIR` alterno si falla|
|Bajo|43 `cron.allow`|Tareas de cron de usuarios no listados dejan de correr|Incluir root e iacdi; revisar crontabs antes|

No afectan al portal: PAM y contraseñas (el portal usa su propia autenticación con PostgreSQL y TOTP), banners, apport, módulos del kernel, core dumps, AIDE, quitar telnet/ftp, permisos, TMOUT y umask. El timer `portal-acceso-health-check` reinicia cada 5 minutos la app que no responda.

## Excepciones que requieren aprobación

Se piden 8 excepciones; cada una se registra como **Excepción** en la columna J con su número aprobado y la justificación en la M.

|Fila|Control|Valor que se mantiene|Justificación|
|-|-|-|-|
|32|ip\_forward|1|Host Docker: /vlan-v2/ y /starlink-sync/ corren en contenedores|
|32|rp\_filter|2 (modo flexible)|Docker y Tailscale; el modo estricto corta tráfico asimétrico|
|35|Módulo squashfs|Habilitado|Lo requiere snapd|
|36|Particiones separadas (L2)|Un solo volumen lógico|Re-particionar exige reconstruir la VM; se aplica en plantillas nuevas|
|14|Salida de ufw|Permitida|Las apps envían correo a smtp.office365.com:25|
|21|NOPASSWD (L2)|En 4 reglas de despliegue|Despliegues y reinicios automáticos de las apps|
|33|netdata en Tailscale|Puerto 19999 solo por Tailscale|Monitoreo remoto del equipo; no expuesto a la LAN|
|Todas|Hoja de la matriz|Ubuntu 24.04 en VM 26.04.1|La matriz no tiene hoja para 26.04|

La fila 42 (`postgres` con /bin/bash) se corrige en vez de exceptuarse, salvo que se encuentre una tarea que use ese shell.

## Plan del fin de semana

El trabajo va de menor a mayor riesgo en cuatro fases; cada fase termina con una prueba del portal y solo se avanza si pasa.

\[embedded content: cronograma de la ventana · 6 bloques, 2 reinicios]

**Viernes 9 de octubre: preparación (sin corte)**

1. Aprobación del plan, ticket de cambio y aviso a usuarios de la ventana.
2. Habilitar sudo para el ejecutor y correr el script de evidencia: SSH efectivo, ufw, sudoers, GRUB, AppArmor y contraseñas vacías.
3. Revisar crontabs de usuarios y si alguna tarea usa la cuenta `postgres` con shell.
4. Dejar listos y revisados los scripts por fase. Respaldan cada archivo antes de cambiarlo y se pueden correr más de una vez.

**Sábado 10 de octubre**

1. **08:00 – Fase 0, respaldo.** Snapshot en VMware, `tar` de /etc, `ufw status numbered` guardado, consola VMware abierta y segunda sesión SSH.
2. **08:30 – Fase 1a, parches.** `apt upgrade` y reinicio al kernel 7.0.0-38 (corte de 1 a 3 minutos). Prueba del portal.
3. **10:00 – Fase 1b, bajo riesgo.** Filas 20, 22, 26 (parcial), 29, 31, 32 (sin ip\_forward ni rp\_filter), 34, 35, 37, 40, 43, 44 y 45. Prueba del portal.
4. **14:00 – Fase 2, riesgo medio.** SSH (10–12, 18), PAM (16, 17, 19), sudo (21), sesión (41), postgres (42) y AppArmor (13). Probar un nuevo login SSH antes de cerrar la sesión de respaldo. Prueba del portal.

**Domingo 11 de octubre**

1. **08:00 – Fase 3, cambios de arranque.** auditd con reglas y `auditd.conf` (23–25), contraseña de GRUB y `audit=1` (28), AIDE (27) y montajes (30). Un reinicio (corte de 1 a 3 minutos).
2. **11:00 – Validación completa.** Script de evidencia en las 40 filas, prueba de un despliegue (`\*-deploy`) y del correo a Office 365.
3. **13:00 – Registro.** Llenar columnas J–M en una copia de la matriz y cerrar el ticket.

**Lunes 12 de octubre:** revisar logs de auditd, AIDE y fallos de login; presentar el resultado a Boba.

Responsables: ejecutor técnico (a definir) y aprobador del cambio (Boba). Contacto de guardia para el portal durante la ventana: a definir.

## Plan de reversa

Cada cambio se revierte desde su respaldo en minutos; el snapshot de VMware queda como último recurso y se borra el viernes 16 de octubre si no hubo problemas.

**Criterios para revertir** (cualquiera de ellos, en la prueba del portal tras cada fase):

* El portal no responde en 443 o falla el login con TOTP.
* No sale correo hacia Office 365 (recuperación de contraseña).
* Cae una app o contenedor y el health-check no lo levanta en 10 minutos.
* Un administrador no puede entrar por SSH ni usar sudo.

|Situación|Reversa|Tiempo|
|-|-|-|
|Falla tras un cambio de configuración|Restaurar el archivo desde `/root/cis-respaldo/<fecha>/` y recargar el servicio|< 5 min|
|Sin acceso SSH|Entrar por la consola VMware y quitar `50-cis.conf`|< 10 min|
|Bloqueo por faillock|`faillock --user <u> --reset` desde consola o la sesión abierta|< 2 min|
|AppArmor bloquea nginx o node|`aa-complain` sobre ese perfil|< 2 min|
|La VM no arranca tras la Fase 3|Elegir el kernel anterior en GRUB (contraseña en bóveda) o revertir el snapshot|10–30 min|
|Falla general sin causa clara|Revertir al snapshot del sábado 08:00|15–30 min|

La contraseña de GRUB se guarda en la bóveda antes del reinicio del domingo; sin ella no se puede editar el arranque desde consola.

## Validación y registro de evidencia

El cumplimiento formal se logra solo cuando las columnas J–M de las 40 filas quedan llenas con evidencia; hoy están vacías.

**Prueba del portal tras cada fase**

* \[ ] Login en portal-acceso con usuario y TOTP
* \[ ] Correo de recuperación de contraseña recibido
* \[ ] Rutas /vlan-v2/, /starlink-sync/ y /mde/ responden
* \[ ] `systemctl --failed` sin unidades caídas
* \[ ] Nuevo login SSH y `sudo -v` de un administrador

**Registro en la matriz** (copia de SGSI-ATI-D07-F01, hoja Ubuntu 24.04):

|Columna|Qué se registra|
|-|-|
|J Estado|Cumple, No cumple, Excepción o No aplica|
|K Responsable|Ejecutor técnico que validó|
|L Fecha de revisión|11/10/2026|
|M Evidencia|Salida del comando de la columna G, archivada en `/root/cis-evidencia/`; número de excepción y justificación cuando corresponda|

El script de evidencia guarda la salida de cada validación en un archivo por fila. Cuando se active Ubuntu Pro, el reporte HTML de `usg audit` se suma como evidencia de la fila 7.

## Decisiones y aprobaciones pendientes

Sin los cinco primeros puntos no se puede ejecutar el sábado; los demás se pueden cerrar después.

**Antes del viernes 9 de octubre**

* \[ ] Aprobar el plan y la ventana del 10 y 11 de octubre (Boba)
* \[ ] Aprobar las 8 excepciones y asignar sus números
* \[ ] Definir ejecutor técnico y contacto de guardia
* \[ ] Dar sudo al ejecutor y acceso a la consola VMware
* \[ ] Aprobar el texto legal para los banners (fila 44)
* \[ ] Confirmar quiénes son administradores SSH (grupo `sshusers`)
* \[ ] Confirmar si se entra al portal por Tailscale

**Después del fin de semana**

* \[ ] Dirección y puerto del SIEM corporativo (fila 26)
* \[ ] Servidores NTP corporativos (fila 38)
* \[ ] Token de Ubuntu Pro para el escaneo USG (fila 7)
* \[ ] Hoja de la matriz para Ubuntu 26.04, o aprobación formal de usar la de 24.04 (SGSI)

