# Industrialisation : installer, sauvegarder, mettre à jour, surveiller

Ce document décrit l'exploitation d'un boîtier chez un client. Tout ce qui est décrit ici est
livré ; ce qui n'a pas encore pu être exécuté sur un vrai mini-PC est signalé.

## 1. Matériel et dimensionnement

Mesures du 12 novembre 2026, installation Docker complète, 4 cœurs partagés, restaurant de
démonstration (12 mois, 345 documents, 720 opérations), **sans modèle d'IA** (moteur seul) :

| Utilisateurs simultanés | Requêtes/s | Écrans (95e centile) | Conseiller (95e centile) | Erreurs |
|---|---|---|---|---|
| 5 | 2,2 | < 0,2 s | 0,2 s | 0 |
| 20 | 8,8 | < 0,8 s | 1,8 s | 0 |

Reproduire : `cd backend && uv run python scripts/test_charge.py --utilisateurs 20 --duree 60`.

Conclusions :

- **L'application elle-même tient largement la charge d'une TPE ou PME** (1 à 10 personnes
  connectées en même temps) sur un mini-PC récent à 4 cœurs.
- **Le modèle d'IA dimensionne le matériel.** Une réponse rédigée fait 150 à 250 mots, soit
  300 à 500 jetons générés. Ordres de grandeur à confirmer par mesure, sur votre PC puis sur le
  mini-PC retenu :
  - sur processeur seul, Qwen 2.5 7B est lent (plusieurs dizaines de secondes par réponse) ;
  - sur une carte graphique avec 8 Go de mémoire, ou une puce à mémoire unifiée, il faut
    compter quelques secondes à une dizaine de secondes.
- **Starter** (16 Go de RAM, sans carte graphique) : convient si l'on accepte un conseiller
  lent, ou avec un modèle plus petit (Qwen 2.5 3B, à évaluer avec le contrôle des chiffres).
- **Professional** (32 Go de RAM, carte graphique ou mémoire unifiée) : la configuration
  recommandée pour un conseiller fluide.
- Les réponses du moteur ne dépendent pas du modèle : un boîtier sans IA reste utilisable.

## 2. Installer un boîtier

1. Installer **Debian 12/13 ou Ubuntu Server 24.04** en choisissant « LVM chiffré » : le
   disque entier est chiffré (LUKS) et la phrase de passe est demandée au démarrage.
   Cela répond à l'exigence « chiffrement des disques » du cahier des charges.
2. Copier ce dépôt sur la machine (clé USB ou `git clone`), puis :
   `sudo ./deploy/installer/installer-boitier.sh`
   Le script :
   - vérifie le chiffrement du disque ;
   - installe Docker, le pare-feu, les mises à jour de sécurité automatiques et la
     découverte réseau (`businessaibox.local`) ;
   - génère les secrets ;
   - n'ouvre les ports qu'au réseau local ;
   - crée le service de démarrage, puis construit et lance l'application.
