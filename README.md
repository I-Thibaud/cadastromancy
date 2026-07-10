# CADASTROMANCY

Import et mise à jour, dans PostgreSQL/PostGIS, du cadastre non nominatif Etalab et des Documents de Filiation Informatisés (DFI - DGFiP), avec reconstitution de la généalogie des parcelles, spatiale et relationnelle.

**Version** : 2.0.0 — Auteur : Thibaud IDOUX

---

## 1. Objectifs

- Maintenir à jour, en base PostgreSQL/PostGIS, les couches **parcelles** et **bâtiments** du cadastre non nominatif Etalab, pour les communes du territoire suivi.
- Charger les **DFI** (fichiers de filiation DGFiP) pour reconstituer l'historique des parcelles : divisions, fusions, remaniements, lotissements.
- Reconstruire automatiquement la **géométrie des parcelles mères** disparues, à partir des géométries filles actuelles.
- Fournir une **frise de filiation en HTML** par parcelle (fonction SQL), exploitable en pop-up QGIS ou dans un portail cartographique.

## 2. Mode opératoire — première utilisation

1. **Prérequis** : PostgreSQL 12+ avec extension PostGIS active ; Python 3.8+ (ou l'exécutable Windows compilé, cf. §6).
2. **Dépendances** : `pip install -r requirements.txt`
3. **Configuration** : copier `config/.env.example` vers `config/.env` et renseigner :
   `DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME, DB_SCHEMA, DEPARTEMENT, CODES_COMMUNE`. Il est également possible de le configurer dans l'interface.
4. **Contrôle avant lancement** : `python check_project.py`
   → vérifie syntaxe, dépendances, imports et présence de la configuration.
5. **Lancement** : `python cadastromancy_app.py` (ouvre l'interface graphique).
   Au premier lancement, le schéma, les tables, les vues matérialisées et les fonctions SQL DFI sont créés automatiquement — aucune manipulation SQL manuelle requise.
6. **Mise à jour du cadastre** : bouton *« Lancer la mise à jour »*. Le programme compare le millésime en ligne à celui déjà en base, télécharge si besoin parcelles et bâtiments pour les communes configurées, les reprojette en Lambert 93 et rafraîchit les vues matérialisées.
7. **Traitement DFI (optionnel)** : télécharger manuellement l'archive DFI du département sur data.economie.gouv.fr, la sélectionner via *« Parcourir... »*, puis relancer. Le programme extrait le fichier du département, contrôle son format, le nettoie, l'insère sans doublon puis calcule filiations et géométries mères.
8. **Appliquer les styles Qgis** : importer les Qml dans qgis pour chacunes des tables. Possibilité de les stocker dans la base et les définir en style par défaut.

## 3. Limites connues

- Une seule configuration `.env` = un seul département suivi (pas de multi-département natif). --> Modifier le .env et relancer à plusieurs reprises.
- Le format brut du fichier DFI (10 colonnes de métadonnées) est contrôlé automatiquement, mais peut évoluer sans préavis d'un millésime DGFiP à l'autre : en cas d'alerte, vérifier manuellement les premières lignes avant de poursuivre.
- La reconstruction géométrique des parcelles mères peut rester **partielle** (parcelle fille manquante en base, hors périmètre suivi) — signalé par le champ `geometrie_partielle`.
- Le nom du géomètre est volontairement écarté du chargement (anonymisation) : aucune traçabilité du professionnel en base.
- `installer.bat` suppose un environnement Windows avec `psql` dans le PATH ; sous Linux/macOS, utiliser directement Python.
- Aucun test automatisé (unitaire/intégration) n'est fourni dans ce dépôt.
- La compilation `.exe` permet de lancer le code sans python

## 4. Architecture du dossier

```
CADASTROMANCY/
├── cadastromancy_app.py     # Logique métier : cadastre + DFI
├── postgres_setup.py        # Création SQL du schéma (tables, vues, fonctions)
├── ui_cadastromancy.py      # Interface graphique (tkinter)
├── check_project.py         # Diagnostic du projet avant déploiement
├── build_exe.py             # Compilation en exécutable Windows 
├── version.py                # Métadonnées de version
├── requirements.txt         # Dépendances Python
├── config/
│   ├── .env.example          # Modèle de configuration (à copier)
│   └── .env                  # Configuration réelle
├── telechargement/          # Fichiers temporaires 
└── style_qgis/              # Styles QGIS (dfi, filiation)
```

## 5. Rôle des scripts

| Script | Rôle |
|---|---|
| `cadastromancy_app.py` | Charge la config, se connecte à PostgreSQL, orchestre la mise à jour cadastre et DFI (`main`, `main_cadastrenn`, `main_dfi`). |
| `postgres_setup.py` | Génère le DDL SQL : tables `date_maj`, `parcelles`, `batiments`, `dfi`, `dfi_lien`, vues matérialisées, et les fonctions PL/pgSQL de traitement DFI et de filiation HTML. |
| `ui_cadastromancy.py` | Fenêtre tkinter : édition de la config, sélection du zip DFI, lien de téléchargement DGFiP, lancement du traitement. |
| `check_project.py` | Contrôle la structure, la syntaxe, les dépendances et la configuration avant mise en production. |
| `build_exe.py` | Génère un exécutable Windows autonome (PyInstaller), un script d'installation (`installer.bat`) et un manifeste de distribution. |
| `version.py` | Numéro de version et date de build, réutilisés par `build_exe.py`. |

## 6. Sécurité

- Ne jamais versionner ni partager `config/.env` (identifiants PostgreSQL en clair).
- Stocker `config/.env` hors des sauvegardes publiques ou partagées.
