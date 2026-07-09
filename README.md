# ProyectoPDI — Visor de Cámara

Aplicación Windows con interfaz tkinter que detecta cámaras USB e integradas,
permite seleccionar el dispositivo y muestra una vista previa en vivo.

También soporta **cámaras IP / stream de red** como ESP32-CAM, cámaras RTSP
y cualquier fuente MJPEG sobre HTTP.

## Requisitos

- Windows 10 u 11
- Python 3.13 o superior
- Cámara USB, integrada, **o** cámara IP accesible por red

## Instalación rápida

```bat
setup.bat    # crea entorno virtual e instala dependencias
run.bat      # inicia la aplicación
```

O manualmente:

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Cámaras IP / ESP32-CAM

Hacé clic en **🌐 Red** en la barra de herramientas, ingresá la URL del stream
y conectate. Ejemplos de URLs compatibles:

| Tipo | Ejemplo |
|------|---------|
| ESP32-CAM (MJPEG) | `http://192.168.1.100:81/stream` |
| RTSP | `rtsp://usuario:contraseña@cámara:554/stream` |
| RTMP | `rtmp://…` |
| Cualquier MJPEG | `http://…` |

> **Nota para ESP32-CAM por USB:** si el microcontrolador está flasheado
> con firmware UVC, aparece como cámara local normal y se detecta con
> el botón 🔍 Detectar. No necesita URL.

## Dos versiones

### 🟢 Portable (para USAR, no requiere nada)

```
portable/VisorCamara.exe
```

Doble clic y funciona. Windows 10 u 11. Sin instalar nada.

### 🔵 Desarrollador (para MODIFICAR el código)

```bat
setup.bat        # instala dependencias
run.bat          # ejecuta desde el código fuente
build.bat        # compila portable/VisorCamara.exe actualizado
```

Requiere Python 3.13 y opcionalmente OpenCode para editar.

### ¿Cuál elijo?

| Querés… | Usá |
|---------|-----|
| Solo ver la cámara ya | `portable/VisorCamara.exe` |
| Cambiar el código o agregar features | El repo completo + `run.bat` |
| Probar en otra máquina sin Python | `portable/VisorCamara.exe`

## Solución de problemas

### "Cámara detenida" sin imagen

1. Asegurate de que ninguna otra aplicación esté usando la cámara
   (Zoom, Teams, navegador, etc.)
2. Reiniciá la aplicación
3. Desconectá y reconectá la cámara USB
4. Verificá que Windows no esté bloqueando la cámara:
   Configuración → Privacidad y seguridad → Cámara → "Permitir que las
   aplicaciones de escritorio accedan a la cámara"

### La cámara no se detecta

- Probalo en otra aplicación (Cámara de Windows) para descartar un
  problema de hardware o driver
- Revisá que el cable USB esté bien conectado

## Estructura del proyecto

Ver [`_asistente-ia/guia-estructura.md`](_asistente-ia/guia-estructura.md)
para la guía visual completa del árbol de archivos.

## Tecnologías

- Python 3.13
- OpenCV 5.0 (captura de video local y por red)
- Pillow 12.2 (conversión y renderizado)
- tkinter (interfaz gráfica)
- numpy 2.4 (manejo de matrices de imagen)
- PyInstaller (build de .exe standalone)
