#!/bin/bash
# Accès distant au boîtier par WireGuard (VPN), configuration contrôlée par le client.
# Le boîtier n'est jamais exposé directement : seul le port UDP du VPN est ouvert, et seuls
# les appareils déclarés ici peuvent s'y connecter.
#
#   sudo ./acces-distant.sh ajouter NOM-APPAREIL   ajoute un appareil, affiche son QR code
#   sudo ./acces-distant.sh liste                  appareils autorisés
#   sudo ./acces-distant.sh retirer NOM-APPAREIL   révoque un appareil
set -euo pipefail

WG_DIR=/etc/wireguard
CONF="$WG_DIR/wg-bab.conf"
PEERS="$WG_DIR/appareils-bab"
PORT="${BAB_WG_PORT:-51820}"
NET="10.77.0"

[ "$(id -u)" -eq 0 ] || { echo "Lancez avec sudo." >&2; exit 1; }
command -v wg >/dev/null || { echo "wireguard-tools manquant (apt install wireguard-tools)." >&2; exit 1; }
mkdir -p "$PEERS"
chmod 700 "$WG_DIR" "$PEERS"

init_server() {
  [ -f "$CONF" ] && return
  umask 077
  wg genkey > "$WG_DIR/serveur.key"
  wg pubkey < "$WG_DIR/serveur.key" > "$WG_DIR/serveur.pub"
  cat > "$CONF" <<SRV
[Interface]
Address = ${NET}.1/24
ListenPort = ${PORT}
PrivateKey = $(cat "$WG_DIR/serveur.key")
SRV
  ufw allow "${PORT}/udp" >/dev/null
  # Les appareils du VPN accèdent à l'interface web du boîtier, et à rien d'autre.
  ufw allow from "${NET}.0/24" to any port 443 proto tcp >/dev/null
  systemctl enable --now "wg-quick@wg-bab"
  echo "Serveur VPN initialisé. Sur votre box Internet, redirigez le port UDP ${PORT} vers ce boîtier."
}

valid_name() {
  [[ "$1" =~ ^[a-zA-Z0-9_-]{1,32}$ ]] || { echo "Nom invalide (lettres, chiffres, - et _)." >&2; exit 1; }
}

case "${1:-}" in
  ajouter)
    name="${2:?Nom de l appareil manquant}"
    valid_name "$name"
    [ -f "$PEERS/$name.pub" ] && { echo "Cet appareil existe déjà." >&2; exit 1; }
    init_server
    used=$(cat "$PEERS"/*.ip 2>/dev/null | sort -n | tail -1 || true)
    ip=$(( ${used:-1} + 1 ))
    [ "$ip" -lt 250 ] || { echo "Nombre maximal d'appareils atteint." >&2; exit 1; }
    umask 077
    key=$(wg genkey)
    pub=$(echo "$key" | wg pubkey)
    echo "$pub" > "$PEERS/$name.pub"
    echo "$ip" > "$PEERS/$name.ip"
    printf '\n[Peer]\n# %s\nPublicKey = %s\nAllowedIPs = %s.%s/32\n' "$name" "$pub" "$NET" "$ip" >> "$CONF"
    wg syncconf wg-bab <(wg-quick strip wg-bab)
    endpoint="${BAB_WG_ENDPOINT:-VOTRE-ADRESSE-PUBLIQUE}:${PORT}"
    client=$(printf '[Interface]\nPrivateKey = %s\nAddress = %s.%s/32\n\n[Peer]\nPublicKey = %s\nEndpoint = %s\nAllowedIPs = %s.1/32\nPersistentKeepalive = 25\n' \
      "$key" "$NET" "$ip" "$(cat "$WG_DIR/serveur.pub")" "$endpoint" "$NET")
    echo "Configuration de « $name » (à importer dans l'application WireGuard, puis à effacer) :"
    echo "$client"
    if command -v qrencode >/dev/null; then echo "$client" | qrencode -t ansiutf8; fi
    echo "Une fois connecté, ouvrez https://${NET}.1"
    ;;
  liste)
    for f in "$PEERS"/*.pub; do
      [ -e "$f" ] && echo "$(basename "$f" .pub)  ${NET}.$(cat "${f%.pub}.ip")"
    done
    ;;
  retirer)
    name="${2:?Nom de l appareil manquant}"
    valid_name "$name"
    pub=$(cat "$PEERS/$name.pub")
    # Supprime le bloc [Peer] de l'appareil.
    awk -v n="# $name" 'BEGIN{RS="";ORS="\n\n"} index($0, n)==0' "$CONF" > "$CONF.tmp" && mv "$CONF.tmp" "$CONF"
    chmod 600 "$CONF"
    wg set wg-bab peer "$pub" remove
    rm -f -- "${PEERS:?}/${name:?}.pub" "${PEERS:?}/${name:?}.ip"
    echo "Accès de « $name » révoqué."
    ;;
  *) sed -n '2,10p' "$0"; exit 2 ;;
esac
