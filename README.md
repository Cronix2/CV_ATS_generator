# CV ATS Generator

Application Next.js pour generer un CV ATS et importer les donnees depuis LinkedIn.

## Prerequis

- Node.js + npm installes
- Dependances installees dans le projet:

```bash
npm install
```

## Lancer le site (mode developpement)

```bash
npm run dev
```

Le site est accessible sur <http://localhost:3000>

## Commandes de deploiement local (start/restart/stop/status/logs)

Le projet inclut un script PowerShell `scripts/deploy.ps1` avec des commandes npm prêtes.

### Mode developpement

- Demarrer:

```bash
npm run deploy:start
```

- Relancer:

```bash
npm run deploy:restart
```

- Arreter:

```bash
npm run deploy:stop
```

- Verifier le statut:

```bash
npm run deploy:status
```

- Voir les logs:

```bash
npm run deploy:logs
```

### Mode production local

- Demarrer (avec build):

```bash
npm run deploy:prod:start
```

- Relancer (avec build):

```bash
npm run deploy:prod:restart
```

## Commandes Next.js standard

- Build:

```bash
npm run build
```

- Demarrage production:

```bash
npm run start
```

- Lint:

```bash
npm run lint
```

## Troubleshooting (Windows)

Si tu vois l'erreur `npm est introuvable dans ce terminal`:

1. Installe Node.js sans droits admin (scope utilisateur):

```bash
winget install OpenJS.NodeJS.LTS --scope user --accept-package-agreements --accept-source-agreements
```

1. Ferme puis reouvre le terminal.

1. Verifie que npm est disponible:

```bash
npm -v
```

1. Relance ensuite la commande `deploy:*` voulue.

Si `winget` n'est pas disponible, utilise l'installeur Node.js "Windows Installer (.msi)" en mode "Just for me" (utilisateur courant), puis reouvre le terminal.

## Emplacement des logs

Les logs du script deploy sont ecrits ici:

- `debug/next-server.out.log`
- `debug/next-server.err.log`
