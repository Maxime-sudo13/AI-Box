# Feuille de route et suivi du développement

Mise à jour à chaque étape. Référence : [cahier des charges](cahier-des-charges.md),
sections 15 (MVP) et 17 (plan de développement).

## Vue d'ensemble

| Phase | Contenu | État |
|---|---|---|
| 1. Fondations | Backend, base de données, authentification, première interface | ✅ Terminée (v0.1.0) |
| 2. Intelligence financière | Import de factures, extraction, calculs, graphiques, anomalies | ⏭️ Prochaine |
| 3. IA | Ollama + Qwen, conseiller conversationnel, recommandations justifiées | À faire |
| 4. Exécution | Moteur d'actions, niveaux 1/2/3, validations, journal des actions | À faire |
| 5. Connecteurs | Socle de connecteurs, première intégration comptable/bancaire | À faire |
| 6. Industrialisation | Mini-PC, durcissement, mises à jour signées, sauvegardes, pilote | À faire |

## Avancement du MVP (cahier des charges, §15)

| # | Exigence | État |
|---|---|---|
| 1 | Installation du logiciel sur un ordinateur Linux | 🟡 Docker Compose prêt, à éprouver sur machine réelle |
| 2 | Interface professionnelle avec authentification | ✅ |
| 3 | Gestion des entreprises et utilisateurs | ✅ |
| 4 | Importation de factures PDF | — |
| 5 | Extraction locale des données | — |
| 6 | Base PostgreSQL locale | ✅ |
| 7 | Tableau de bord financier | — |
| 8 | Analyse des charges et revenus | — |
| 9 | Détection des anomalies simples | — |
| 10 | Prévision de trésorerie | — |
| 11 | Conseiller IA local | — |
| 12 | Système de recommandations | — |
| 13 | Historique des analyses | — |
| 14 | Gestion des permissions | 🟡 Rôles utilisateurs faits ; permissions des actions IA en phase 4 |
| 15 | Premier système d'exécution d'actions contrôlées | — |

## Journal

### 12 novembre 2026 — v0.1.0, Phase 1 terminée

Livré :
- Cahier des charges versionné dans `docs/`.
- API FastAPI + PostgreSQL avec migrations Alembic.
- Assistant de première installation (administrateur, entreprise, modules), exécutable une
  seule fois, protégé contre deux installations simultanées.
- Authentification : mots de passe Argon2 (12 caractères minimum), cookie de session
  `HttpOnly`/`SameSite=Strict`, seule l'empreinte du jeton est stockée, verrouillage
  15 minutes après 5 échecs, révocation des autres sessions au changement de mot de passe.
- Rôles par entreprise (Dirigeant, Gestionnaire, Lecture seule) et administrateur du
  boîtier ; impossible de supprimer le dernier administrateur.
- Catalogue des 10 modules du cahier des charges, activables par entreprise.
- Journal d'activité consultable et paginé, incluant les accès refusés.
- Interface React responsive en français, sans aucune requête externe (vérifié).
- Déploiement Docker Compose + Caddy (HTTPS interne, en-têtes de sécurité, CSP stricte).

Vérifié : 27 tests automatisés de l'API ; parcours complet dans un navigateur réel
(installation, création d'utilisateur, accès en lecture seule, désactivation d'un compte,
journal, affichage smartphone).

Non vérifié : le `docker compose` n'a pas pu être lancé dans l'environnement de
développement (pas de démon Docker) ; à tester sur le PC de développement.

Points ouverts :
- Choisir le jeu de données de l'entreprise fictive de démonstration (secteur, volume de
  factures) pour la Phase 2.
- Le réseau Docker interne bloque tout accès sortant de l'API : en Phase 3, Ollama devra
  tourner dans un conteneur sur ce même réseau interne (pas sur l'hôte).

### Prochaine étape — Phase 2

1. Modèle de données financières : tiers (clients/fournisseurs), factures, lignes, paiements.
2. Import de PDF individuels et par lots, stockage local des originaux, détection des doublons.
3. Extraction locale (texte PDF, puis OCR pour les scans) : montants HT/TVA/TTC, dates, tiers.
4. Écran de vérification des données extraites (confirmées / estimées / manquantes).
5. Moteur de calcul classique : chiffre d'affaires, charges, marge, trésorerie prévisionnelle.
6. Génération d'une entreprise fictive avec ses factures pour la démonstration.
