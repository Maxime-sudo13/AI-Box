# Tester Business AI Box sur votre ordinateur

Pas besoin du mini-PC : la même installation tourne sur un ordinateur Windows, Mac ou Linux,
avec le restaurant de démonstration déjà chargé et votre Ollama pour l'IA.

## Prérequis (une seule fois)

1. **Docker Desktop** : https://www.docker.com/products/docker-desktop/ — installez-le, puis
   lancez-le et attendez que la baleine indique « Engine running ».
2. **Le code du projet** sur votre ordinateur :
   - avec Git : `git clone https://github.com/Maxime-sudo13/AI-Box.git` puis
     `git checkout claude/business-ai-box-specs-jy7oep` dans le dossier `AI-Box` ;
   - ou sur GitHub : choisir la branche `claude/business-ai-box-specs-jy7oep`, bouton
     **Code › Download ZIP**, puis décompresser.
3. **Ollama** (déjà installé chez vous) avec le modèle : `ollama pull qwen2.5:7b`.
   Facultatif : sans Ollama, tout fonctionne, le conseiller répond alors avec le moteur de
   calcul.

## Lancer

Dans le dossier `AI-Box` :

| Système | Commande |
|---|---|
| Windows (PowerShell) | `.\lancer-en-local.ps1` |
| Mac / Linux (Terminal) | `./lancer-en-local.sh` |

Si Windows refuse d'exécuter le script : `Set-ExecutionPolicy -Scope Process Bypass`, puis
relancez la commande.

La première fois, la construction prend 5 à 10 minutes (téléchargement des composants), puis
le restaurant de démonstration est chargé (environ 30 secondes). Le navigateur s'ouvre ensuite
sur **http://localhost:8080** :

- adresse e-mail : `gerant@bistrot.local`
- mot de passe : `demo-bistrot-2026`

Les fois suivantes, le lancement prend quelques secondes et vos données sont conservées.

## Ce qu'il faut regarder

Suivez le déroulé de [demo.md](demo.md). Pour l'IA en particulier :

1. Ouvrez **Conseiller** : en haut à droite, l'indicateur doit afficher
   « IA locale active · qwen2.5:7b ».
2. Posez les questions d'exemple. Sous chaque réponse, notez l'auteur :
   - « Rédigé par qwen2.5:7b · chiffres contrôlés » : le modèle a reformulé et tous ses
     chiffres ont été vérifiés ;
   - « rédaction de l'IA écartée (chiffre non vérifié) » : Qwen a écrit un chiffre absent des
     données, sa réponse a été remplacée par celle du moteur.
3. Notez la proportion de réponses écartées et le temps de réponse : c'est ce qui dira si
   Qwen 2.5 7B convient ou s'il faut ajuster la consigne ou changer de modèle.

Pour tester le **dossier surveillé** : dans **Logiciels connectés**, connectez le dossier
`.` puis déposez des factures PDF dans `deploy/depot/` et cliquez sur « Synchroniser ».

## Mesurer l'IA sur votre PC

Le conseiller reconnaît les questions courantes par mots-clés. Pour une question formulée
autrement, c'est le modèle qui choisit les analyses à lancer (« Question comprise par l'IA »
sous la réponse). Pour mesurer si votre modèle choisit bien, depuis le dossier AI-Box :

```
docker compose -f deploy/docker-compose.local.yml exec api python scripts/banc_routage.py
```

Le script pose 32 questions inhabituelles (dont 4 hors sujet ou malveillantes) et affiche
deux taux de bons choix : le modèle seul, et le système complet (mots-clés d'abord, modèle
sinon), ainsi que le temps moyen.

Premier essai (13 novembre 2026, PC de développement, Qwen 2.5 7B) : 18/22 bons choix,
0,3 s par question. Les erreurs : 3 questions sur l'entreprise jugées « hors sujet » ; la
consigne du modèle a été corrigée en conséquence (v0.6.4). Envoyez-moi le résultat : il sert à choisir le modèle et
le matériel. Seules la question et la liste des analyses sont envoyées au modèle, jamais vos
données.

Pour que le modèle choisisse les analyses de chaque question (plus lent sans carte graphique),
ajoutez `BAB_AI_ROUTING=toujours` dans `deploy/.env`, puis relancez le script de lancement.

## En cas de problème

| Symptôme | Solution |
|---|---|
| « IA locale indisponible » | Vérifiez qu'Ollama tourne (`ollama list`). Sous Linux, ou si cela persiste, démarrez Ollama avec la variable `OLLAMA_HOST=0.0.0.0` pour qu'il accepte les connexions de Docker. |
| Le port 8080 est déjà utilisé | Dans `deploy/docker-compose.local.yml`, remplacez `127.0.0.1:8080:80` par `127.0.0.1:8090:80`, puis ouvrez http://localhost:8090. |
| Une page ou un lien annoncé n'apparaît pas | Regardez la version écrite en bas du menu de gauche. Si elle est ancienne (ou absente), relancez le script : il récupère la dernière version (`git pull`) et reconstruit l'application. Puis rechargez la page avec Ctrl+F5. |
| Le script s'arrête à « Attente du serveur » | `docker compose -f deploy/docker-compose.local.yml logs api` affiche la cause. |
| Repartir de zéro | `docker compose -f deploy/docker-compose.local.yml down -v` (efface aussi les données de test). |

## Arrêter

`docker compose -f deploy/docker-compose.local.yml down` : l'application s'arrête, les données
restent pour la prochaine fois.

L'application n'est accessible que depuis votre ordinateur (adresse 127.0.0.1) : rien n'est
exposé sur votre réseau ni sur Internet.
