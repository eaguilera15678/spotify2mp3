# spotify2mp3

Script en Python para descargar playlists de Spotify en formato MP3 usando spotipy para obtener la metadata y yt-dlp + ffmpeg para la descarga y transcodificación. Ejemplo con la playlist `https://open.spotify.com/playlist/37i9dQZF1DWW7hJS3Xj96I`.

## Requisitos
- Python 3.10+ (probado en 3.13)
- ffmpeg disponible en tu PATH
- Credenciales de API de Spotify (Client ID y Client Secret)

## Instalación
1. Crea y activa un entorno virtual (opcional pero recomendado):
   ```sh
   python -m venv .venv
   .venv/Scripts/activate  # Windows
   # source .venv/bin/activate  # macOS/Linux
   ```
2. Instala dependencias:
   ```sh
   pip install -r requirements.txt
   ```
3. Crea un archivo `.env` en la raíz con tus credenciales de Spotify:
   ```env
   SPOTIFY_CLIENT_ID=tu_client_id
   SPOTIFY_CLIENT_SECRET=tu_client_secret
   ```

## Uso
Ejemplo con la playlist del enunciado, descargando a la carpeta `downloads`:
```sh
python src/spotify2mp3.py --playlist https://open.spotify.com/playlist/37i9dQZF1DWW7hJS3Xj96I --out-dir downloads
```

Si ffmpeg no está en el PATH, indica la ruta al binario (o carpeta que lo contiene):
```sh
python src/spotify2mp3.py --playlist <url_o_id> --out-dir downloads --ffmpeg-path "C:\\ffmpeg\\bin\\ffmpeg.exe"
```
También funciona pasando solo la carpeta `--ffmpeg-path C:\\ffmpeg\\bin`.

Si quieres validar el entorno antes de descargar (ffmpeg y credenciales), usa:
```sh
python src/spotify2mp3.py --playlist <url_o_id> --check
```
Si faltan credenciales y no tienes `.env`, el script te pedirá los valores para esa ejecución (no se guardan en disco).

Parámetros disponibles:
- `--playlist` (requerido): URL o ID de la playlist de Spotify.
- `--out-dir` (opcional): carpeta de salida (por defecto `downloads`).
- `--limit` (opcional): número de pistas a procesar para pruebas rápidas.

## Notas
- yt-dlp necesita ffmpeg para convertir a MP3. En Windows puedes instalar builds desde https://www.gyan.dev/ffmpeg/builds/
- El script añade metadatos básicos (título, artista y álbum) al MP3.
- Usa este proyecto de forma responsable y respeta los términos de servicio de Spotify y YouTube.
