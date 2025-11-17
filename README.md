# Widget de Tasa BCV (BCV Tasa USD)

Esta guía detalla la instalación, creación del ejecutable y configuración de autoarranque para el monitor de la tasa de cambio oficial del Dólar (USD) publicado por el Banco Central de Venezuela (BCV).

## Características principales

- Flotante y siempre visible (topmost).
- Actualiza al inicio y automáticamente (por defecto a las 05:00 y 13:00 — configurable en el código).
- Guarda historiales en SQLite (rate_bcv.db) para calcular diferencias (Alza ↑ / Baja ↓).
- Manejo de errores: ante fallas muestra la última tasa válida almacenada.

---

## 1. Dependencias (requirements.txt)

Contenido sugerido para `requirements.txt`:

```text
requests
beautifulsoup4
pyinstaller
urllib3
```

---

## 2. Entorno virtual e instalación

Se recomienda usar un entorno virtual para aislar dependencias.

Paso 1 — Crear el entorno virtual:

```bash
virtualenv venv
```

Paso 2 — Activar el entorno virtual:

Linux / macOS:

```bash
source venv/bin/activate
```

Windows (PowerShell o CMD):

```bash
.\venv\Scripts\activate
```

Paso 3 — Instalar dependencias:

```bash
pip install -r requirements.txt
```

---

## 3. Crear ejecutable con PyInstaller

Asegúrate de que el script principal se llame `main.py` y que el entorno virtual esté activado.

Compilar en una sola pieza sin consola:

Linux / macOS:

```bash
pyinstaller --onefile src/main.py
```

Windows (sin consola):

```bash
pyinstaller --onefile --noconsole src/main.py
```

El ejecutable resultante se ubicará en la carpeta `dist/`.

---

## 4. Autoarranque (inicio automático)

### 4.1 Windows

1. Copia `main.exe` a una ubicación permanente, por ejemplo:
   - C:\Program Files\TasaBCV\main.exe
2. Crea un acceso directo al ejecutable.
3. Abre la carpeta de inicio:
```bash
# Ejecutar en Win+R
shell:startup
```
4. Pega el acceso directo dentro de esa carpeta.

### 4.2 Linux (GNOME, KDE, XFCE)

1. Copia el ejecutable `main` a una ubicación permanente, por ejemplo:
```bash
cp dist/main ~/.local/bin/tasa_bcv/main
```
2. Asegúrate de permisos de ejecución:
```bash
chmod +x ~/.local/bin/tasa_bcv/main
```
3. Crea la carpeta de autostart si no existe:
```bash
mkdir -p ~/.config/autostart
```
4. Crea el archivo `~/.config/autostart/rate_bcv.desktop` con el siguiente contenido (reemplaza `Exec=` con la ruta absoluta del ejecutable):

```ini
[Desktop Entry]
Type=Application
Name=Widget Tasa BCV
Comment=Muestra la tasa de cambio del BCV
# IMPORTANTE: Reemplaza la ruta 'Exec' con la ABSOLUTA y CORRECTA de tu ejecutable
Exec=/home/tu_usuario/.local/bin/tasa_bcv/main
Terminal=false
StartupNotify=false
Icon=utilities-system-monitor
```

---

## 5. Notas adicionales y buenas prácticas

- Ajusta los horarios de actualización en el código Python si lo necesitas.
- Mantén el archivo `rate_bcv.db` en una ubicación con permisos de escritura para la aplicación.
- Para depuración, ejecuta el script directamente en el entorno virtual antes de crear el ejecutable:
```bash
python src/main.py
```

---


