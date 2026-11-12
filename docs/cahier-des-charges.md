# Business AI Box — Cahier des charges V1

**Document de conception — Version 1.0 — 12 novembre 2026**

> Le cerveau numérique privé de l'entreprise.

| | |
|---|---|
| Type de produit | SaaS On-Premise |
| Cible | TPE / PME |
| Traitement IA | Local par défaut |
| Modèle économique | Boîtier + licence |

Business AI Box est un produit destiné aux TPE et PME, développé progressivement, installé chez les clients et commercialisé sous forme de boîtier physique accompagné d'une licence logicielle.

Deux décisions structurent le produit :

- **Périmètre personnalisable** : chaque entreprise choisit les domaines qu'elle souhaite connecter et surveiller.
- **Autonomie avec exécution** : l'IA ne se contente pas de conseiller. Elle peut aussi effectuer des opérations dans les logiciels connectés, selon les autorisations accordées par le dirigeant.

Règle fondamentale : l'IA peut être autonome dans les limites définies par le client, mais **les opérations sensibles doivent être soumises à validation**.

---

## 1. Vision et objectif du produit

Business AI Box est un système intelligent de gestion, d'analyse et d'optimisation d'entreprise, installé directement dans les locaux du client.

Il se connecte aux logiciels professionnels déjà utilisés par l'entreprise, récupère les informations autorisées, les centralise localement et les analyse pour produire une vision globale de son fonctionnement.

Son objectif est de permettre au dirigeant de comprendre :

- Où son entreprise gagne de l'argent.
- Où elle en perd.
- Quelles dépenses peuvent être optimisées.
- Quels clients ou fournisseurs posent problème.
- Quels produits et services sont les plus rentables.
- Quels risques financiers se profilent.
- Quelles opportunités commerciales sont inexploitées.
- Quelles actions peuvent améliorer ses performances.

L'application doit se comporter comme un directeur financier, opérationnel et stratégique virtuel.

## 2. Principes fondamentaux non négociables

### 2.1. Hébergement local

Chaque client possède son propre boîtier.

Les éléments suivants sont stockés localement :

- Documents importés.
- Factures et devis.
- Informations financières.
- Données clients et fournisseurs.
- Historique des analyses.
- Historique des recommandations.
- Historique des actions effectuées par les agents IA.
- Paramètres et autorisations.
- Base de données de l'entreprise.

Aucun de ces éléments ne doit être stocké sur un serveur appartenant à l'éditeur de Business AI Box.

### 2.2. Intelligence artificielle locale

Le système doit privilégier les modèles IA exécutés sur le boîtier.

Aucune API IA externe ne doit être nécessaire au fonctionnement normal du produit.

Une éventuelle connexion à un modèle externe pourra être ajoutée comme option facultative, avec consentement explicite et indication des informations qui seront transmises.

### 2.3. Liberté de choix

L'entreprise choisit :

- Les logiciels à connecter.
- Les données accessibles.
- Les départements à surveiller.
- Les analyses à effectuer.
- Les recommandations à recevoir.
- Les actions que l'IA est autorisée à réaliser.

### 2.4. Autonomie contrôlée

L'IA peut effectuer des opérations dans les logiciels connectés, dans les limites des autorisations données.

Toutes les opérations doivent être traçables, réversibles lorsque cela est possible et soumises à des règles de sécurité.

## 3. Architecture générale

Le produit comprend quatre éléments principaux.

### A. Le boîtier physique

Un mini-ordinateur installé chez le client et relié au réseau Ethernet de son entreprise.

Il héberge :

- Le système d'exploitation.
- Le serveur applicatif.
- La base de données.
- Les modèles d'intelligence artificielle.
- Les agents spécialisés.
- Les connecteurs logiciels.
- Le système de sécurité.
- Le tableau de bord.

### B. L'application de gestion

Une application web accessible depuis :

- Un ordinateur.
- Un smartphone.
- Une tablette.

Elle communique directement avec le boîtier sur le réseau local ou par un accès distant sécurisé.

### C. Le moteur d'intelligence artificielle

Un ensemble de modèles et d'agents spécialisés capables de comprendre les données, identifier des anomalies, produire des analyses et effectuer des opérations autorisées.

### D. Le système de connecteurs

Un ensemble de modules permettant de communiquer avec les logiciels tiers.

Chaque connecteur doit pouvoir :

- S'authentifier auprès du logiciel.
- Récupérer les informations autorisées.
- Actualiser les données.
- Détecter les changements.
- Effectuer certaines opérations lorsque les permissions le permettent.
- Signaler les erreurs de connexion.