3. Brancher le **support de sauvegarde** (disque USB) et le monter sur `/mnt/sauvegarde` de
   façon permanente (ligne dans `/etc/fstab` avec l'option `nofail`).
4. Depuis un poste du réseau : `https://businessaibox.local`. Créer le compte
   administrateur, puis, dans **Paramètres › Système**, créer la clé de récupération.
5. Télécharger le modèle d'IA : `/opt/business-ai-box/deploy/telecharger-modele.sh`.

> Non exécuté à ce jour sur un mini-PC (pas encore de matériel). Le script a été vérifié par
> analyse statique (shellcheck) ; à dérouler une première fois sur une machine de test.

**Déblocage du disque chiffré au démarrage** : par défaut, il faut saisir la phrase de passe
à chaque démarrage (clavier branché). Pour un redémarrage sans intervention, une option est
de lier le déchiffrement à la puce TPM du mini-PC (`systemd-cryptenroll --tpm2-device=auto`).
C'est un compromis : le disque reste protégé s'il est retiré, mais pas si le boîtier entier
est volé. À décider avec chaque client.

## 3. Sauvegardes

- **Quotidiennes** (2 h 30 UTC), plus à la demande depuis **Système** ou avant chaque mise à
  jour. Les 14 dernières sont conservées.
- **Contenu** : la base complète, les documents originaux, les ordres de virement et la clé de
  chiffrement des identifiants des connecteurs.
- **Chiffrement asymétrique** :
  - le boîtier ne détient qu'une clé publique : il peut créer des sauvegardes mais pas les
    relire ;
  - seule la **clé de récupération**, affichée une seule fois et imprimée par le dirigeant,
    permet de les déchiffrer ;
  - un disque de sauvegarde volé, même avec le boîtier, reste donc illisible.
- **Contrôle** : depuis **Système › Vérifier**, la sauvegarde est entièrement déchiffrée et
  contrôlée sans rien modifier. À faire après l'installation, puis une fois par trimestre.
- **Copie hors site** : depuis **Système › Télécharger**. Le fichier reste chiffré et peut être
  confié à l'expert-comptable ou stocké ailleurs sans risque.

### Restaurer

La restauration remplace toutes les données. Elle se fait depuis la console du boîtier :

```bash
cd /opt/business-ai-box/deploy
docker compose stop web                       # plus personne ne peut se connecter
docker compose exec api python -m app.ops sauvegardes
docker compose exec api python -m app.ops restaurer /sauvegardes/business-ai-box-AAAAMMJJ-HHMMSS.babk
# saisir la clé de récupération, puis taper RESTAURER
docker compose restart api && docker compose start web
```

Ce cycle (sauvegarde, sinistre simulé, restauration, vérification des comptes, des
entreprises et des documents) est couvert par un test automatisé.

**Sur un nouveau matériel** (boîtier détruit) :

1. Installer le boîtier comme au §2.
2. Copier le fichier `.babk` sur le support de sauvegarde.
3. Restaurer comme ci-dessus.

La clé de chiffrement des connecteurs étant incluse dans la sauvegarde, les connexions
reprennent sans ressaisie.

## 4. Mises à jour signées

Côté éditeur, une seule fois :

```bash
python -m app.ops editeur-cle ~/cle-editeur.pem
```

- La clé **privée** ne quitte jamais le poste de l'éditeur ; à conserver hors ligne, avec une
  copie de secours.
- La clé **publique** affichée est installée sur chaque boîtier, dans
  `backend/app/ops/cles_editeur/editeur.pub`.

Publier une version :

```bash
./deploy/editeur/construire-paquet.sh 0.6.0 ~/cle-editeur.pem   # → dist/business-ai-box-0.6.0.babmaj
```

Installer chez le client (clé USB ou téléchargement) :

```bash
sudo /opt/business-ai-box/deploy/mettre-a-jour.sh /media/usb/business-ai-box-0.6.0.babmaj
```

Le script :

1. vérifie la signature et l'empreinte de chaque fichier, et refuse tout retour à une version
   antérieure ;
2. sauvegarde les données ;
3. charge les nouvelles images ;
4. redémarre ;
5. contrôle la santé du boîtier, puis **revient automatiquement à la version précédente** si le
   boîtier ne répond pas.

Aucune donnée n'est envoyée à l'éditeur. Les migrations de base s'appliquent au démarrage.

> La vérification des paquets (signature, empreintes, paquet trafiqué, mauvaise clé, retour en
> arrière) est couverte par des tests. L'enchaînement complet du script sur un boîtier reste à
> exécuter une première fois en conditions réelles.

## 5. Accès distant

```bash
sudo /opt/business-ai-box/deploy/installer/acces-distant.sh ajouter telephone-dirigeant
```

- Le premier appareil initialise le VPN WireGuard. Seul le port UDP 51820 est ouvert : à
  rediriger vers le boîtier sur la box Internet.
- Chaque appareil reçoit sa propre clé, sous forme de QR code à scanner avec l'application
  WireGuard.
- `retirer` révoque un appareil (téléphone perdu, départ d'un salarié).
- Le client garde la maîtrise de la configuration : l'éditeur n'a pas d'accès permanent.

## 6. Surveillance

**Paramètres › Système** affiche :

- la version et la révision de la base ;
- l'état de l'IA et le mode de communication ;
- l'espace disque, la taille de la base et des documents ;
- les tâches planifiées ;
- l'état des sauvegardes : support distinct ou non, dernière sauvegarde automatique,
  prochaine prévue ;
- le nombre de clés d'éditeur installées.

Des avertissements apparaissent en tête de page :

- pas de clé de sauvegarde ;
- sauvegardes sur le même disque que les données ;
- échec de la dernière sauvegarde ;
- disque presque plein ;
- connexion de logiciel en erreur.

Les journaux techniques restent sur le boîtier : `docker compose logs api`.
