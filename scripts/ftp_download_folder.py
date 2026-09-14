"""
Download image files from a remote FTP folder into a local mirror directory.

Used by scripts/upload_almarphoto_photos.ps1 when -UseFtp is passed. Only
downloads files that are missing locally or have a different size on the server.

Credentials can be passed on the command line or via env vars:
  ALMARPHOTO_FTP_HOST, ALMARPHOTO_FTP_USER, ALMARPHOTO_FTP_PASSWORD,
  ALMARPHOTO_FTP_REMOTE_PATH (default: /uploads)

Example:

    python scripts/ftp_download_folder.py --dest C:/temp/almarphoto_uploads
    python scripts/ftp_download_folder.py --host ftp.example.com --user u --password p \\
        --remote /htdocs/almarphoto/uploads --dest C:/temp/almarphoto_uploads --dry-run
"""

from __future__ import annotations

import argparse
import ftplib
import os
import sys
from pathlib import Path

IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".tif", ".tiff"}


def _connect(host: str, user: str, password: str, port: int, timeout: int) -> ftplib.FTP:
    ftp = ftplib.FTP()
    ftp.connect(host, port, timeout=timeout)
    ftp.login(user, password)
    ftp.set_pasv(True)
    return ftp


def _remote_size(ftp: ftplib.FTP, remote_path: str) -> int | None:
    try:
        return ftp.size(remote_path)
    except ftplib.error_perm:
        return None


def _list_files(ftp: ftplib.FTP, remote_dir: str) -> list[str]:
    remote_dir = remote_dir.rstrip("/") or "/"
    names = ftp.nlst(remote_dir)
    out: list[str] = []
    for name in names:
        base = name.rsplit("/", 1)[-1]
        if base in (".", ".."):
            continue
        if Path(base).suffix.lower() in IMG_EXT:
            out.append(name if name.startswith("/") else f"{remote_dir}/{base}".replace("//", "/"))
    return sorted(set(out))


def sync_folder(
    *,
    host: str,
    user: str,
    password: str,
    remote_dir: str,
    dest: Path,
    port: int = 21,
    timeout: int = 60,
    dry_run: bool = False,
) -> dict[str, int]:
    dest.mkdir(parents=True, exist_ok=True)
    ftp = _connect(host, user, password, port, timeout)
    try:
        remote_files = _list_files(ftp, remote_dir)
    finally:
        ftp.quit()

    downloaded = skipped = failed = 0
    for remote_path in remote_files:
        local_path = dest / Path(remote_path).name
        remote_size = None
        try:
            ftp = _connect(host, user, password, port, timeout)
            try:
                remote_size = _remote_size(ftp, remote_path)
                if local_path.is_file() and remote_size is not None and local_path.stat().st_size == remote_size:
                    skipped += 1
                    continue
                if dry_run:
                    print(f"would download {remote_path} -> {local_path}")
                    downloaded += 1
                    continue
                with local_path.open("wb") as fh:
                    ftp.retrbinary(f"RETR {remote_path}", fh.write)
                print(f"downloaded {local_path.name}")
                downloaded += 1
            finally:
                ftp.quit()
        except Exception as exc:  # pragma: no cover - network dependent
            failed += 1
            print(f"failed {remote_path}: {exc}", file=sys.stderr)

    return {
        "remote_files": len(remote_files),
        "downloaded": downloaded,
        "skipped": skipped,
        "failed": failed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Mirror image files from an FTP folder.")
    parser.add_argument("--host", default=os.environ.get("ALMARPHOTO_FTP_HOST", ""))
    parser.add_argument("--user", default=os.environ.get("ALMARPHOTO_FTP_USER", ""))
    parser.add_argument("--password", default=os.environ.get("ALMARPHOTO_FTP_PASSWORD", ""))
    parser.add_argument(
        "--remote",
        default=os.environ.get("ALMARPHOTO_FTP_REMOTE_PATH", "/uploads"),
        help="Remote FTP folder (default: /uploads or ALMARPHOTO_FTP_REMOTE_PATH).",
    )
    parser.add_argument("--dest", required=True, help="Local folder to write files into.")
    parser.add_argument("--port", type=int, default=21)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.host or not args.user:
        parser.error("FTP host and user are required (--host / --user or ALMARPHOTO_FTP_* env vars).")

    stats = sync_folder(
        host=args.host,
        user=args.user,
        password=args.password or "",
        remote_dir=args.remote,
        dest=Path(args.dest).expanduser(),
        port=args.port,
        timeout=args.timeout,
        dry_run=args.dry_run,
    )
    print(
        f"\nDone. remote={stats['remote_files']} downloaded={stats['downloaded']} "
        f"skipped={stats['skipped']} failed={stats['failed']} dry_run={args.dry_run}"
    )
    return 1 if stats["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
