# Déploiement pilote — liste de contrôle

Objectif : faire fonctionner Business AI Box pendant 4 à 8 semaines chez une vraie entreprise,
mesurer la valeur apportée et corriger ce qui ne fonctionne pas avant de commercialiser.

## Avant d'arriver chez le client

- [ ] Mini-PC choisi d'après les mesures de [industrialisation.md](industrialisation.md) §1,
      avec un modèle d'IA testé en conditions réelles (temps de réponse, part des
      rédactions acceptées par le contrôle des chiffres).
- [ ] Boîtier installé et testé à l'atelier :
  - [ ] disque chiffré ;
  - [ ] `installer-boitier.sh` déroulé sans erreur ;
  - [ ] sauvegarde puis **restauration réelle sur une seconde machine**.
- [ ] Disque USB de sauvegarde formaté et étiqueté.
- [ ] Clé publique de l'éditeur installée, et un paquet de mise à jour de test appliqué une fois.
- [ ] Documents remis au client :
  - [ ] convention de pilote (durée, gratuité, confidentialité) ;
  - [ ] contrat de sous-traitance (voir [rgpd.md](rgpd.md)) ;
  - [ ] fiche « clé de récupération ».

## Le jour de l'installation (½ journée)

- [ ] Branchement au réseau, accès à `https://businessaibox.local` depuis le poste du dirigeant.
- [ ] Compte administrateur créé par le dirigeant lui-même. Le mot de passe n'est pas connu
      de l'éditeur.
- [ ] Clé de récupération créée, imprimée et rangée par le dirigeant. Vérification d'une
      première sauvegarde avec cette clé.
- [ ] Modules choisis avec le dirigeant.
- [ ] Imports : 12 mois de factures (dossier ou lot), relevé bancaire, export des ventes.
- [ ] Factures « à vérifier » passées en revue ensemble.
- [ ] Revue des premières alertes avec le dirigeant : sont-elles justes ? utiles ?
- [ ] Autorisations des actions réglées par le dirigeant.
- [ ] Connexions éventuelles (banque, messagerie), en lecture seule.

## Pendant le pilote

- [ ] Point hebdomadaire de 30 minutes.
- [ ] Mesures à relever :
  - précision de lecture des factures réelles (corrections nécessaires / factures importées) ;
  - alertes jugées justes / fausses / inutiles ;
  - questions posées au conseiller et satisfaction ;
  - part des rédactions de l'IA acceptées et temps de réponse ;
  - actions proposées / validées / refusées ;
  - temps passé par le dirigeant chaque semaine ;
  - économies ou encaissements obtenus grâce au boîtier.
- [ ] Une restauration de sauvegarde vérifiée (**Système › Vérifier**) au milieu du pilote.
- [ ] Une mise à jour signée appliquée pendant le pilote.

## Bilan

- [ ] Ce que le dirigeant paierait, et pour quels modules.
- [ ] Les 5 corrections prioritaires.
- [ ] Accord pour citer l'entreprise (témoignage) ou non.
- [ ] À la fin : export ou restitution des données, puis effacement du boîtier si le client
      ne poursuit pas (réinstallation complète, disque effacé).
