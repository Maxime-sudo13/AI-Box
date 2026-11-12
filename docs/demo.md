# Démonstration : « Le Bistrot des Tilleuls »

Restaurant traditionnel fictif de Lyon (SARL, 7 salariés, environ 50 000 € de chiffre
d'affaires HT par mois). Douze mois complets d'activité, générés de façon réaliste et
déterministe : à chaque génération, les données se terminent la veille du jour où elles
sont produites.

Tous les noms, adresses et numéros SIREN sont fictifs. Les SIREN ne respectent
volontairement pas la clé de contrôle, pour ne jamais correspondre à une entreprise réelle.

## Préparer la démonstration

```bash
cd backend
# Option A : produire les fichiers, pour les déposer soi-même dans l'interface
uv run python -m app.demo generate --out ../demo-restaurant

# Option B : créer directement l'entreprise sur le boîtier et tout importer (≈ 30 s)
uv run python -m app.demo seed
```

L'option A est la plus spectaculaire devant un prospect. On ouvre **Données**, puis on
glisse d'un coup le dossier `factures` (345 fichiers), le relevé bancaire et le journal de
caisse. On voit alors chaque document lu et classé en direct.

| Contenu | Volume | Particularités |
|---|---|---|
| Factures fournisseurs | ≈ 320 | 15 fournisseurs, 3 mises en page différentes |
| Factures scannées | 11 | Image seule, légèrement de travers : lues par OCR |
| Photo de facture | 1 | JPEG pris « au smartphone » |
| Factures de privatisation | 9 | Émises par le restaurant à des entreprises clientes |
| Bon de livraison | 1 | Ressemble à une facture mais sans montant |
| Journal de caisse | 308 jours | Couverts, CA nourriture et boissons, CB, espèces, titres-restaurant |
| Relevé bancaire | ≈ 720 opérations | Encaissements, fournisseurs, salaires, URSSAF, TVA, emprunt… |

## Ce que le boîtier doit trouver tout seul

Les situations ci-dessous sont glissées dans les données. Le boîtier les détecte sans
aucune aide, et les tests automatisés le vérifient à chaque modification.

| Situation cachée | Où elle apparaît | Ce qu'elle démontre |
|---|---|---|
| Le coût matière cuisine dérive de 27,7 % à 31 %. Le prix du saumon a augmenté et les volumes achetés en viande et poisson ont grimpé sans hausse de fréquentation. | Alerte prioritaire, avec le coût annuel de la dérive et les fournisseurs qui y contribuent | Analyse croisée achats × ventes, propre à la restauration |
| Le pavé de saumon passe de 24,90 € à 30,38 € le kilo (+22 %). La bavette prend +9 %. | Alerte avec le surcoût annuel, la courbe du prix et les factures | Suivi du prix de chaque article, ligne par ligne |
| Une facture de privatisation (Delmas Conseil) reste impayée depuis près de 4 mois. | Alerte prioritaire. La prévision de trésorerie ne la compte pas. | Rapprochement factures ↔ banque, prudence de la prévision |
| Passage au logiciel de caisse CaissePro en juin, sans avoir résilié TactilResto. | Alerte « deux abonnements similaires » : 1 608 € HT par an | Détection d'abonnements en double |
| Facture d'électricité de septembre sur relevé estimé : 1,6 fois le montant habituel. | Alerte, avec la mention « consommation estimée » lue sur la facture | Contrôle des factures avant paiement |
| Deux factures de la boucherie ont été payées mais jamais reçues. | Alerte « paiement sans facture », avec la TVA non récupérable | Détection des justificatifs manquants |
| Une facture du primeur est renvoyée en DUPLICATA. | Écartée automatiquement, alerte « reçue deux fois » | Pas de double comptage, pas de double paiement |
| Le même PDF est enregistré deux fois dans le dossier (« … (1).pdf »). | Refusé à l'import : « déjà importé » | Contrôle par empreinte du fichier |
| Une grosse commande de fin d'année chez le caviste (6 754 €), puis les échéances de décembre. | Trésorerie prévue sous le seuil de vigilance fin décembre | Prévision à 90 jours expliquée composante par composante |
| Un bon de livraison sans montant. | Placé « à vérifier » : il n'est jamais inventé de montant | Honnêteté de l'extraction |
| Fermeture estivale de deux semaines en août. | EBE négatif en août, trésorerie au plus bas fin août | Réalisme des données |

## Déroulé conseillé (10 minutes)

1. **Tableau de bord** : la situation du mois se lit en moins de deux minutes. Cliquer sur
   « Coût matière cuisine » pour montrer la formule, les 18 factures utilisées et la
   mise en garde sur l'absence d'inventaire.
2. **Graphique d'activité** : cliquer sur août pour montrer l'effet de la fermeture, puis
   revenir sur octobre.
3. **Alertes** : ouvrir le saumon, puis la facture impayée, puis les deux logiciels de
   caisse. Insister sur le fait que chaque montant cite ses documents et détaille son calcul.
4. **Trésorerie** : le point bas de fin décembre et sa construction (connu ou estimé).
5. **Données** : ouvrir une facture scannée et montrer l'original à côté des données lues,
   les coches « vérifié » et le paiement rapproché.
6. **Confidentialité** : débrancher le câble réseau Internet du boîtier. Tout continue de
   fonctionner.
