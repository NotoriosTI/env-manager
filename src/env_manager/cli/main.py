"""Punto de entrada único de la CLI: ``env-manager <acción> [opciones]``.

Blueprint §1.7: el comando visible lleva el nombre de la aplicación y las
acciones son subcomandos, no binarios con guion. Los resultados van a stdout,
el diagnóstico a stderr y cada categoría de error tiene un exit code estable
(ver ``exit_codes.py``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

from env_manager.cli import exit_codes

PROG = "env-manager"


class _Parser(argparse.ArgumentParser):
    """ArgumentParser cuyo error de uso sale con el código del contrato.

    argparse sale con 2 por defecto, que en este contrato significa "error de
    operación". §1.7 pide exit codes estables por categoría, así que el error de
    uso tiene que salir con USAGE en los dos runtimes.
    """

    def error(self, message: str) -> "NoReturn":  # type: ignore[valid-type]
        self.print_usage(sys.stderr)
        print(f"Error: {message}", file=sys.stderr)
        sys.exit(exit_codes.USAGE)


def _emit(payload: dict[str, Any], lines: Sequence[str], as_json: bool) -> None:
    """Print the result to stdout, as JSON or as human-readable text."""

    if as_json:
        print(json.dumps(payload, sort_keys=True, indent=2))
        return
    for line in lines:
        print(line)


def _fail(message: str, code: int) -> "NoReturn":  # type: ignore[valid-type]
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(code)


def _add_format_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format for stdout (default: text)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog=PROG,
        description="Environment-aware configuration loader for Notorios apps.",
    )
    parser.add_argument("--version", action="store_true", help="Print the version and exit")

    subparsers = parser.add_subparsers(dest="action", metavar="<acción>", parser_class=_Parser)

    encrypt = subparsers.add_parser(
        "encrypt",
        help="Encrypt a .env file using dotenvx-compatible ECIES encryption",
    )
    encrypt.add_argument("file", help="Path to the .env file to encrypt")
    encrypt.add_argument(
        "-o",
        "--output",
        default=None,
        metavar="OUTPUT",
        help="Write encrypted output here instead of modifying the input in place",
    )
    encrypt.add_argument(
        "--env",
        default=None,
        help="Environment name (writes DOTENV_PRIVATE_KEY_<NAME> in .env.keys)",
    )
    encrypt.add_argument(
        "--force", action="store_true", help="Overwrite an existing .env.keys file"
    )
    _add_format_flag(encrypt)

    decrypt = subparsers.add_parser(
        "decrypt",
        help="Decrypt an encrypted .env file back to plaintext",
    )
    decrypt.add_argument("file", help="Path to the encrypted .env file")
    decrypt.add_argument(
        "--env",
        default=None,
        help="Environment name (reads DOTENV_PRIVATE_KEY_<NAME> from .env.keys)",
    )
    decrypt.add_argument(
        "--key", default=None, help="Private key hex (skips the .env.keys lookup)"
    )
    decrypt.add_argument(
        "-o",
        "--output",
        default=None,
        metavar="OUTPUT",
        help="Write decrypted output here instead of modifying the input in place",
    )
    _add_format_flag(decrypt)

    secrets = subparsers.add_parser(
        "secrets",
        help="Operate the app's consolidated JSON secret in Secret Manager",
    )
    secrets_sub = secrets.add_subparsers(dest="secrets_action", metavar="<sub-acción>",
                                         parser_class=_Parser)

    secrets_list = secrets_sub.add_parser(
        "list", help="List the key names in the consolidated secret (never values)"
    )
    secrets_list.add_argument("secret", help="Consolidated secret name, e.g. <app>-config")
    secrets_list.add_argument("--project", required=True, help="GCP project id")
    _add_format_flag(secrets_list)

    secrets_set = secrets_sub.add_parser(
        "set",
        help=(
            "Set one key, adding a new version and destroying the previous one. "
            "The value is read from stdin, never from argv."
        ),
    )
    secrets_set.add_argument("secret", help="Consolidated secret name, e.g. <app>-config")
    secrets_set.add_argument("--key", required=True, help="Key name inside the JSON payload")
    secrets_set.add_argument("--project", required=True, help="GCP project id")
    _add_format_flag(secrets_set)

    return parser


def _run_encrypt(args: argparse.Namespace) -> None:
    from env_manager.cli.encrypt import encrypt_dotenv_file

    try:
        encrypt_dotenv_file(
            args.file,
            output_path=args.output,
            env_name=args.env,
            force=args.force,
        )
    except ImportError as exc:
        _fail(str(exc), exit_codes.DEPENDENCY)
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        _fail(str(exc), exit_codes.OPERATION)

    out = args.output or args.file
    keys_path = Path(out).parent / ".env.keys"
    _emit(
        {"action": "encrypt", "input": args.file, "output": out, "keys": str(keys_path)},
        [f"Encrypted {args.file} -> {out}", f"Private key written to {keys_path}"],
        args.format == "json",
    )


def _run_decrypt(args: argparse.Namespace) -> None:
    from env_manager.cli.decrypt import decrypt_dotenv_file

    try:
        decrypted, skipped = decrypt_dotenv_file(
            args.file,
            private_key_hex=args.key,
            output_path=args.output,
            env_name=args.env,
        )
    except ImportError as exc:
        _fail(str(exc), exit_codes.DEPENDENCY)
    except (FileNotFoundError, ValueError) as exc:
        _fail(str(exc), exit_codes.OPERATION)
    except Exception as exc:  # descifrado fallido: clave equivocada, payload roto
        _fail(f"Decryption failed: {exc}", exit_codes.OPERATION)

    out = args.output or args.file
    _emit(
        {
            "action": "decrypt",
            "input": args.file,
            "output": out,
            "decrypted": decrypted,
            "skipped": skipped,
        },
        [f"Decrypted {decrypted} value(s), skipped {skipped} plaintext value(s)"],
        args.format == "json",
    )


def _run_secrets(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    from env_manager.cli import secrets as secrets_module

    if args.secrets_action is None:
        print("Error: 'secrets' needs a sub-action: list or set", file=sys.stderr)
        parser.print_help(sys.stderr)
        sys.exit(exit_codes.USAGE)

    try:
        if args.secrets_action == "list":
            keys = secrets_module.list_keys(args.project, args.secret)
            _emit(
                {"action": "secrets.list", "secret": args.secret, "keys": keys},
                [f"{len(keys)} key(s) in '{args.secret}':", *(f"  {k}" for k in keys)],
                args.format == "json",
            )
            return

        value = secrets_module.read_value_from_stdin()
        result = secrets_module.set_key(args.project, args.secret, args.key, value)
    except secrets_module.SecretDestroyError as exc:
        _fail(str(exc), exit_codes.REMOTE)
    except secrets_module.SecretsError as exc:
        _fail(str(exc), exit_codes.OPERATION)
    except Exception as exc:  # noqa: BLE001 - todo lo remoto cae acá
        _fail(f"Secret Manager call failed: {exc}", exit_codes.REMOTE)

    if result["unchanged"]:
        lines = [f"'{args.key}' already had that value in '{args.secret}'. No new version created."]
    else:
        lines = [
            f"Set '{args.key}' in '{args.secret}'.",
            f"Created {result['created_version']}",
            f"Destroyed {len(result['destroyed_versions'])} previous version(s)",
        ]
    _emit({"action": "secrets.set", **result}, lines, args.format == "json")


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if getattr(args, "version", False):
        from env_manager import __version__

        print(__version__)
        sys.exit(exit_codes.OK)

    if args.action is None:
        parser.print_help(sys.stderr)
        sys.exit(exit_codes.USAGE)

    if args.action == "encrypt":
        _run_encrypt(args)
    elif args.action == "decrypt":
        _run_decrypt(args)
    elif args.action == "secrets":
        _run_secrets(args, parser)

    sys.exit(exit_codes.OK)


if __name__ == "__main__":
    main()