## 4. Modules fonctionnels

Le logiciel doit être modulaire. Lors de l'installation, le dirigeant choisit les modules qui correspondent à son activité.

### Module 1 — Direction générale

Vue globale de l'entreprise.

Fonctionnalités :

- Indice de santé global.
- Synthèse financière.
- Évolution du chiffre d'affaires.
- Rentabilité.
- Évolution des charges.
- Situation des clients et fournisseurs.
- Alertes prioritaires.
- Opportunités détectées.
- Recommandations stratégiques.

Le dirigeant doit pouvoir ouvrir son application et comprendre la situation de son entreprise en moins de deux minutes.

### Module 2 — Gestion financière

Fonctionnalités :

- Analyse des revenus.
- Analyse des dépenses.
- Analyse des marges.
- Suivi des bénéfices.
- Prévision de trésorerie.
- Détection des dépenses inhabituelles.
- Comparaison des fournisseurs.
- Analyse des coûts fixes et variables.
- Suivi des factures fournisseurs.
- Suivi des factures clients.
- Détection des impayés.
- Prévision des échéances.

L'application doit pouvoir répondre à des questions comme :

- « Pourquoi mon bénéfice a-t-il diminué ce mois-ci ? »
- « Combien puis-je réellement investir actuellement ? »
- « Quelles dépenses ont augmenté anormalement ? »

### Module 3 — Comptabilité et documents

Fonctionnalités :

- Importation de PDF.
- Importation d'Excel et CSV.
- Reconnaissance automatique des factures.
- Extraction des montants, dates, TVA et fournisseurs.
- Classement automatique.
- Détection des doublons.
- Détection des documents manquants.
- Recherche dans les documents.
- Rapprochement entre factures et paiements.

L'importation doit accepter les documents individuellement ou en lots.

Les documents originaux restent sur le boîtier.

### Module 4 — Ventes et chiffre d'affaires

Fonctionnalités :

- Analyse des ventes.
- Évolution du panier moyen.
- Analyse des produits les plus rentables.
- Identification des produits peu rentables.
- Analyse des clients.
- Détection des baisses de commandes.
- Identification des opportunités de vente.
- Prévision des revenus.
- Comparaison des performances commerciales.

Exemple : l'IA remarque qu'un produit représente une grande partie des ventes, mais possède une marge particulièrement faible. Elle peut proposer une modification tarifaire et calculer son impact estimé.

### Module 5 — Clients et CRM

Fonctionnalités :

- Historique des clients.
- Segmentation.
- Analyse de la fidélisation.
- Détection des clients inactifs.
- Détection des retards de paiement.
- Préparation des relances.
- Identification des clients à fort potentiel.
- Analyse des performances commerciales.

L'agent peut préparer des emails de relance ou mettre à jour le CRM selon les autorisations accordées.

### Module 6 — Fournisseurs et achats

Fonctionnalités :

- Centralisation des fournisseurs.
- Comparaison des prix.
- Analyse des évolutions tarifaires.
- Détection des augmentations inhabituelles.
- Comparaison des conditions commerciales.
- Détection des dépendances à un fournisseur.
- Préparation des demandes de devis.
- Suggestions de renégociation.

### Module 7 — Stocks et logistique

Fonctionnalités :

- Suivi des stocks.
- Détection des stocks dormants.
- Prévision des ruptures.
- Analyse de la rotation des produits.
- Identification des produits surstockés.
- Prévision des besoins.
- Suggestions de réapprovisionnement.

L'IA pourra préparer une commande, mais son envoi devra respecter les permissions configurées.

### Module 8 — Ressources humaines

Fonctionnalités :

- Suivi des effectifs.
- Analyse des coûts salariaux.
- Suivi des absences.
- Analyse de la masse salariale.
- Suivi des heures supplémentaires.
- Analyse des coûts par service.
- Prévisions des besoins en personnel.

Ce module doit respecter des règles strictes de confidentialité et ne pas effectuer de décisions automatisées concernant les salariés.

### Module 9 — Gestion des contrats et abonnements

Fonctionnalités :

- Centralisation des contrats.
- Détection des dates de renouvellement.
- Suivi des abonnements.
- Détection des services potentiellement inutilisés.
- Alertes avant échéance.
- Analyse des dépenses récurrentes.
- Suggestions de résiliation ou renégociation.

### Module 10 — Conseiller stratégique IA

C'est le module central.

