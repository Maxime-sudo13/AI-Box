#!/bin/bash
# Business AI Box — installation sur un mini-PC Debian 12/13 ou Ubuntu Server 22.04/24.04.
#
# Prérequis : système installé avec le disque chiffré (choix « LVM chiffré » de l'installateur),
# connexion Internet pendant l'installation, ce dépôt copié sur la machine.
# Usage :   sudo ./deploy/installer/installer-boitier.sh [--sans-chiffrement] [--nom businessaibox]
set -euo pipefail

INSTALL_DIR=/opt/business-ai-box
DEPOT_DIR=/srv/depot
BACKUP_DIR=/mnt/sauvegarde
APP_UID=10001
HOSTNAME_BOX=businessaibox
ALLOW_UNENCRYPTED=0
SOURCE_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

while [ $# -gt 0 ]; do
  case "$1" in
    --sans-chiffrement) ALLOW_UNENCRYPTED=1 ;;
    --nom) HOSTNAME_BOX="$2"; shift ;;
    *) echo "Option inconnue : $1" >&2; exit 2 ;;
  esac
  shift
done

etape() { printf '\n\033[1m== %s\033[0m\n' "$1"; }
stop() { printf '\033[31mArrêt : %s\033[0m\n' "$1" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || stop "lancez ce script avec sudo."
# shellcheck source=/dev/null
. /etc/os-release
case "$ID" in debian|ubuntu) ;; *) stop "système non pris en charge ($ID) : Debian ou Ubuntu requis." ;; esac

etape "1. Chiffrement du disque"
if lsblk -no TYPE | grep -q crypt; then
  echo "Disque chiffré détecté (LUKS)."
elif [ "$ALLOW_UNENCRYPTED" -eq 1 ]; then
  echo "ATTENTION : disque non chiffré (--sans-chiffrement). À réserver aux machines de test."
else
  stop "le disque n'est pas chiffré. Réinstallez le système avec « LVM chiffré », ou relancez avec --sans-chiffrement pour un test."
fi

etape "2. Paquets système"
apt-get update -q
apt-get install -y -q ca-certificates curl gnupg ufw unattended-upgrades avahi-daemon wireguard-tools qrencode openssl
install -m 0755 -d /etc/apt/keyrings
if [ ! -f /etc/apt/keyrings/docker.asc ]; then
  curl -fsSL "https://download.docker.com/linux/${ID}/gpg" -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
fi
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/${ID} ${VERSION_CODENAME} stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update -q
apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-compose-plugin
systemctl enable --now docker
# Mises à jour de sécurité du système appliquées automatiquement.
dpkg-reconfigure -f noninteractive unattended-upgrades

etape "3. Fichiers de l'application"
mkdir -p "$INSTALL_DIR"
for part in backend frontend deploy README.md; do
  cp -a "$SOURCE_DIR/$part" "$INSTALL_DIR/"
done
mkdir -p "$DEPOT_DIR" "$BACKUP_DIR"
chown "$APP_UID" "$DEPOT_DIR" "$BACKUP_DIR"
if ! mountpoint -q "$BACKUP_DIR"; then
  echo "ATTENTION : $BACKUP_DIR n'est pas un support distinct. Montez-y un disque USB ou un partage NAS"
  echo "(voir docs/industrialisation.md), sinon les sauvegardes resteront sur le disque du boîtier."
fi

etape "4. Configuration"
ENV_FILE="$INSTALL_DIR/deploy/.env"
if [ ! -f "$ENV_FILE" ]; then
  umask 077
  cat > "$ENV_FILE" <<CONF
BAB_DB_PASSWORD=$(openssl rand -hex 24)
BAB_SECRET_KEY=$(openssl rand -base64 32)
BAB_HOSTNAME=${HOSTNAME_BOX}.local
BAB_OFFLINE_MODE=true
BAB_DEPOT_DIR=$DEPOT_DIR
BAB_BACKUP_MEDIUM=$BACKUP_DIR
BAB_AI_MODEL=qwen2.5:7b
BAB_VERSION=dev
CONF
  echo "Fichier $ENV_FILE créé (secrets générés, lisible par root uniquement)."
else
  echo "Configuration existante conservée."
fi
hostnamectl set-hostname "$HOSTNAME_BOX"
systemctl enable --now avahi-daemon
echo "Le boîtier sera joignable sur https://${HOSTNAME_BOX}.local"

etape "5. Pare-feu"
ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
for net in 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16; do
  ufw allow from "$net" to any port 443 proto tcp
  ufw allow from "$net" to any port 80 proto tcp
  ufw allow from "$net" to any port 22 proto tcp
done
ufw --force enable
echo "Seul le réseau local de l'entreprise peut joindre le boîtier ; rien n'est exposé sur Internet."

etape "6. Service au démarrage"
cat > /etc/systemd/system/business-ai-box.service <<UNIT
[Unit]
Description=Business AI Box
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$INSTALL_DIR/deploy
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload

etape "7. Construction et démarrage (10 à 20 minutes la première fois)"
cd "$INSTALL_DIR/deploy"
docker compose build
systemctl enable --now business-ai-box.service

etape "Installation terminée"
cat <<FIN
Étapes suivantes :
  1. Ouvrez https://${HOSTNAME_BOX}.local depuis un poste du réseau et créez le compte administrateur.
  2. Paramètres › Système : créez la clé de récupération des sauvegardes et rangez-la hors du boîtier.
  3. Modèle d'IA : $INSTALL_DIR/deploy/telecharger-modele.sh qwen2.5:7b
  4. Clé publique de l'éditeur (mises à jour signées) : copiez le fichier .pub fourni dans
     $INSTALL_DIR/backend/app/ops/cles_editeur/ puis : cd $INSTALL_DIR/deploy && docker compose build api && docker compose up -d
  5. Accès distant (facultatif) : sudo $INSTALL_DIR/deploy/installer/acces-distant.sh ajouter mon-telephone
FIN
