"""Simple Spotify playlist to MP3 downloader.

Este script obtiene metadata de una playlist de Spotify, busca el mejor match
en YouTube y descarga el audio como MP3 usando yt-dlp + ffmpeg.

Ejemplo rápido:
    python src/spotify2mp3.py \
        --playlist https://open.spotify.com/playlist/37i9dQZF1DWW7hJS3Xj96I \
        --out-dir downloads

Variables requeridas:
    SPOTIFY_CLIENT_ID
    SPOTIFY_CLIENT_SECRET
Opcional:
    SPOTIFY_REDIRECT_URI (solo para flujos distintos a client credentials)

Nota: ffmpeg debe estar en el PATH para que yt-dlp convierta a MP3.
"""

from __future__ import annotations

import argparse
import dataclasses
import os
import re
import sys
from pathlib import Path
from typing import Iterable, List, Optional, Sequence
import shutil

import spotipy
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import track
from spotipy.oauth2 import SpotifyClientCredentials
from yt_dlp import YoutubeDL

console = Console()


@dataclasses.dataclass
class Track:
    """Lightweight representation of a Spotify track."""

    title: str
    artists: List[str]
    duration_ms: int
    album: str

    def pretty_title(self) -> str:
        return f"{self.title} - {', '.join(self.artists)}"


def ensure_ffmpeg_available(ffmpeg_path: Optional[str] = None) -> str:
    """Return a valid ffmpeg binary path or exit with guidance."""

    def _fail(msg: str) -> None:
        console.print(
            "[red]" + msg + "[/red]\n"
            "Windows: https://www.gyan.dev/ffmpeg/builds/\n"
            "Mac/Linux: usa tu gestor de paquetes (brew/apt/yum).",
            style="bold",
        )
        sys.exit(1)

    if ffmpeg_path:
        candidate = Path(ffmpeg_path)
        if candidate.is_dir():
            candidate = candidate / ("ffmpeg.exe" if sys.platform.startswith("win") else "ffmpeg")
        if candidate.exists():
            return str(candidate)
        _fail(f"ffmpeg no se encontró en la ruta proporcionada: {candidate}")

    found = shutil.which("ffmpeg")
    if found:
        return found

    _fail("ffmpeg no se encontró en el PATH. Instálalo y vuelve a intentar.")


def load_credentials(interactive: bool = True) -> None:
    """Load env vars; optionally prompt once if missing."""

    load_dotenv()
    required = ("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET")
    missing = [k for k in required if not os.getenv(k)]
    if not missing:
        return

    if interactive:
        console.print(
            Panel(
                "No encontré credenciales de Spotify. Ingresa estos valores para esta ejecución (no se guardan en disco).",
                title="Config rápida",
                style="yellow",
            )
        )
        for key in missing:
            value = console.input(f"{key}: ").strip()
            if value:
                os.environ[key] = value

    missing_after = [k for k in required if not os.getenv(k)]
    if missing_after:
        console.print(
            "[red]Faltan variables de entorno necesarias:[/red] "
            + ", ".join(missing_after)
            + "\nCrea un archivo .env con SPOTIFY_CLIENT_ID y SPOTIFY_CLIENT_SECRET.",
            style="bold",
        )
        sys.exit(1)


def build_spotify_client() -> spotipy.Spotify:
    """Return an authenticated Spotify client using client credentials."""

    auth_manager = SpotifyClientCredentials()
    return spotipy.Spotify(auth_manager=auth_manager)


def parse_playlist_id(raw: str) -> str:
    """Extract playlist ID from a URL or raw ID."""

    # Handle URLs like https://open.spotify.com/playlist/<id>?si=...
    match = re.search(r"playlist/([a-zA-Z0-9]+)", raw)
    if match:
        return match.group(1)
    # Handle custom proxy URL in the example
    match = re.search(r"playlist/([a-zA-Z0-9]+)", raw.rstrip("/"))
    if match:
        return match.group(1)
    return raw


def fetch_playlist_tracks(client: spotipy.Spotify, playlist: str) -> List[Track]:
    """Fetch all tracks from a playlist and normalize fields."""

    playlist_id = parse_playlist_id(playlist)
    limit = 100
    offset = 0
    items: List[Track] = []

    while True:
        batch = client.playlist_items(
            playlist_id,
            offset=offset,
            limit=limit,
            fields="items(track(name,artists(name),duration_ms,album(name))),next",
        )
        for entry in batch.get("items", []):
            track = entry.get("track") or {}
            if not track:
                continue
            items.append(
                Track(
                    title=track.get("name", "Unknown"),
                    artists=[a.get("name", "") for a in track.get("artists", [])],
                    duration_ms=int(track.get("duration_ms") or 0),
                    album=track.get("album", {}).get("name", ""),
                )
            )
        if not batch.get("next"):
            break
        offset += limit

    return items


