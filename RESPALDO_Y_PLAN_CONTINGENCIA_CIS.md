# Respaldo Preventivo y Plan de Contingencia — App LTI

**Fecha:** 7 de octubre de 2026  
**Motivo:** Plan de Remediación y Hardening CIS en la máquina virtual `iacdi` (Ubuntu 26.04) programado para el fin de semana del 10 y 11 de octubre de 2026.  
**Ubicación de respaldos locales:** `backups_iacdi/`

---

## 1. Detalle del Respaldo Generado

Se generó un respaldo comprimido de los componentes críticos directamente desde la instancia de producción en el servidor `iacdi`:

- **Archivo:** `backups_iacdi/backup_iacdi_app_lti_20261007_112323.tar.gz`
- **Tamaño aproximado:** ~280 KB
- **Contenido incluido:**
  - `.env` de producción (incluye variables de conexión MSSQL `192.168.10.6`, claves JWT de SSO, flags de entorno).
  - `backend/` (código fuente completo de la API FastAPI y automatización de tickets).
  - `frontend/` (interfaz web, vistas, estilos y scripts).
  - `deploy/` (unidad de servicio systemd `app-lti.service`, scripts de instalación y rollback).

---

## 2. Procedimiento de Restauración Rápida

Si durante o después de la ventana de mantenimiento ocurre una falla en el servidor `iacdi`, seguir según el caso:

### Caso A: El servicio `app-lti` no inicia o se caen archivos
1. **Revisar logs del servicio:**
   ```bash
   ssh iacdi "journalctl -u app-lti -n 50 --no-pager"
   ```
2. **Re-sincronizar el código desde el equipo de desarrollo:**
   ```bash
   bash deploy_to_iacdi.sh
   ssh iacdi "sudo systemctl restart app-lti"
   ```
3. **Restaurar el `.env` o código desde el archivo de respaldo (si se borraron o corrompieron):**
   ```bash
   scp backups_iacdi/backup_iacdi_app_lti_20261007_112323.tar.gz iacdi:/tmp/
   ssh iacdi "tar -xzvf /tmp/backup_iacdi_app_lti_20261007_112323.tar.gz -C /home/iacdi/Desarrollos/app-lti/"
   ssh iacdi "sudo systemctl restart app-lti"
   ```

### Caso B: Problemas de permisos con systemd / sandbox tras aplicar CIS
Si los controles de hardening del sistema impiden que el servicio `app-lti` funcione como usuario `iacdi`:
```bash
ssh iacdi "sudo bash /home/iacdi/Desarrollos/app-lti/deploy/rollback-app-lti.sh"
```
*(Esto reactiva el proceso transitorio manual en `0.0.0.0:8000` mientras se investiga el bloqueo).*

### Caso C: Caída general de la máquina virtual o inaccesibilidad de red
Solicitar al administrador de VMware la restauración del **Snapshot tomado el sábado 10 de octubre a las 08:00 AM** (Fase 0 del plan CIS).

---

## 3. Comandos para el Grupo `sshusers` (Acceso SSH)

En las Fases 1b y 2 del plan CIS (filas 10–12 y 18), se configurará `AllowGroups sshusers` en `/etc/ssh/sshd_config.d/50-cis.conf`. Si un usuario no está en ese grupo, **será expulsado y no podrá volver a conectarse por SSH**.

### 3.1 Verificar si el grupo existe
```bash
ssh iacdi "getent group sshusers"
```
*(Si no devuelve nada, el grupo aún no ha sido creado en el servidor).*

### 3.2 Crear el grupo y agregar al usuario `bobbasystem`
El ejecutor o administrador con permisos `sudo` debe correr en `iacdi`:
```bash
# 1. Crear el grupo sshusers (si no existe)
sudo groupadd -f sshusers

# 2. Agregar a bobbasystem al grupo
sudo usermod -aG sshusers bobbasystem

# 3. (Opcional) Agregar también a otros administradores o usuarios necesarios (ej: iacdi)
sudo usermod -aG sshusers iacdi
```

### 3.3 Confirmar que `bobbasystem` ya pertenece a `sshusers`
Desde tu terminal local puedes verificarlo ejecutando:
```bash
ssh iacdi "id -Gn bobbasystem"
```
**Resultado esperado:** debe incluir `sshusers` en la lista (por ejemplo: `bobbasystem sudo users apps-edit sshusers`).

> **Nota Crítica:** Asegurarse de pertenecer a `sshusers` **antes** de que el ejecutor aplique `systemctl restart ssh` o `systemctl reload ssh`.
