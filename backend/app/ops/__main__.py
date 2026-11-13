"""Outils d'exploitation du boîtier.

    python -m app.ops cle-sauvegarde          crée la clé de récupération (une seule fois)
    python -m app.ops sauvegarder             crée une sauvegarde chiffrée maintenant
    python -m app.ops sauvegardes             liste les sauvegardes
    python -m app.ops verifier FICHIER        déchiffre et contrôle une sauvegarde
    python -m app.ops restaurer FICHIER       remplace la base et les documents (avec confirmation)

    python -m app.ops editeur-cle SORTIE      crée la paire de clés de l'éditeur (poste éditeur)
    python -m app.ops signer VERSION CLE SORTIE FICHIERS…   construit un paquet signé
    python -m app.ops verifier-maj PAQUET [--extraire DOSSIER]   vérifie un paquet

La clé de récupération est demandée à la saisie (ou BAB_RECOVERY_KEY) : jamais en argument,
pour qu'elle n'apparaisse pas dans l'historique du terminal.
"""

import argparse
import getpass
import os
import sys
from pathlib import Path

from app.ops import backup, updates


def _key() -> str:
    return os.environ.get("BAB_RECOVERY_KEY") or getpass.getpass("Clé de récupération : ")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.ops")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("cle-sauvegarde")
    sub.add_parser("sauvegarder")
    sub.add_parser("sauvegardes")
    v = sub.add_parser("verifier")
    v.add_argument("fichier", type=Path)
    r = sub.add_parser("restaurer")
    r.add_argument("fichier", type=Path)
    r.add_argument("--oui", action="store_true", help="ne pas demander de confirmation")
    k = sub.add_parser("editeur-cle")
    k.add_argument("sortie", type=Path)
    s = sub.add_parser("signer")
    s.add_argument("version")
    s.add_argument("cle", type=Path)
    s.add_argument("sortie", type=Path)
    s.add_argument("fichiers", type=Path, nargs="+")
    s.add_argument("--notes", default="")
    m = sub.add_parser("verifier-maj")
    m.add_argument("paquet", type=Path)
    m.add_argument("--extraire", type=Path)
    m.add_argument("--version-installee")
    args = parser.parse_args()

    try:
        if args.cmd == "cle-sauvegarde":
            if backup.public_key_path().exists():
                sys.exit(
                    "Une clé existe déjà. La remplacer rendrait les anciennes sauvegardes inutilisables avec la nouvelle clé."
                )
            key = backup.create_recovery_key()
            print("Clé de récupération — à imprimer et conserver hors du boîtier. Elle ne sera plus affichée :\n")
            print(f"    {key}\n")
        elif args.cmd == "sauvegarder":
            info = backup.create_backup("manual")
            print(f"Sauvegarde créée : {info.path} ({info.size // 1024} Ko)")
        elif args.cmd == "sauvegardes":
            for info in backup.list_backups():
                print(f"{info.created_at[:19]}  {info.size // 1024:>8} Ko  v{info.version}  {info.name}")
        elif args.cmd == "verifier":
            manifest = backup.verify_backup(args.fichier, _key())
            print(
                f"Sauvegarde valide : version {manifest['version']}, {manifest['files']} fichier(s), créée le {manifest['created_at'][:19]}."
            )
        elif args.cmd == "restaurer":
            if (
                not args.oui
                and input("La base et les documents actuels seront remplacés. Tapez RESTAURER : ") != "RESTAURER"
            ):
                sys.exit("Restauration annulée.")
            manifest = backup.restore_backup(args.fichier, _key())
            print(f"Restauration terminée (sauvegarde du {manifest['created_at'][:19]}). Redémarrez le service.")
        elif args.cmd == "editeur-cle":
            private, public = updates.generate_publisher_key()
            args.sortie.write_text(private)
            os.chmod(args.sortie, 0o600)
            print(
                f"Clé privée : {args.sortie} (à conserver hors ligne)\nClé publique, à installer dans app/ops/cles_editeur/ :\n{public}"
            )
        elif args.cmd == "signer":
            out = updates.build_package(args.version, args.fichiers, args.cle.read_text(), args.sortie, args.notes)
            print(f"Paquet signé : {out}")
        elif args.cmd == "verifier-maj":
            if args.extraire:
                args.extraire.mkdir(parents=True, exist_ok=True)
            kwargs = {"current": args.version_installee} if args.version_installee else {}
            manifest = updates.verify_package(args.paquet, extract_to=args.extraire, **kwargs)
            print(f"Paquet valide : version {manifest['version']}, signé par « {manifest['signer']} ».")
    except (backup.BackupError, updates.UpdateError) as exc:
        sys.exit(f"Erreur : {exc}")


if __name__ == "__main__":
    main()