def sanitize_filename(name: str) -> str:
    """Make a filesystem-safe filename."""

    return re.sub(r"[^\w\-\. ]", "", name).strip()


def pick_best_youtube_result(candidates: Iterable[dict], target_duration: int) -> Optional[dict]:
    """Choose the YouTube result whose duration is closest to target."""

    best = None
    best_delta = None
    for item in candidates:
        duration = item.get("duration") or 0
        delta = abs(duration - target_duration)
        if best_delta is None or delta < best_delta:
            best = item
            best_delta = delta
    return best


def search_youtube_audio(query: str, target_duration: int) -> Optional[str]:
    """Search YouTube for the query and return a video URL or None."""

    ydl_opts = {
        "quiet": True,
        "skip_download": True,
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"ytsearch10:{query}", download=False)
    entries = info.get("entries") or []
    best = pick_best_youtube_result(entries, target_duration)
    if not best:
        return None
    return f"https://www.youtube.com/watch?v={best['id']}"


def download_track(video_url: str, track: Track, out_dir: Path, ffmpeg_path: Optional[str]) -> Path:
    """Download a single track as MP3 to out_dir."""

    filename = sanitize_filename(track.pretty_title()) or "track"
    output_template = str(out_dir / f"{filename}.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "quiet": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "320",
            },
            {"key": "FFmpegMetadata"},
        ],
        "postprocessor_args": [
            "-metadata",
            f"title={track.title}",
            "-metadata",
            f"artist={', '.join(track.artists)}",
            "-metadata",
            f"album={track.album}",
        ],
    }

    if ffmpeg_path:
        ydl_opts["ffmpeg_location"] = ffmpeg_path

    with YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])

    return Path(output_template.replace("%(ext)s", "mp3"))


def process_playlist(
    playlist: str,
    out_dir: Path,
    limit: Optional[int],
    ffmpeg_path: Optional[str],
) -> None:
    """Orchestrate fetching, searching, and downloading."""

    resolved_ffmpeg = ensure_ffmpeg_available(ffmpeg_path)
    load_credentials()

    try:
        client = build_spotify_client()
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]No se pudo crear el cliente de Spotify: {exc}[/red]")
        sys.exit(1)

    console.print(Panel.fit(f"Descargando playlist: {playlist}", style="cyan"))
    try:
        tracks = fetch_playlist_tracks(client, playlist)
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Error obteniendo playlist: {exc}[/red]")
        sys.exit(1)

    if limit is not None:
        tracks = tracks[:limit]

    if not tracks:
        console.print("[yellow]No se encontraron pistas en la playlist.[/yellow]")
        return

    out_dir.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    skipped: List[str] = []

    for track_obj in track(tracks, description="Descargando", console=console):
        query = f"{track_obj.title} {track_obj.artists[0] if track_obj.artists else ''} audio"
        target_seconds = track_obj.duration_ms // 1000
        video_url = search_youtube_audio(query, target_seconds)
        if not video_url:
            skipped.append(track_obj.pretty_title())
            console.print(f"[yellow]No se encontró resultado para {track_obj.pretty_title()}[/yellow]")
            continue
        try:
            output_path = download_track(video_url, track_obj, out_dir, resolved_ffmpeg)
            downloaded += 1
            console.print(f"[green]OK[/green] {track_obj.pretty_title()} -> {output_path.name}")
        except Exception as exc:  # noqa: BLE001
            skipped.append(track_obj.pretty_title())
            console.print(f"[red]Error descargando {track_obj.pretty_title()}: {exc}[/red]")

    console.print(
        Panel(
            f"Listo. {downloaded} descargadas, {len(skipped)} pendientes.",
            title="Resumen",
            style="green" if downloaded else "yellow",
        )
    )
    if skipped:
        console.print("Saltadas:")
        for name in skipped:
            console.print(f" - {name}")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Descarga playlists de Spotify a MP3")
    parser.add_argument("--playlist", required=True, help="URL o ID de la playlist de Spotify")
    parser.add_argument("--out-dir", default="downloads", help="Directorio de salida")
    parser.add_argument("--limit", type=int, default=None, help="Límite opcional de pistas para prueba")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Solo valida dependencias (ffmpeg/credenciales) y sale",
    )
    parser.add_argument(
        "--ffmpeg-path",
        help="Ruta directa a ffmpeg (binario o carpeta que lo contiene)",
        default=None,
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    if args.check:
        ensure_ffmpeg_available(args.ffmpeg_path)
        load_credentials()
        console.print("Entorno OK. Ejecuta de nuevo sin --check para descargar.", style="green")
        return

    process_playlist(args.playlist, Path(args.out_dir), args.limit, args.ffmpeg_path)


if __name__ == "__main__":
    main()