Il rassemble les analyses des différents modules et permet au dirigeant de dialoguer avec son entreprise.

Exemples de demandes :

- « Fais-moi un bilan complet de mon entreprise. »
- « Comment pourrais-je augmenter mon bénéfice de 10 % ? »
- « Où est-ce que je perds le plus d'argent ? »
- « Compare mes trois derniers mois. »
- « Quels sont mes cinq problèmes prioritaires ? »
- « Si je recrute une personne supplémentaire, quel sera l'impact financier ? »
- « Prépare un plan d'optimisation pour les 90 prochains jours. »

Chaque réponse doit être justifiée par les données disponibles, les calculs réalisés et les éventuelles incertitudes.

## 5. Le système d'agents intelligents

Le produit doit utiliser plusieurs agents spécialisés plutôt qu'un seul agent chargé de tout faire.

Agents prévus :

1. **Agent financier** : analyse la rentabilité, les charges et la trésorerie.
2. **Agent commercial** : analyse les ventes et les opportunités.
3. **Agent achats** : analyse les fournisseurs et les coûts.
4. **Agent stocks** : analyse les approvisionnements.
5. **Agent administratif** : surveille les documents et les échéances.
6. **Agent RH** : analyse les indicateurs de personnel autorisés.
7. **Agent stratégique** : rassemble les analyses et propose des plans d'action.
8. **Agent exécutif** : prépare et exécute les opérations autorisées.

Un agent central coordonne les autres.

Les agents ne doivent pas disposer d'un accès illimité à toutes les données. Ils reçoivent uniquement les informations nécessaires à leur mission.

## 6. Système d'automatisation et d'exécution

C'est une fonctionnalité différenciante du produit. L'IA doit pouvoir passer de l'analyse à l'action.

| Situation détectée | Action possible |
|---|---|
| Facture client impayée | Préparer et envoyer une relance autorisée |
| Dépense inhabituelle | Créer une alerte |
| Contrat arrivant à échéance | Préparer une demande de résiliation |
| Client inactif | Préparer une campagne de réactivation |
| Stock insuffisant | Préparer une commande |
| Devis reçu | Comparer les tarifs et préparer une réponse |
| Baisse de rentabilité | Préparer un plan d'optimisation |
| Nouveau prospect | Créer une fiche dans le CRM |

### Niveaux d'autorisation

Chaque action possède un niveau de risque.

**Niveau 1 — Automatique.** Actions sans conséquence financière ou juridique importante :

- Classement documentaire.
- Actualisation des tableaux de bord.
- Création d'alertes.
- Analyse des données.
- Préparation de rapports.
- Mise à jour de notes internes.

**Niveau 2 — Autorisation préalable.** Actions qui nécessitent une validation du dirigeant :

- Envoi d'un email externe.
- Envoi d'une relance client.
- Modification d'une fiche client.
- Modification d'un tarif.
- Envoi d'un devis.
- Création d'une commande.

**Niveau 3 — Validation renforcée.** Actions sensibles :

- Paiement.
- Virement.
- Signature de contrat.
- Déclaration fiscale.
- Modification de coordonnées bancaires.
- Embauche ou licenciement.
- Engagement financier important.

Ces opérations ne doivent jamais être exécutées par simple interprétation d'une instruction de l'IA. Elles nécessitent une authentification renforcée et une confirmation explicite.

Le dirigeant doit pouvoir modifier les permissions à tout moment.

### Journal d'activité

Chaque action doit enregistrer :

- La date et l'heure.
- L'agent responsable.
- La donnée ayant déclenché l'action.
- L'opération proposée.
- L'autorisation obtenue.
- Le résultat.
- Les éventuelles erreurs.
- La possibilité d'annuler ou de corriger l'opération.

## 7. Connecteurs logiciels

Le système doit disposer d'un catalogue de connecteurs.

Premières intégrations à étudier :

| Catégorie | Logiciels |
|---|---|
| Comptabilité | Pennylane, Sage, Cegid |
| Banque | Qonto |
| ERP | Odoo |
| CRM | HubSpot |
| Bureautique | Excel, Microsoft 365 |
| Documents | Google Drive, OneDrive |
| Gestion commerciale | Axonaut |
| E-commerce | Shopify |
| Communication | Gmail, Outlook |

Les connexions doivent privilégier les API officielles et les autorisations OAuth en lecture seule au démarrage.

Les données ne doivent pas être copiées sur un serveur de l'éditeur de Business AI Box.

