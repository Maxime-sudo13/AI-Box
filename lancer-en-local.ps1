# Business AI Box — test sur votre ordinateur (Windows). Prérequis : Docker Desktop démarré.
# Lancer depuis PowerShell, dans le dossier AI-Box :  .\lancer-en-local.ps1
# (si Windows bloque le script : Set-ExecutionPolicy -Scope Process Bypass, puis relancer)
#
# Pas de « $ErrorActionPreference = Stop » : Windows PowerShell considère comme une erreur fatale
# tout message d'erreur d'une commande externe, y compris les essais normaux pendant que le
# serveur démarre. Chaque étape vérifie donc elle-même son code de retour.
$compose = @("compose", "-f", "docker-compose.local.yml")
Push-Location $PSScriptRoot
try {
  # Récupère la dernière version du code si le dossier vient de « git clone ».
  # (Désactiver : $env:BAB_NO_PULL = "1")
  if ((Test-Path ".git") -and (Get-Command git -ErrorAction SilentlyContinue) -and ($env:BAB_NO_PULL -ne "1")) {
    Write-Host "0/3  Récupération de la dernière version (git pull)..."
    & git pull --ff-only
    if ($LASTEXITCODE -ne 0) { Write-Host "  (mise à jour impossible : on continue avec la version présente sur ce PC)" }
  }
  Set-Location "deploy"

  Write-Host "1/3  Construction et démarrage (la première fois : 5 à 10 minutes)..."
  & docker @compose up -d --build
  if ($LASTEXITCODE -ne 0) { Write-Host "Échec du démarrage. Docker Desktop est-il lancé ?"; exit 1 }

  Write-Host "2/3  Attente du serveur..."
  $ready = $false
  for ($i = 0; $i -lt 90; $i++) {
    # Le serveur écoute-t-il ? (réponse 0 ou un code d'erreur, sans message d'erreur affiché)
    & docker @compose exec -T api python -c "import socket, sys; sys.exit(socket.socket().connect_ex(('127.0.0.1', 8000)))" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    Start-Sleep -Seconds 2
  }
  if (-not $ready) { Write-Host "Le serveur ne démarre pas. Détails : docker compose -f deploy\docker-compose.local.yml logs api"; exit 1 }

  Write-Host "3/3  Chargement du restaurant de démonstration (la première fois : environ 1 minute)..."
  & docker @compose exec -T api python -m app.demo seed --admin-email gerant@bistrot.local --admin-password demo-bistrot-2026

  $version = & docker @compose exec -T api python -c "import app; print(app.__version__)"
  Write-Host ""
  Write-Host "Prêt : http://localhost:8080   (version $version, affichée aussi en bas du menu de gauche)"
  Write-Host "  Adresse e-mail : gerant@bistrot.local"
  Write-Host "  Mot de passe   : demo-bistrot-2026"
  Write-Host "Tester l'IA : docker compose -f deploy\docker-compose.local.yml exec api python scripts/banc_routage.py"
  Write-Host "Arrêter     : docker compose -f deploy\docker-compose.local.yml down   (vos données sont conservées)"
  Start-Process "http://localhost:8080"
}
finally {
  # On revient dans le dossier AI-Box, d'où les commandes ci-dessus fonctionnent.
  Pop-Location
}
