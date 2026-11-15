#!/usr/bin/env python3
"""Guncelleme paketleri icin Ed25519 anahtar yonetimi ve detached imzalama.

Updater, yayinlanan ``.sig`` dosyasini ``<artefakt>.sig`` adresinden indirir ve
``hidrostatik_test/app_metadata.py`` icindeki ``UPDATE_SIGNING_PUBLIC_KEY``
degeriyle dogrular. Bu arac ayni bicimi uretir:

- Imza: 64 baytlik ham Ed25519 imzasinin **base64** kodlamasi (tek satir).
  Updater hem ham 64 baytlik hem base64 metin bicimini kabul eder; base64
  metin, GitHub release asset'i olarak tasinirken bozulmadigi icin secildi.

Alt komutlar:

    generate   Anahtar cifti uretir; ozel anahtar ~/.config/hydro/ altina yazilir,
               public key base64 olarak stdout'a basilir.
    sign       <artefakt> icin <artefakt>.sig dosyasini uretir.
    verify     <artefakt> <imza> dosyasini public key ile dogrular.
    fingerprint Anahtar parmak izini (SHA-256) yazdirir.

Ozel anahtar repoya asla yazilmaz. Yolu degistirmek icin ``--key`` veya
``HYDRO_UPDATE_SIGNING_KEY`` ortam degiskeni kullanilabilir.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_KEY_PATH = Path.home() / ".config" / "hydro" / "update_signing_key.pem"
KEY_PATH_ENV = "HYDRO_UPDATE_SIGNING_KEY"
SIGNATURE_SUFFIX = ".sig"
SIGNATURE_BYTES = 64
PUBLIC_KEY_BYTES = 32


class SigningError(RuntimeError):
    """Kullaniciya dogrudan gosterilebilecek imzalama hatasi."""


def _crypto():
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
            Ed25519PublicKey,
        )
    except ImportError as exc:  # pragma: no cover - bagimlilik eksikse
        raise SystemExit(
            "HATA: 'cryptography' paketi gerekli. Kurmak icin: python -m pip install -r requirements.txt"
        ) from exc
    return serialization, Ed25519PrivateKey, Ed25519PublicKey


def resolve_key_path(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    env_value = os.environ.get(KEY_PATH_ENV, "").strip()
    if env_value:
        return Path(env_value).expanduser()
    return DEFAULT_KEY_PATH


def public_key_bytes(private_key) -> bytes:
    serialization, _, _ = _crypto()
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def fingerprint(public_bytes: bytes) -> str:
    """SSH benzeri parmak izi: SHA-256'nin iki haneli bayt gruplari."""
    digest = hashlib.sha256(public_bytes).hexdigest().upper()
    return ":".join(digest[index : index + 2] for index in range(0, len(digest), 2))


def encode_public_key(public_bytes: bytes) -> str:
    return base64.b64encode(public_bytes).decode("ascii")


def decode_public_key(material: str) -> bytes:
    compact = "".join(material.split())
    if not compact:
        raise SigningError("Public key bos.")
    try:
        raw = base64.b64decode(compact, validate=True)
    except (ValueError, TypeError) as exc:
        raise SigningError("Public key base64 kodlu olmali.") from exc
    if len(raw) != PUBLIC_KEY_BYTES:
        raise SigningError(
            f"Public key {PUBLIC_KEY_BYTES} baytlik Ed25519 anahtari olmali (gelen: {len(raw)} bayt)."
        )
    return raw


def load_private_key(path: Path):
    serialization, _, _ = _crypto()
    if not path.is_file():
        raise SigningError(
            f"Ozel anahtar bulunamadi: {path}\n"
            f"Once 'python3 tools/update_signing.py generate' calistirin veya {KEY_PATH_ENV} ile yolu belirtin."
        )
    try:
        return serialization.load_pem_private_key(path.read_bytes(), password=None)
    except (ValueError, TypeError) as exc:
        raise SigningError(f"Ozel anahtar PEM olarak okunamadi: {path}") from exc