> **Attention** : lorsqu'un logiciel source est lui-même hébergé dans le cloud, ses données peuvent déjà être stockées chez son fournisseur. Le boîtier les récupère pour les traiter localement. Cela ne signifie pas que le logiciel source cesse de les héberger.

Le système doit aussi proposer :

- Importation manuelle.
- Importation automatisée de fichiers.
- Connecteurs locaux.
- Synchronisation périodique.
- Gestion des erreurs et des autorisations expirées.

Les connecteurs seront développés progressivement selon les demandes des premiers clients.

## 8. Tableau de bord professionnel

L'interface doit être moderne, sobre et extrêmement lisible.

**Accueil**

- Santé globale.
- Chiffre d'affaires.
- Bénéfice estimé.
- Trésorerie.
- Charges.
- Évolution de l'activité.

**Centre d'intelligence**

- Recommandations.
- Opportunités.
- Alertes.
- Problèmes prioritaires.
- Actions suggérées.

**Centre d'automatisation**

- Actions en attente de validation.
- Actions exécutées.
- Automatisations actives.
- Historique des opérations.

**Centre des données**

- Logiciels connectés.
- Documents importés.
- Synchronisation.
- Qualité et fraîcheur des données.

**Paramètres**

- Gestion des utilisateurs.
- Gestion des autorisations.
- Modules activés.
- Confidentialité.
- Sauvegardes.
- Configuration du boîtier.

L'interface doit être responsive et utilisable sur smartphone.

## 9. Sécurité et confidentialité

La sécurité doit être un argument commercial majeur.

Exigences :

- Hébergement exclusivement local des données de l'application.
- Chiffrement des disques et des sauvegardes.
- Chiffrement des communications réseau.
- Authentification forte.
- Gestion des rôles et permissions.
- Protection contre les accès non autorisés.
- Journalisation des opérations.
- Séparation des données entre utilisateurs.
- Protection des clés API et jetons OAuth.
- Mises à jour signées et vérifiées.
- Sauvegardes locales sur support distinct.
- Procédure de restauration.
- Désactivation complète des connexions externes facultatives.

Le boîtier ne doit pas exposer directement ses services sur Internet.

Pour l'accès à distance, privilégier un VPN sécurisé de type WireGuard, avec une configuration contrôlée par le client.

Les mises à jour peuvent être téléchargées puis vérifiées avant installation. Elles ne doivent jamais envoyer les données de l'entreprise vers l'éditeur.

Le logiciel doit également être conçu en tenant compte du RGPD, des obligations de sécurité, des durées de conservation et des droits des personnes concernées.

Une analyse d'impact sur la protection des données devra être envisagée selon les traitements et les données concernés.

## 10. Architecture technique

| Couche | Technologie envisagée |
|---|---|
| Système d'exploitation | Debian ou Ubuntu Server |
| Interface | React + TypeScript |
| API backend | Python + FastAPI |
| Base de données | PostgreSQL |
| Stockage documentaire | Stockage local chiffré |
| Extraction documentaire | OCR et bibliothèques Python |
| IA locale | Ollama |
| Modèle IA initial | Qwen 2.5 7B |
| Orchestration | Python |
| Tâches planifiées | APScheduler ou équivalent |
| Authentification | Gestion locale des utilisateurs |
| Reverse proxy | Caddy ou équivalent |
| Conteneurisation | Docker Compose |
| Surveillance | Journaux et métriques locaux |

L'architecture devra être organisée en modules indépendants.

Un connecteur ne doit pas pouvoir compromettre l'ensemble du système.

### Architecture logique

```
                 ENTREPRISE
                     |
               Réseau Ethernet
                     |
              BUSINESS AI BOX
                     |
       +-------------+-------------+
       |             |             |
    Interface      Backend       Sécurité
       |             |             |
       +-------------+-------------+
                     |
              Moteur central
                     |
       +-------------+-------------+
       |             |             |
   PostgreSQL    Agents IA      Connecteurs
       |             |             |
       |         Modèle local      |
       |             |             |
       +-------------+-------------+
                     |
              Analyse métier
                     |
          Recommandations / Actions
                     |
              Validation client
                     |
           Exécution dans les outils
```

## 11. Configuration matérielle

Le produit doit pouvoir fonctionner sur différents niveaux de matériel.

**Version Starter**

- Mini-PC x86-64.
- 16 Go de RAM minimum.
- SSD 512 Go.
- Processeur moderne.
- Réseau Ethernet Gigabit.

Usage : petite entreprise, analyses financières, importation documentaire et modèles IA légers.

