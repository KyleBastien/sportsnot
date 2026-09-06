#!/usr/bin/env python3
"""Deterministically pack and AES-256-GCM seal Odds API season archives."""

from __future__ import annotations

import argparse
import base64
import binascii
import gzip
import io
import json
import os
import sys
import tarfile
from pathlib import Path, PurePosixPath

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from odds_archive_common import load_env_value, sha256

NONCE_BYTES = 12
KEY_BYTES = 32


def archive_key() -> bytes:
    encoded = load_env_value("ODDS_ARCHIVE_KEY")
    try:
        key = base64.b64decode(encoded, altchars=b"-_", validate=True)
    except (binascii.Error, ValueError):
        raise RuntimeError("ODDS_ARCHIVE_KEY must be urlsafe-base64 encoded") from None
    if len(key) != KEY_BYTES:
        raise RuntimeError("ODDS_ARCHIVE_KEY must decode to exactly 32 bytes")
    return key


def _tar_info(path: Path, source: Path) -> tarfile.TarInfo:
    relative = path.relative_to(source).as_posix()
    info = tarfile.TarInfo(relative + ("/" if path.is_dir() else ""))
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    return info


def _add_tar_entry(archive: tarfile.TarFile, path: Path, source: Path) -> None:
    if path.is_symlink():
        raise RuntimeError(f"symlinks are not allowed: {path}")
    info = _tar_info(path, source)
    if path.is_dir():
        info.type = tarfile.DIRTYPE
        info.mode = 0o755
        archive.addfile(info)
        return
    if not path.is_file():
        raise RuntimeError(f"unsupported archive entry: {path}")
    info.type = tarfile.REGTYPE
    info.mode = 0o644
    info.size = path.stat().st_size
    with path.open("rb") as handle:
        archive.addfile(info, handle)


def _source_entries(source: Path) -> list[Path]:
    if not source.is_dir():
        raise RuntimeError(f"season plaintext directory not found: {source}")
    entries = sorted(source.rglob("*"), key=lambda path: path.relative_to(source).as_posix())
    if not entries:
        raise RuntimeError(f"season plaintext directory is empty: {source}")
    return entries


def deterministic_tar(source: Path) -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for path in _source_entries(source):
            _add_tar_entry(archive, path, source)
    return output.getvalue()


def deterministic_gzip(data: bytes) -> bytes:
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0) as handle:
        handle.write(data)
    return output.getvalue()


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


def _decrypt(blob: bytes) -> bytes:
    if len(blob) <= NONCE_BYTES:
        raise RuntimeError("encrypted archive is truncated")
    nonce = blob[:NONCE_BYTES]
    try:
        return AESGCM(archive_key()).decrypt(nonce, blob[NONCE_BYTES:], None)
    except InvalidTag:
        raise RuntimeError("decryption failed: ODDS_ARCHIVE_KEY is missing or wrong") from None


def _decompress(plaintext: bytes) -> bytes:
    try:
        return gzip.decompress(plaintext)
    except OSError:
        raise RuntimeError("decrypted payload is not valid gzip data") from None


def _validate_destination(destination: Path) -> None:
    if destination.exists() and any(destination.iterdir()):
        raise RuntimeError(f"destination must be absent or empty: {destination}")


def _extract_member(archive: tarfile.TarFile, member: tarfile.TarInfo, destination: Path) -> bool:
    target = safe_destination(destination, member.name)
    if member.isdir():
        target.mkdir(parents=True, exist_ok=True)
        return False
    if not member.isfile():
        raise RuntimeError(f"unsupported archive member: {member.name}")
    source_handle = archive.extractfile(member)
    if source_handle is None:
        raise RuntimeError(f"cannot read archive member: {member.name}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source_handle.read())
    return True


def open_archive(source: Path, destination: Path) -> dict[str, int | str]:
    if not source.is_file():
        raise RuntimeError(f"encrypted archive not found: {source}")
    _validate_destination(destination)
    blob = source.read_bytes()
    plaintext = _decrypt(blob)
    tar_bytes = _decompress(plaintext)
    destination.mkdir(parents=True, exist_ok=True)
    file_count = 0
    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r:") as archive:
        for member in archive.getmembers():
            file_count += _extract_member(archive, member, destination)
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
