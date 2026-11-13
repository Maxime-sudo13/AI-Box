# Protection des données (RGPD) — éléments pour la commercialisation

> Document de travail préparé à partir du fonctionnement réel du logiciel. Il ne remplace pas
> l'avis d'un juriste ou d'un délégué à la protection des données, à solliciter avant la
> commercialisation.

## Qui est responsable de quoi

- **Le client** (l'entreprise équipée du boîtier) est **responsable de traitement** : il
  choisit les données importées, les modules activés, les connexions et les actions autorisées.
- **L'éditeur** de Business AI Box fournit le matériel et le logiciel. Comme **aucune donnée
  de l'entreprise ne lui est transmise** (traitement local, pas de télémétrie, mises à jour
  importées et vérifiées sur place), il n'est pas sous-traitant pour le fonctionnement
  courant.
- **L'éditeur devient sous-traitant** s'il intervient sur un boîtier contenant des données
  (support, maintenance, restauration). Un contrat de sous-traitance (article 28 du RGPD)
  doit alors encadrer ces interventions.
- **Logiciels connectés** (banque, messagerie, comptabilité) : le client a déjà une relation
  directe avec ces éditeurs. Le boîtier ne fait que récupérer les données autorisées.

## Registre des traitements (modèle pour le client)

| Traitement | Finalité | Données | Personnes concernées | Durée de conservation proposée |
|---|---|---|---|---|
| Pilotage financier | Analyse de l'activité, de la rentabilité et de la trésorerie | Factures, relevés bancaires, ventes | Fournisseurs et clients professionnels ; personnes physiques (entrepreneurs individuels, clients particuliers figurant sur une facture) | Pièces comptables : 10 ans (Code de commerce, article L123-22) |
| Relances et courriels | Recouvrement, échanges fournisseurs | Nom, adresse e-mail, montants | Contacts des clients et fournisseurs | Durée de la relation commerciale + 3 ans |
| Comptes utilisateurs | Accès sécurisé au boîtier | Nom, e-mail, empreinte du mot de passe, journal de connexion | Salariés et dirigeants utilisateurs | Durée de l'accès ; journaux : 1 an |
| Journal d'activité | Sécurité, traçabilité des actions | Identité de l'auteur, action, adresse IP locale | Utilisateurs | 1 an (préconisation CNIL pour les journaux) |
| Masse salariale | Analyse des charges de personnel | Montants globaux des salaires et cotisations, issus du relevé bancaire | Salariés (de façon agrégée) | Comme les pièces comptables |

## Mesures de sécurité en place (article 32)

- Hébergement exclusivement local, disque chiffré (LUKS), sauvegardes chiffrées dont la clé
  de récupération est conservée hors du boîtier.
- Authentification individuelle :
  - mots de passe hachés (Argon2) ;
  - verrouillage après 5 échecs ;
  - sessions révocables ;
  - réauthentification pour les opérations sensibles.
- Rôles par entreprise. Un utilisateur ne voit que les entreprises auxquelles il est
  rattaché, et les agents d'IA n'accèdent qu'aux données de leur mission.
- Journal de toutes les opérations sensibles, y compris les tentatives refusées.
- Identifiants des logiciels connectés chiffrés (AES-256-GCM), jamais affichés ni journalisés.
- Pas d'exposition sur Internet ; accès distant par VPN contrôlé par le client.
- Mode « zéro communication externe » par défaut.
- IA locale :
  - aucune donnée n'est envoyée à un service d'IA extérieur ;
  - le modèle ne voit pas les documents bruts ;
  - aucune décision automatisée concernant les salariés (article 22 ; cahier des charges,
    module 8).

## Analyse d'impact (AIPD)

Une AIPD est obligatoire quand un traitement remplit au moins deux critères de la liste de la
CNIL. Pour un usage de pilotage financier d'une TPE, la plupart des critères ne sont
**a priori pas remplis** :

- pas de données sensibles ;
- pas de profilage de personnes ;
- pas de surveillance systématique ;
- pas de décision automatisée produisant des effets juridiques.

Le point à examiner est **l'usage d'une technologie innovante (IA)**. Atténuations :

- modèle local ;
- l'IA ne fait que reformuler, avec contrôle de chaque chiffre ;
- l'IA ne déclenche aucune action sans validation humaine.

Recommandation : rédiger une AIPD courte pour le produit, mise à la disposition des clients.
Le futur module RH (données individuelles des salariés) devra faire l'objet de sa propre
analyse.

## Droits des personnes

- **Accès et portabilité** : les documents originaux et les données extraites sont
  consultables et téléchargeables depuis le boîtier.
- **Effacement et limitation** : un document peut être écarté des calculs (« Ignorer »).
- **À développer** : la suppression définitive d'un tiers et de ses documents, et l'export
  complet d'une entreprise. Les pièces comptables restent soumises à l'obligation de
  conservation de 10 ans.

## Points ouverts avant commercialisation

1. Validation juridique de ce document et des conditions générales de vente.
2. Contrat de sous-traitance type pour les interventions de support.
3. Fonction de purge automatique selon les durées de conservation.
4. AIPD produit.