**Version Professional**

- Processeur plus puissant.
- 32 Go de RAM.
- SSD NVMe 1 To.
- GPU adapté à l'inférence locale ou mémoire partagée suffisante.
- Ethernet 2,5 Gb/s souhaitable.

Usage : PME, davantage de connecteurs, documents et utilisateurs.

**Version Enterprise**

- Workstation ou serveur compact.
- 64 Go de RAM ou plus.
- Stockage NVMe évolutif.
- GPU avec mémoire vidéo adaptée aux modèles choisis.
- Possibilité de redondance et de sauvegarde externe locale.

Usage : entreprises avec beaucoup de données et plusieurs utilisateurs simultanés.

Les configurations exactes seront validées par des tests de charge. Les 8 Go de VRAM du matériel de développement ne doivent pas être considérés comme une référence universelle pour les clients.

## 12. Gestion des données et fiabilité des analyses

Le système doit distinguer :

- Les données confirmées.
- Les données estimées.
- Les données manquantes.
- Les données anciennes.
- Les données incohérentes.

Chaque recommandation doit pouvoir afficher ses sources et ses calculs.

Exemple : « Votre marge a diminué de 6 % entre septembre et octobre. Cette variation provient principalement de l'augmentation du coût des matières premières. »

Le dirigeant doit pouvoir ouvrir le détail du calcul.

Le système ne doit jamais inventer une économie potentielle ou présenter une hypothèse comme une certitude.

**Un moteur de calcul classique sera responsable des indicateurs financiers. L'IA se chargera de l'interprétation, de l'explication et de la préparation des actions.**

## 13. Installation et première configuration

L'expérience d'installation doit être très simple.

1. Le client branche le boîtier au réseau.
2. Il accède à une adresse locale ou à un portail d'installation.
3. Il crée son compte administrateur.
4. Il renseigne les informations de son entreprise.
5. Il choisit les modules souhaités.
6. Il sélectionne ses logiciels professionnels.
7. Il autorise chaque connexion.
8. Le système effectue un premier inventaire des données.
9. Le moteur réalise une première analyse.
10. Le dirigeant découvre son tableau de bord et ses premières recommandations.

Le système doit afficher clairement les connexions réussies, les données récupérées et les éventuelles limites.

## 14. Modèle économique

Modèle commercial envisagé :

- Vente du boîtier.
- Licence logicielle.
- Maintenance et mises à jour.
- Modules complémentaires.
- Support technique.

La possibilité d'une location du boîtier pourra être étudiée.

Les prix ne sont pas encore définis. Ils devront être établis après estimation du coût du matériel, de la fabrication, du support et de la maintenance.

L'objectif est d'éviter une facturation au nombre de requêtes IA puisque l'IA fonctionne localement.

## 15. Périmètre de la première version (MVP)

Il ne faut surtout pas développer les dix modules simultanément.

La première version doit démontrer la valeur du concept avec un ensemble limité mais réellement fonctionnel.

### MVP obligatoire

1. Installation du logiciel sur un ordinateur Linux.
2. Interface professionnelle avec authentification.
3. Gestion des entreprises et utilisateurs.
4. Importation de factures PDF.
5. Extraction locale des données.
6. Base PostgreSQL locale.
7. Tableau de bord financier.
8. Analyse des charges et revenus.
9. Détection des anomalies simples.
10. Prévision de trésorerie.
11. Conseiller IA local.
12. Système de recommandations.
13. Historique des analyses.
14. Gestion des permissions.
15. Premier système d'exécution d'actions contrôlées.

### Premier connecteur externe

Commencer par un connecteur comptable ou financier disposant d'une API adaptée, après avoir validé ses conditions d'accès.

L'importation de fichiers restera disponible pour tester le produit sans dépendre d'un fournisseur externe.

### Fonctionnalités reportées

- Gestion complète des RH.
- Gestion avancée des stocks.
- Nombreux connecteurs.
- Automatisation complexe multi-logiciels.
- Comparaison sectorielle externe.
- Plusieurs agents spécialisés évolués.
- Déploiement à grande échelle.

## 16. Tests et critères de validation

Le MVP sera considéré comme fonctionnel lorsque :