def decode_signature_file(raw: bytes) -> bytes:
    """Updater ile ayni kural: 64 bayt ham veri ya da base64 metin."""
    if len(raw) == SIGNATURE_BYTES:
        return raw
    blob = raw.strip()
    if not blob:
        raise SigningError("Imza dosyasi bos.")
    try:
        decoded = base64.b64decode(blob, validate=True)
    except (ValueError, TypeError) as exc:
        raise SigningError("Imza dosyasi base64 olarak okunamadi.") from exc
    if len(decoded) != SIGNATURE_BYTES:
        raise SigningError(f"Imza {SIGNATURE_BYTES} bayt olmali (gelen: {len(decoded)} bayt).")
    return decoded


def write_private_key(path: Path, pem: bytes, *, force: bool) -> None:
    created_parent = not path.parent.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    if created_parent or path.parent == DEFAULT_KEY_PATH.parent:
        try:
            os.chmod(path.parent, 0o700)
        except OSError:
            pass
    if path.exists() and not force:
        raise SigningError(f"Anahtar zaten var: {path} (yeniden uretmek icin --force kullanin).")
    temporary = path.with_name(f".{path.name}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(pem)
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass
    os.chmod(path, 0o600)


def command_generate(args: argparse.Namespace) -> int:
    serialization, Ed25519PrivateKey, _ = _crypto()
    key_path = resolve_key_path(args.key)

    if key_path.exists() and not args.force:
        exit_code = 0
        print(
            f"UYARI: Ozel anahtar zaten mevcut, uzerine yazilmadi: {key_path}",
            file=sys.stderr,
        )
        print(
            "       Yeniden uretmek icin --force kullanin (mevcut imzalar gecersiz olur).",
            file=sys.stderr,
        )
        private_key = load_private_key(key_path)
    else:
        private_key = Ed25519PrivateKey.generate()
        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        write_private_key(key_path, pem, force=True)
        print(f"Ozel anahtar yazildi (0600): {key_path}", file=sys.stderr)
        exit_code = 0

    raw_public = public_key_bytes(private_key)
    print(f"Parmak izi (SHA-256): {fingerprint(raw_public)}", file=sys.stderr)
    print(
        "Public key'i hidrostatik_test/app_metadata.py icindeki UPDATE_SIGNING_PUBLIC_KEY degerine yazin.",
        file=sys.stderr,
    )
    # stdout yalnizca public key tasir; scriptler dogrudan kullanabilir.
    print(encode_public_key(raw_public))
    return exit_code


def command_sign(args: argparse.Namespace) -> int:
    private_key = load_private_key(resolve_key_path(args.key))
    artifact = Path(args.artifact).expanduser()
    if not artifact.is_file():
        raise SigningError(f"Imzalanacak dosya bulunamadi: {artifact}")
    payload = artifact.read_bytes()
    if not payload:
        raise SigningError(f"Imzalanacak dosya bos: {artifact}")
    signature = private_key.sign(payload)
    if len(signature) != SIGNATURE_BYTES:  # pragma: no cover - savunma amacli
        raise SigningError("Beklenmeyen imza uzunlugu.")
    output = (
        Path(args.output).expanduser()
        if args.output
        else artifact.with_name(f"{artifact.name}{SIGNATURE_SUFFIX}")
    )
    output.write_text(base64.b64encode(signature).decode("ascii") + "\n", encoding="ascii")
    print(f"Imza yazildi: {output}", file=sys.stderr)
    print(output)
    return 0


def command_verify(args: argparse.Namespace) -> int:
    _, _, Ed25519PublicKey = _crypto()
    from cryptography.exceptions import InvalidSignature

    artifact = Path(args.artifact).expanduser()
    if not artifact.is_file():
        raise SigningError(f"Dogrulanacak dosya bulunamadi: {artifact}")
    signature_path = (
        Path(args.signature).expanduser()
        if args.signature
        else artifact.with_name(f"{artifact.name}{SIGNATURE_SUFFIX}")
    )
    if not signature_path.is_file():
        raise SigningError(
            f"Imza dosyasi bulunamadi: {signature_path}\n"
            "Imzalanmamis bir paket yayinlanamaz; once 'sign' calistirin."
        )
    signature = decode_signature_file(signature_path.read_bytes())

    if args.public_key:
        raw_public = decode_public_key(args.public_key)
    elif args.key:
        raw_public = public_key_bytes(load_private_key(resolve_key_path(args.key)))
    else:
        raw_public = decode_public_key(_embedded_public_key())

    key = Ed25519PublicKey.from_public_bytes(raw_public)
    try:
        key.verify(signature, artifact.read_bytes())
    except InvalidSignature as exc:
        raise SigningError(
            f"IMZA GECERSIZ: {artifact.name}\n"
            "Dosya degistirilmis/bozulmus veya imza baska bir anahtarla uretilmis."
        ) from exc
    print(f"OK: {artifact.name} imzasi dogrulandi (parmak izi {fingerprint(raw_public)})")
    return 0


def command_fingerprint(args: argparse.Namespace) -> int:
    if args.public_key:
        raw_public = decode_public_key(args.public_key)
    elif args.key:
        raw_public = public_key_bytes(load_private_key(resolve_key_path(args.key)))
    else:
        raw_public = decode_public_key(_embedded_public_key())
    print(f"Parmak izi (SHA-256): {fingerprint(raw_public)}")
    print(f"Public key (base64): {encode_public_key(raw_public)}")
    return 0


def _embedded_public_key() -> str:
    from hidrostatik_test.app_metadata import UPDATE_SIGNING_PUBLIC_KEY

    if not str(UPDATE_SIGNING_PUBLIC_KEY or "").strip():
        raise SigningError(
            "app_metadata.UPDATE_SIGNING_PUBLIC_KEY tanimli degil. "
            "--public-key ile acik anahtar verin."
        )
    return str(UPDATE_SIGNING_PUBLIC_KEY)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="HYDRO guncelleme paketleri icin Ed25519 anahtar/imza araci.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser("generate", help="Ed25519 anahtar cifti uretir")
    generate.add_argument("--key", help=f"Ozel anahtar yolu (varsayilan: {DEFAULT_KEY_PATH})")
    generate.add_argument(
        "--force",
        action="store_true",
        help="Mevcut anahtarin uzerine yaz (eski imzalar gecersiz olur)",
    )
    generate.set_defaults(handler=command_generate)

    sign = subparsers.add_parser("sign", help="Artefakt icin .sig dosyasi uretir")
    sign.add_argument("artifact", help="Imzalanacak dosya (.zip, .exe, .dmg)")
    sign.add_argument("--key", help="Ozel anahtar yolu")
    sign.add_argument("--output", help="Imza dosyasi yolu (varsayilan: <artefakt>.sig)")
    sign.set_defaults(handler=command_sign)

    verify = subparsers.add_parser("verify", help="Detached imzayi dogrular")
    verify.add_argument("artifact", help="Dogrulanacak dosya")
    verify.add_argument(
        "signature",
        nargs="?",
        help="Imza dosyasi (varsayilan: <artefakt>.sig)",
    )
    verify.add_argument("--key", help="Ozel anahtar yolu (public key bundan turetilir)")
    verify.add_argument(
        "--public-key", help="Base64 Ed25519 public key (gomulu anahtari gecersiz kilar)"
    )
    verify.set_defaults(handler=command_verify)

    fingerprint_parser = subparsers.add_parser("fingerprint", help="Anahtar parmak izini yazdirir")
    fingerprint_parser.add_argument("--key", help="Ozel anahtar yolu")
    fingerprint_parser.add_argument("--public-key", help="Base64 Ed25519 public key")
    fingerprint_parser.set_defaults(handler=command_fingerprint)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except SigningError as exc:
        print(f"HATA: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        print("Iptal edildi.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
