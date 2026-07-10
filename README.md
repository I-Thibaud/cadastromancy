# CADASTROMANCY

Import et mise à jour, dans PostgreSQL/PostGIS, du cadastre non nominatif Etalab et des Documents de Filiation Informatisés (DFI - DGFiP), avec reconstitution de la généalogie des parcelles, spatiale et relationnelle.

**Version** : 2.0.0 — Auteur : Thibaud IDOUX

<!-- Remplacer par une capture d'écran ou un gif de l'interface / du résultat QGIS -->
<!-- ![Aperçu de CADASTROMANCY](docs/demo.gif) -->

**Sommaire**
- [CADASTROMANCY](#cadastromancy)
  - [1. Objectifs](#1-objectifs)
  - [2. Première utilisation](#2-première-utilisation)
    - [Option A — Exécutable portable (simple, recommandé)](#option-a--exécutable-portable-simple-recommandé)
    - [Option B — Via Python (avancé, pour modifier le code)](#option-b--via-python-avancé-pour-modifier-le-code)
  - [3. Configuration : le fichier `.env`](#3-configuration--le-fichier-env)
  - [4. Limites connues](#4-limites-connues)
  - [5. Architecture du dossier](#5-architecture-du-dossier)
  - [6. Rôle des scripts](#6-rôle-des-scripts)
  - [7. Compilation Windows](#7-compilation-windows)
  - [8. Dépannage](#8-dépannage)
  - [9. Sécurité](#9-sécurité)

---

## 1. Objectifs

- Maintenir à jour, en base PostgreSQL/PostGIS, les couches **parcelles** et **bâtiments** du cadastre non nominatif Etalab, pour les communes du territoire suivi.
- Charger les **DFI** (fichiers de filiation DGFiP) pour reconstituer l'historique des parcelles : divisions, fusions, remaniements, lotissements.
- Reconstruire automatiquement la **géométrie des parcelles mères** disparues, à partir des géométries filles actuelles.
- Fournir une **frise de filiation en HTML** par parcelle (fonction SQL), exploitable en pop-up QGIS ou dans un portail cartographique.
- *(à faire)* Illustrer ce README avec une image ou un gif de l'interface et/ou du rendu QGIS final — un aperçu visuel vaut mieux qu'une longue description pour un premier contact avec l'outil.

## 2. Première utilisation

Deux façons d'utiliser CADASTROMANCY, selon ton profil :

### Option A — Exécutable portable (simple, recommandé)

Aucune installation de Python requise.

1. **Récupérer l'exécutable** : télécharger la dernière version depuis l'onglet *Releases* du dépôt (ou compiler soi-même, cf. [§7](#7-compilation-windows)).
2. **Extraire** le `.zip` — garder tout le dossier `CADASTROMANCY/` intact, y compris le sous-dossier `_internal/` (indispensable, ne pas le supprimer ni le déplacer séparément).
3. **Lancer** `CADASTROMANCY.exe`.
4. Au premier lancement, la fenêtre propose de créer `config/.env` à partir du modèle — cliquer *"Éditer la configuration"* et renseigner les identifiants PostgreSQL (détail au [§3](#3-configuration--le-fichier-env)).
5. Utiliser les boutons de l'interface pour lancer la mise à jour du cadastre et, en option, traiter un fichier DFI.

*(`installer.bat` reste disponible en raccourci facultatif : il crée `config/.env` et lance l'exe en une seule étape, mais son test de présence de `psql` peut bloquer à tort si PostgreSQL est distant sans client local installé — l'application elle-même n'a pas besoin de `psql`.)*

### Option B — Via Python (avancé, pour modifier le code)

1. **Prérequis** : PostgreSQL 12+ avec extension PostGIS active, Python 3.8+.
2. **Cloner le dépôt** et installer les dépendances :
   ```bash
   pip install -r requirements.txt
   ```
3. **Configuration** : copier `config/.env.example` vers `config/.env` (détail au [§3](#3-configuration--le-fichier-env)).
4. **Contrôle avant lancement** :
   ```bash
   python check_project.py
   ```
   → vérifie syntaxe, dépendances, imports et présence de la configuration.
5. **Lancement** :
   ```bash
   python cadastromancy_app.py
   ```
6. Au premier lancement, le schéma, les tables, les vues matérialisées et les fonctions SQL DFI sont créés automatiquement — aucune manipulation SQL manuelle requise.
7. **Appliquer les styles QGIS** : importer les `.qml` du dossier `style_qgis/` dans QGIS pour chaque table (possibilité de les stocker en base et de les définir en style par défaut).

## 3. Configuration : le fichier `.env`

Toute la configuration (base de données, territoire suivi) passe par un unique fichier `config/.env`, jamais versionné ni partagé.

**Emplacement selon le mode d'utilisation :**

| Mode | Emplacement de `config/.env` |
|---|---|
| Exécutable portable | à côté de `CADASTROMANCY.exe`, dans `CADASTROMANCY/config/.env` |
| Python | à la racine du dépôt, dans `config/.env` |

**Variables à renseigner** (copier `config/.env.example` comme point de départ) :

```ini
DB_USER=votre_utilisateur
DB_PASSWORD=votre_mot_de_passe
DB_HOST=localhost
DB_PORT=5432
DB_NAME=votre_bdd
DB_SCHEMA=ref_cadastre_nn
DEPARTEMENT=29
CODES_COMMUNE=017,040,076,084
```

| Variable | Rôle |
|---|---|
| `DB_USER` / `DB_PASSWORD` | Identifiants de connexion PostgreSQL |
| `DB_HOST` / `DB_PORT` | Adresse et port du serveur PostgreSQL |
| `DB_NAME` | Nom de la base de données cible |
| `DB_SCHEMA` | Schéma PostgreSQL où sont créées les tables du projet |
| `DEPARTEMENT` | Code département (2 chiffres, ex : `29`) — utilisé aussi pour retrouver le bon fichier DFI |
| `CODES_COMMUNE` | Liste des codes commune (3 chiffres, séparés par des virgules) du territoire suivi |

**Deux façons de créer/éditer ce fichier :**
- Via l'interface : bouton *"Éditer la configuration (.env)"* — le crée automatiquement à partir du modèle s'il n'existe pas encore.
- Manuellement : copier `config/.env.example` vers `config/.env` et éditer avec un éditeur de texte.

## 4. Limites connues

- Une seule configuration `.env` = un seul département suivi (pas de multi-département natif) → modifier le `.env` et relancer à plusieurs reprises pour couvrir plusieurs départements.
- Le format brut du fichier DFI (10 colonnes de métadonnées) est contrôlé automatiquement, mais peut évoluer sans préavis d'un millésime DGFiP à l'autre : en cas d'alerte, vérifier manuellement les premières lignes avant de poursuivre.
- La reconstruction géométrique des parcelles mères peut rester **partielle** (parcelle fille manquante en base, hors périmètre suivi) — signalé par le champ `geometrie_partielle`.
- Le nom du géomètre est volontairement écarté du chargement (anonymisation) : aucune traçabilité du professionnel en base.
- Aucun test automatisé (unitaire/intégration) n'est fourni dans ce dépôt.
- Sous Linux/macOS : utiliser directement Python (option B) — l'exécutable compilé est Windows uniquement.

## 5. Architecture du dossier

**Dépôt (code source) :**

```
CADASTROMANCY/
├── cadastromancy_app.py      # Logique métier : cadastre + DFI
├── postgres_setup.py         # Création SQL du schéma (tables, vues, fonctions)
├── ui_cadastromancy.py       # Interface graphique (tkinter)
├── chemins.py                # Résolution centralisée des chemins (exe vs script)
├── check_project.py          # Diagnostic du projet avant déploiement
├── build_exe.py              # Compilation en exécutable Windows
├── version.py                 # Métadonnées de version
├── requirements.txt          # Dépendances Python
├── assets/
│   └── cadastromancy.ico      # Icône de l'exécutable
├── config/
│   ├── .env.example           # Modèle de configuration (versionné)
│   └── .env                   # Configuration réelle (JAMAIS versionné)
├── telechargement/           # Fichiers temporaires (créé et vidé automatiquement)
└── style_qgis/                # Styles QGIS (.qml — parcelles, bâtiments, filiation)
```

**Distribution (générée par `build_exe.py`, jamais versionnée — cf. `.gitignore`) :**

```
dist/CADASTROMANCY/
├── CADASTROMANCY.exe          # Exécutable
├── _internal/                 # DLL et dépendances Python — NE PAS SUPPRIMER
├── installer.bat              # Raccourci facultatif (cf. §2, option A)
├── config/
│   └── .env.example
├── README_COMPILATION.txt
└── manifest_distribution.json
```

## 6. Rôle des scripts

| Script | Rôle |
|---|---|
| `cadastromancy_app.py` | Charge la config, se connecte à PostgreSQL, orchestre la mise à jour cadastre et DFI (`main`, `main_cadastrenn`, `main_dfi`). |
| `postgres_setup.py` | Génère le DDL SQL : tables `date_maj`, `parcelles`, `batiments`, `dfi`, `dfi_lien`, vues matérialisées, et les fonctions PL/pgSQL de traitement DFI et de filiation HTML. |
| `ui_cadastromancy.py` | Fenêtre tkinter : édition de la config, sélection du zip DFI, lien de téléchargement DGFiP, lancement du traitement. |
| `chemins.py` | Résout le dossier du projet/config selon le mode (exécutable compilé ou script Python), pour que `.env` soit trouvé au bon endroit dans les deux cas. |
| `check_project.py` | Contrôle la structure, la syntaxe, les dépendances et la configuration avant mise en production. |
| `build_exe.py` | Génère l'exécutable Windows autonome (PyInstaller, mode `--onedir`), le script d'installation facultatif et le manifeste de distribution. |
| `version.py` | Numéro de version et date de build, réutilisés par `build_exe.py`. |

## 7. Compilation Windows

```bash
python build_exe.py
```

Le résultat est généré dans `dist/CADASTROMANCY/` (mode `--onedir` : un dossier complet à distribuer, pas un exe isolé — cf. [§5](#5-architecture-du-dossier)).

**Point d'attention pour toute évolution du code** : geopandas s'appuie sur plusieurs paquets (`pyogrio`, `pyproj`, `shapely`, `geoalchemy2`) qui sont importés **dynamiquement à l'intérieur de fonctions** (`to_crs`, `to_postgis`...) plutôt qu'en haut des fichiers. PyInstaller ne les détecte alors pas automatiquement : toute nouvelle dépendance de ce type doit être ajoutée explicitement dans `build_exe.py` via `--collect-all=nom_du_paquet`, en plus de `requirements.txt`.

## 8. Dépannage

| Symptôme | Cause probable | Piste |
|---|---|---|
| `config/.env` introuvable après compilation | Chemin calculé via `__file__` au lieu du dossier réel de l'exe | Vérifier que le fichier concerné importe bien `DOSSIER_CONFIG` depuis `chemins.py`/`cadastromancy_app.py` |
| `ModuleNotFoundError: No module named 'xxx'` à l'exécution de l'exe | Paquet importé dynamiquement, invisible pour l'analyse statique de PyInstaller | Ajouter `--collect-all=xxx` dans `build_exe.py` **et** `xxx` dans `requirements.txt` ; vérifier qu'il est bien installé dans le venv utilisé pour compiler |
| `... DLL could not be found` / `Accès refusé` sur une DLL native (GDAL, GEOS, PROJ, psycopg2...) | Extraction temporaire bloquée (antivirus, stratégie de sécurité) en mode `--onefile`, ou deux versions de la même bibliothèque native embarquées en conflit | Vérifier qu'on est bien en `--onedir` ; vérifier qu'un seul moteur GDAL est présent dans l'environnement de build (éviter d'avoir `fiona` **et** `pyogrio` en même temps) |
| Le programme fonctionne en script Python mais pas en `.exe`, sur la **même machine** | Environnement de compilation différent de celui testé en script (venv vs Python global) | Vérifier avec `python -c "import sys; print(sys.executable)"` que le même interpréteur est utilisé pour `pip install` et pour lancer `build_exe.py` |

## 9. Sécurité

- Ne jamais versionner ni partager `config/.env` (identifiants PostgreSQL en clair) — vérifié par `.gitignore`.
- Stocker `config/.env` hors des sauvegardes publiques ou partagées.
- Ne jamais committer le dossier `dist/` (exécutable + DLL) dans le dépôt Git — le publier via l'onglet *Releases* de GitHub à la place (fichiers volumineux, régénérables à chaque build).