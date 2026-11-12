# Feuille de route et suivi du développement

Mise à jour à chaque étape. Référence : [cahier des charges](cahier-des-charges.md),
sections 15 (MVP) et 17 (plan de développement).

## Vue d'ensemble

| Phase | Contenu | État |
|---|---|---|
| 1. Fondations | Backend, base de données, authentification, première interface | ✅ Terminée (v0.1.0) |
| 2. Intelligence financière | Import de factures, extraction, calculs, graphiques, anomalies | ✅ Terminée (v0.2.0) |
| 3. IA | Ollama + Qwen, conseiller conversationnel, recommandations justifiées | ⏭️ Prochaine |
| 4. Exécution | Moteur d'actions, niveaux 1/2/3, validations, journal des actions | À faire |
| 5. Connecteurs | Socle de connecteurs, première intégration comptable/bancaire | À faire |
| 6. Industrialisation | Mini-PC, durcissement, mises à jour signées, sauvegardes, pilote | À faire |

## Avancement du MVP (cahier des charges, §15)

| # | Exigence | État |
|---|---|---|
| 1 | Installation du logiciel sur un ordinateur Linux | 🟡 Docker Compose prêt, à éprouver sur machine réelle |
| 2 | Interface professionnelle avec authentification | ✅ |
| 3 | Gestion des entreprises et utilisateurs | ✅ |
| 4 | Importation de factures PDF | ✅ PDF, scans et photos, par lots |
| 5 | Extraction locale des données | ✅ Texte PDF + OCR Tesseract, contrôle croisé des montants |
| 6 | Base PostgreSQL locale | ✅ |
| 7 | Tableau de bord financier | ✅ |
| 8 | Analyse des charges et revenus | ✅ Compte de résultat mensuel, EBE, ratios de restauration |
| 9 | Détection des anomalies simples | ✅ 8 détecteurs justifiés et chiffrés |
| 10 | Prévision de trésorerie | ✅ 90 jours, composantes connues et estimées séparées |
| 11 | Conseiller IA local | — |
| 12 | Système de recommandations | 🟡 Pistes d'action par alerte ; recommandations rédigées par l'IA en phase 3 |
| 13 | Historique des analyses | 🟡 Analyses recalculées à la demande et reproductibles ; décisions sur les alertes historisées ; instantanés datés à faire |
| 14 | Gestion des permissions | 🟡 Rôles utilisateurs faits ; permissions des actions IA en phase 4 |
| 15 | Premier système d'exécution d'actions contrôlées | — |

## Journal

### 12 novembre 2026 — v0.2.0, Phase 2 terminée

Livré :
- **Lecture des factures sur le boîtier** : texte des PDF (avec repérage des colonnes), OCR
  Tesseract en français pour les scans et les photos. Sont extraits : le sens (achat ou
  vente), le tiers, le SIREN, le numéro, les dates, le HT, la TVA par taux, le TTC et les
  lignes d'articles.
- **Fiabilité champ par champ** : un montant n'est « vérifié » que s'il se recoupe
  (HT + TVA = TTC, somme des lignes = HT). Sinon il est « estimé », « manquant » ou
  « incohérent ». Une facture qui ne se recoupe pas passe « à vérifier ».
- **Doublons** : un même fichier importé deux fois est refusé grâce à son empreinte. Une
  même facture reçue deux fois (même tiers, même numéro) est écartée des calculs.
- **Imports CSV** : relevé bancaire et journal de caisse. Ils sont tolérants aux variantes
  d'export (séparateur, encodage, débit/crédit séparés ou montant signé, lignes d'en-tête).
  Réimporter un fichier ne crée pas de doublon.
- **Rapprochement automatique** des paiements et des factures, catégorisation des
  opérations bancaires, apprentissage de la catégorie par fournisseur.
- **Moteur de calcul** déterministe : compte de résultat mensuel, EBE, coût matière
  cuisine et boissons, masse salariale, ticket moyen, couverts. Chaque indicateur expose
  sa formule, ses données d'entrée (avec un lien vers les documents) et sa fiabilité.
- **Prévision de trésorerie** à 90 jours. Elle combine les factures à payer et à encaisser,
  les charges récurrentes détectées, les recettes moyennes et les achats futurs des
  fournisseurs réguliers, avec un seuil de vigilance expliqué.
- **8 détecteurs d'anomalies**, chacun avec preuves, calcul et piste d'action : dérive du
  coût matière, hausse de prix d'un article, facture impayée, abonnements en double,
  facture inhabituelle, paiement sans facture, doublon, tension de trésorerie. Les
  décisions (traitée, ignorée) sont historisées.
- **Interface** : tableau de bord, alertes, trésorerie, données (dépôt de centaines de
  fichiers en une fois) et écran de vérification d'une facture à côté de son original.
  Graphiques en SVG sans bibliothèque externe, palette validée pour le daltonisme, mode
  sombre, smartphone.
- **Restaurant de démonstration** « Le Bistrot des Tilleuls » : voir [demo.md](demo.md).

Décisions prises :
- Restaurant comme premier secteur de démonstration. Ses ventes viennent du journal de
  caisse et non de factures, d'où trois sources de données plutôt qu'une seule.
- Ventes, achats et charges sont rattachés au mois de la facture ou de la journée de
  caisse (logique d'engagement). Les charges connues seulement par la banque (salaires,
  loyer, cotisations) sont rattachées au mois du paiement.
- Les remboursements d'emprunt, la TVA, l'impôt sur les sociétés, les investissements et
  les mouvements du compte courant d'associé n'entrent pas dans l'EBE.
- L'aperçu des documents est rendu en image sur le boîtier : il s'affiche dans tous les
  navigateurs, y compris sur smartphone.

Vérifié : 65 tests automatisés, dont un parcours complet sur les 345 documents de
démonstration ; lecture exacte des 320 factures de démonstration (OCR compris) ; parcours
dans un vrai navigateur, sur ordinateur et sur smartphone, sans aucune requête externe.

Limites connues, à traiter ensuite :
- La précision de lecture n'a été mesurée que sur des factures générées pour la
  démonstration. **Il faut constituer un corpus de vraies factures anonymisées** pour la
  mesurer en conditions réelles.
- Sans inventaire de stock, le coût matière est approché par les achats du mois.
- La prévision de trésorerie ne tient pas compte de la saisonnalité.
- Un paiement qui règle plusieurs factures à la fois n'est pas encore rapproché.
- Les lignes d'articles ne sont pas modifiables dans l'écran de vérification.
- Le chiffrement du disque reste à mettre en place au niveau du système (phase 6).
- Le `docker compose` n'a toujours pas été testé sur une vraie machine.

### Prochaine étape — Phase 3 (IA locale)

1. Service d'IA interchangeable (Ollama + Qwen 2.5 7B par défaut), désactivable.
2. Conseiller conversationnel : l'IA reçoit les résultats du moteur de calcul (indicateurs,
   alertes, sources), jamais les données brutes en vrac. Elle explique et cite ses sources.
3. Recommandations rédigées à partir des alertes, avec les incertitudes affichées.
4. Garde-fou : toute affirmation chiffrée de l'IA doit provenir d'un résultat du moteur.

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
