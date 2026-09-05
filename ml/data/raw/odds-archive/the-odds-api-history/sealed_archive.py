#!/usr/bin/env python3
"""Deterministically pack and AES-256-GCM seal Odds API season archives."""

from __future__ import annotations

import argparse
import base64
import binascii
import gzip
import hashlib
import io
import json
import os
import sys
import tarfile
from pathlib import Path, PurePosixPath

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

NONCE_BYTES = 12
KEY_BYTES = 32


def load_env_value(name: str) -> str:
    value = os.environ.get(name)
    if value:
        return value
    env_path = Path(__file__).resolve().parents[4] / ".env"
    if env_path.exists():
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, candidate = line.split("=", 1)
            if key.strip() == name:
                value = candidate.strip().strip('"').strip("'")
                if value:
                    return value
    raise RuntimeError(f"{name} is missing from environment and ml/.env")


def archive_key() -> bytes:
    encoded = load_env_value("ODDS_ARCHIVE_KEY")
    try:
        key = base64.b64decode(encoded, altchars=b"-_", validate=True)
    except (binascii.Error, ValueError):
        raise RuntimeError("ODDS_ARCHIVE_KEY must be urlsafe-base64 encoded") from None
    if len(key) != KEY_BYTES:
        raise RuntimeError("ODDS_ARCHIVE_KEY must decode to exactly 32 bytes")
    return key


def deterministic_tar(source: Path) -> bytes:
    if not source.is_dir():
        raise RuntimeError(f"season plaintext directory not found: {source}")
    entries = sorted(source.rglob("*"), key=lambda path: path.relative_to(source).as_posix())
    if not entries:
        raise RuntimeError(f"season plaintext directory is empty: {source}")
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for path in entries:
            if path.is_symlink():
                raise RuntimeError(f"symlinks are not allowed: {path}")
            relative = path.relative_to(source).as_posix()
            info = tarfile.TarInfo(relative + ("/" if path.is_dir() else ""))
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            if path.is_dir():
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
                archive.addfile(info)
                continue
            if not path.is_file():
                raise RuntimeError(f"unsupported archive entry: {path}")
            info.type = tarfile.REGTYPE
            info.mode = 0o644
            info.size = path.stat().st_size
            with path.open("rb") as handle:
                archive.addfile(info, handle)
    return output.getvalue()


def deterministic_gzip(data: bytes) -> bytes:
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0) as handle:
        handle.write(data)
    return output.getvalue()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def seal(source: Path, output: Path, force: bool) -> dict[str, int | str]:
    if output.exists() and not force:
        raise RuntimeError(f"output already exists; pass --force to replace: {output}")
    tar_bytes = deterministic_tar(source)
    plaintext = deterministic_gzip(tar_bytes)
    nonce = os.urandom(NONCE_BYTES)
    ciphertext = nonce + AESGCM(archive_key()).encrypt(nonce, plaintext, None)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_bytes(ciphertext)
    os.replace(temporary, output)
    return {
        "ciphertext_bytes": len(ciphertext),
        "ciphertext_sha256": sha256(ciphertext),
        "plaintext_gzip_bytes": len(plaintext),
        "plaintext_gzip_sha256": sha256(plaintext),
        "tar_bytes": len(tar_bytes),
        "tar_sha256": sha256(tar_bytes),
    }


def safe_destination(root: Path, member_name: str) -> Path:
    member = PurePosixPath(member_name)
    if member.is_absolute() or ".." in member.parts:
        raise RuntimeError(f"unsafe archive member: {member_name}")
    destination = (root / Path(*member.parts)).resolve()
    try:
        destination.relative_to(root.resolve())
    except ValueError:
        raise RuntimeError(f"unsafe archive member: {member_name}") from None
    return destination


def open_archive(source: Path, destination: Path) -> dict[str, int | str]:
    if not source.is_file():
        raise RuntimeError(f"encrypted archive not found: {source}")
    if destination.exists() and any(destination.iterdir()):
        raise RuntimeError(f"destination must be absent or empty: {destination}")
    blob = source.read_bytes()
    if len(blob) <= NONCE_BYTES:
        raise RuntimeError("encrypted archive is truncated")
    nonce = blob[:NONCE_BYTES]
    try:
        plaintext = AESGCM(archive_key()).decrypt(nonce, blob[NONCE_BYTES:], None)
    except InvalidTag:
        raise RuntimeError("decryption failed: ODDS_ARCHIVE_KEY is missing or wrong") from None
    try:
        tar_bytes = gzip.decompress(plaintext)
    except OSError:
        raise RuntimeError("decrypted payload is not valid gzip data") from None
    destination.mkdir(parents=True, exist_ok=True)
    file_count = 0
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:") as archive:
        members = archive.getmembers()
        for member in members:
            target = safe_destination(destination, member.name)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise RuntimeError(f"unsupported archive member: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            source_handle = archive.extractfile(member)
            if source_handle is None:
                raise RuntimeError(f"cannot read archive member: {member.name}")
            target.write_bytes(source_handle.read())
            file_count += 1
    return {
        "ciphertext_sha256": sha256(blob),
        "plaintext_gzip_sha256": sha256(plaintext),
        "tar_sha256": sha256(tar_bytes),
        "files_opened": file_count,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    seal_parser = commands.add_parser("seal")
    seal_parser.add_argument("season_plaintext_dir", type=Path)
    seal_parser.add_argument("output", type=Path)
    seal_parser.add_argument("--force", action="store_true")
    open_parser = commands.add_parser("open")
    open_parser.add_argument("input", type=Path)
    open_parser.add_argument("destination", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "seal":
            result = seal(args.season_plaintext_dir, args.output, args.force)
        elif args.command == "open":
            result = open_archive(args.input, args.destination)
        else:
            raise RuntimeError(f"unsupported command: {args.command}")
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