- Les documents peuvent être importés localement.
- Les informations sont extraites et enregistrées correctement.
- Le tableau de bord calcule les indicateurs attendus.
- Les analyses sont reproductibles.
- L'IA répond à partir des données réellement disponibles.
- Les recommandations sont justifiées.
- Les permissions sont respectées.
- Une action autorisée peut être exécutée.
- Une action interdite est bloquée.
- Toutes les opérations sont historisées.
- Aucune donnée métier n'est transmise à l'éditeur.
- Le logiciel continue à fonctionner sans connexion Internet, pour ses fonctionnalités locales.
- Une sauvegarde peut être restaurée.

Des tests de sécurité, de charge et de récupération après panne devront compléter ces critères avant toute commercialisation.

## 17. Plan de développement

**Phase 1 — Fondations**

- Installer Linux et Docker.
- Créer le backend.
- Créer la base de données.
- Développer l'authentification.
- Construire la première interface.

**Phase 2 — Intelligence financière**

- Importer les documents.
- Extraire les informations.
- Construire les calculs.
- Développer les graphiques.
- Détecter les anomalies.

**Phase 3 — IA**

- Installer Ollama.
- Connecter le modèle local.
- Construire les agents.
- Développer le conseiller conversationnel.
- Produire des recommandations justifiées.

**Phase 4 — Exécution**

- Construire le moteur d'actions.
- Développer les permissions.
- Ajouter les validations.
- Ajouter les journaux d'activité.
- Tester les opérations.

**Phase 5 — Connecteurs**

- Créer le système de connecteurs.
- Développer les premières intégrations.
- Gérer les authentifications.
- Automatiser la synchronisation.

**Phase 6 — Industrialisation**

- Préparer l'installation sur mini-PC.
- Sécuriser le système.
- Automatiser les mises à jour.
- Construire le processus de sauvegarde.
- Tester avec une entreprise pilote.

Le suivi d'avancement est tenu dans [feuille-de-route.md](feuille-de-route.md).

## 18. Philosophie du produit

Business AI Box doit respecter cinq principes :

1. **Confidentialité** : l'entreprise conserve la maîtrise de ses données.
2. **Intelligence** : le système comprend les relations entre les différents départements.
3. **Anticipation** : il détecte les problèmes avant qu'ils ne deviennent critiques.
4. **Action** : il ne se contente pas de conseiller, il sait agir dans les limites autorisées.
5. **Transparence** : le dirigeant comprend toujours pourquoi une recommandation est formulée et ce que l'IA a fait.

La finalité n'est pas de remplacer le dirigeant. C'est de lui donner une vision globale de son entreprise et un assistant capable de l'aider à mieux la piloter.

## 19. Les trois décisions techniques à préserver

Trois points font la différence entre un prototype intéressant et un produit réellement commercialisable.

### 19.1. Le système doit être indépendant de l'IA

Si Qwen est remplacé demain par un autre modèle, tout le logiciel doit continuer à fonctionner. Les calculs, les données, les connecteurs et les automatisations ne doivent pas dépendre d'un modèle particulier.

### 19.2. Les connecteurs doivent être sécurisés

Un logiciel connecté ne doit jamais donner automatiquement accès à toutes les fonctions de l'entreprise. On doit pouvoir autoriser uniquement la lecture des factures, par exemple, sans autoriser les paiements.

### 19.3. Une véritable garantie de confidentialité

Prévoir un mode « zéro communication externe » : aucun accès Internet nécessaire au fonctionnement quotidien, aucune télémétrie, aucune transmission de données métier. Les mises à jour sont importées et vérifiées séparément.

C'est important pour pouvoir commercialiser une véritable solution privée.

## 20. Stratégie de développement

Pas d'achat de matériel pour le moment : le produit est développé sur le PC actuel, avec l'environnement Ollama et Qwen existant.

Feuille de route immédiate :

1. **Architecture technique** — organiser le projet, les dossiers, les services et les bases de données.
2. **Interface professionnelle** — construire le tableau de bord et l'espace d'administration.
3. **Premier moteur financier** — importer des factures, calculer les indicateurs et identifier les anomalies.
4. **Premier conseiller IA** — lui permettre de comprendre les chiffres et de produire des recommandations.
5. **Premier agent exécutif** — lui permettre d'effectuer une opération réelle, contrôlée et historisée.
6. **Transformation en Business AI Box** — installer le système sur un mini-PC et tester le fonctionnement en réseau local.

La première démonstration doit être impressionnante même sans aucun connecteur externe : on importe les factures d'une entreprise fictive, et Business AI Box produit un diagnostic complet avec des recommandations chiffrées. Ensuite, on ajoute les connexions aux logiciels professionnels.

C'est la manière la plus économique de prouver que le produit fonctionne avant d'investir.
