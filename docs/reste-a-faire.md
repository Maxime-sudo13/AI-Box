# Ce qu'il reste à faire, et les améliorations proposées

État au 13 novembre 2026, version 0.6.0. Les six phases du plan de développement sont faites
côté logiciel. Ce qui reste se répartit en trois blocs :

- **A.** Ce qui bloque la commercialisation.
- **B.** Les écarts restants avec le cahier des charges.
- **C.** Les améliorations que je recommande.

La partie **D** propose un ordre de marche.

Tailles indicatives : **S** = moins d'une journée de développement, **M** = quelques jours,
**L** = une à deux semaines.

---

## A. Bloquant avant de vendre (à faire dans l'ordre)

| # | Action | Qui | Taille | Pourquoi c'est bloquant |
|---|---|---|---|---|
| A1 | **Tester Qwen 2.5 7B sur votre PC** (message prêt pour la session locale) : part des rédactions acceptées par le contrôle des chiffres, temps de réponse | Vous + session locale | S | Décide du modèle et donc du mini-PC à acheter |
| A2 | **Constituer un corpus de 100 à 200 vraies factures anonymisées**, de vrais fournisseurs et dans des formats variés : multi-pages, avoirs, factures étrangères, photos de mauvaise qualité, factures sans tableau | Vous (collecte), moi (mesure et corrections) | M | La lecture est à 100 % sur nos factures générées, mais n'a jamais été mesurée sur de vraies factures. C'est le premier risque du produit |
| A3 | **Double authentification (TOTP)**, au moins pour les administrateurs et dirigeants | Moi | M | Le cahier des charges exige une « authentification forte » ; aujourd'hui : mot de passe + réauthentification pour les actions sensibles |
| A4 | **Licence logicielle** : fichier de licence signé par vous (modules achetés, date de fin de maintenance), vérifié hors ligne comme les mises à jour | Moi | M | Le modèle économique est « boîtier + licence » ; il n'existe encore aucun mécanisme de licence |
| A5 | **Premier mini-PC** : `installer-boitier.sh`, disque USB de sauvegarde, restauration sur une seconde machine, vrai paquet de mise à jour, choix du déverrouillage du disque (phrase de passe ou puce TPM) | Vous + moi | M | Rien de l'installation n'a encore tourné sur le vrai matériel |
| A6 | **Valider Qonto et la messagerie** avec de vrais comptes | Vous (clés d'API), moi | S | Testés uniquement contre des simulations |
| A7 | **Juridique** : validation du document RGPD, CGV et contrat de licence, contrat de sous-traitance pour le support, analyse d'impact (AIPD) courte | Juriste | M | Obligations légales ; argument commercial « confidentialité » |
| A8 | **Audit de sécurité externe** (test d'intrusion du boîtier) | Prestataire | M | Le produit se vend sur la sécurité : il faut un regard extérieur |
| A9 | **Pilote** chez une vraie entreprise, 4 à 8 semaines ([pilote.md](pilote.md)) | Vous | L | Seule preuve de valeur réelle |

---

## B. Écarts restants avec le cahier des charges

**Fonctions des modules 1 à 6 (des briques existent déjà) :**

| Exigence | État | Taille |
|---|---|---|
| Indice de santé global (module 1) | Absent. À construire de façon transparente : 5 sous-notes expliquées (rentabilité, trésorerie, coût matière, impayés, qualité des données), jamais une note opaque | M |
| Import Excel (module 3) | CSV uniquement : ajouter `.xlsx` (relevés, journaux de caisse) | S |
| Recherche dans le contenu des documents (module 3) | Recherche sur le nom, le numéro et le tiers ; ajouter la recherche plein texte (PostgreSQL) | S |
| Rapprochement d'un paiement couvrant plusieurs factures | Non géré | M |
| Analyse des coûts fixes et variables (module 2) | Partielle (catégories) ; ajouter le seuil de rentabilité, très parlant pour un dirigeant | S |
| Comparaison des fournisseurs, dépendance à un fournisseur (module 6) | Hausses de prix et classement faits ; ajouter l'alerte de dépendance (un fournisseur > 40 % d'une catégorie) | S |
| Ventes par produit, panier moyen (module 4) | Nécessite un export de caisse détaillé par article | M |
| Clients et CRM : segmentation, clients inactifs (module 5) | Seuls les impayés sont traités | M |

**Modules entiers non commencés :**

| Exigence | État | Taille |
|---|---|---|
| Stocks (module 7), RH (module 8), contrats (module 9) | Non commencés (les abonnements sont partiellement couverts). Reportés par le cahier des charges | L chacun |

**Système et connecteurs :**

| Exigence | État | Taille |
|---|---|---|
| Connecteurs Pennylane, Sage, Cegid, Odoo, HubSpot… | Prévus, selon les besoins des premiers clients | M chacun |
| Suppression définitive et export complet d'une entreprise (RGPD) | À faire, en respectant les 10 ans de conservation comptable | S |
| Purge automatique selon les durées de conservation | À faire | S |

---

## C. Améliorations que je recommande

Classées par rapport valeur / effort.

### C1. Ce qui ferait le plus d'effet chez un client

1. **Rapport mensuel automatique en PDF** (taille M) :
   - le 5 de chaque mois, le boîtier prépare le bilan du mois : indicateurs, graphiques,
     alertes, plan d'action ;
   - le dirigeant le lit en 2 minutes, et peut le transmettre à son expert-comptable ou à
     son banquier ;
   - c'est la fonction la plus « visible » et la plus facile à vendre.
2. **Objectifs fixés par le dirigeant** (taille S) :
   - par exemple coût matière 29 %, chiffre d'affaires mensuel, trésorerie minimale ;
   - les alertes et le tableau de bord se comparent à ses objectifs, et pas seulement au
     passé.
3. **Saisie d'inventaire simplifiée** (taille S) : un chiffre de stock par mois suffit à
   calculer le vrai coût matière, au lieu de l'approcher par les achats.
4. **Saisonnalité dans la prévision de trésorerie** (taille S) : utiliser l'année précédente
   (décembre fort, août faible) dès que 12 mois sont disponibles.
5. **Accès invité « expert-comptable »** (taille M) : lecture seule, export des pièces et des
   écritures. Les experts-comptables sont un excellent canal de vente.
6. **Le boîtier apprend des corrections** (taille M) : quand le dirigeant corrige une facture
   d'un fournisseur, le boîtier retient ce gabarit. La lecture s'améliore donc chez chaque
   client.
7. **Résumé hebdomadaire** dans l'application, et par courriel si SMTP est activé (taille S) :
   « 3 nouvelles alertes, 1 facture à vérifier, trésorerie OK ».

### C2. IA

8. **Le modèle choisit lui-même les agents et les outils** (taille M). Il ne calcule toujours
   rien : il désigne seulement les outils à appeler. Aujourd'hui, les intentions sont
   reconnues par mots-clés, et une formulation inattendue reçoit une réponse générique. Le
   routage par mots-clés reste en secours.
9. **Brouillons de courriels rédigés par l'IA** à partir des modèles actuels, avec le même
   contrôle des chiffres (taille S).
10. **« Expliquer ce graphique »** : un bouton sur chaque graphique (taille S).
11. **Banc d'essai des modèles** (taille S) :
    - script qui pose 30 questions de référence à n'importe quel modèle, et mesure le taux
      d'acceptation et le temps de réponse ;
    - permet de choisir objectivement entre Qwen, Mistral, Llama… à chaque nouvelle version.

### C3. Fiabilité et sécurité

12. **Lecture des documents dans un processus isolé** avec limite de temps et de mémoire
    (taille S) : un PDF malveillant ou géant ne doit pas pouvoir bloquer le serveur.
13. **Cache des analyses**, invalidé à chaque import (taille S) : pages instantanées, et
    possibilité de lancer plusieurs processus serveur.
14. **Limitation des tentatives de connexion par adresse IP**, en plus du verrouillage par
    compte (taille S).
15. **Surveillance du matériel** (taille S) : santé du disque, onduleur, alerte si le disque
    de sauvegarde est débranché depuis plus de 48 heures.
16. **Mise à jour des dépendances** suivie automatiquement, avec une alerte sur les failles
    connues (taille S).

### C4. Qualité du développement

17. **Intégration continue sur GitHub** (taille S) : tests et vérifications à chaque envoi.
    Aujourd'hui, ils ne tournent que lorsque je les lance.
18. **Tests de l'interface dans le dépôt** (taille M) : les parcours navigateur que j'ai
    exécutés sont restés dans mon espace de travail ; ils doivent devenir une suite de tests
    permanente.
19. **Vérification mobile et mode sombre** des pages récentes (taille S) : Conseiller,
    Automatisation, Logiciels connectés et Système n'ont été contrôlées que sur ordinateur.
20. **Audit d'accessibilité** : navigation au clavier, lecteurs d'écran (taille S).

---

## D. Proposition d'ordre de marche

1. **Cette semaine**, en parallèle :
   - vous : A1 (test Qwen) et la collecte des factures réelles (A2) ;
   - moi : A3 (double authentification), A4 (licence), C4-17 (intégration continue),
     C4-19 (mobile).
2. **Ensuite** : A2 (corrections sur factures réelles), C1-1 (rapport mensuel), C1-2
   (objectifs), C3-12 (isolation de la lecture des documents).
3. **Avec le matériel** : A5, A6, puis le pilote (A9). En parallèle : A7 et A8.
4. **Selon le pilote** : les modules B les plus demandés par le client, et le premier
   connecteur comptable.

## E. Questions commerciales à trancher

- **Prix** : coût du matériel (selon A1), support, maintenance. À établir avant le pilote
  pour tester l'intention d'achat.
- **Cible de départ** :
  - les restaurants (démonstration prête, indicateurs métier forts) ;
  - ou les TPE de services (plus nombreuses, mais moins d'indicateurs spécifiques) ;
  - ma recommandation : commencer par la restauration, puis élargir.
- **Canal** : vente directe, ou via les experts-comptables (qui ont déjà la confiance des
  dirigeants et leurs factures).
- **Support** : qui intervient chez le client, sous quel délai, avec quel accès (VPN à la
  demande, jamais permanent).
