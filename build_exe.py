#!/usr/bin/env python3
# build_exe.py
# Compile le projet en exécutable Windows avec PyInstaller

import sys
import subprocess
import shutil
import os
from pathlib import Path
from shutil import rmtree
import json
from datetime import datetime

from version import __version__


class ExeBuilder:
    def __init__(self):
        self.project_root = Path(__file__).resolve().parent
        self.dist_folder = self.project_root / "dist"
        self.build_folder = self.project_root / "build"
        self.spec_folder = self.project_root
        # En --onedir, PyInstaller crée dist/CADASTROMANCY/ (d'après --name) :
        # c'est ce dossier, pas dist/ directement, qui contient l'exe + ses DLL.
        self.app_folder = self.dist_folder / "CADASTROMANCY"
    
    def log(self, message, level="INFO"):
        """Logger un message."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        prefix = {
            "INFO": "ℹ️ ",
            "SUCCESS": "✅",
            "ERROR": "❌",
            "WARNING": "⚠️ "
        }.get(level, "●")
        print(f"[{timestamp}] {prefix} {message}")
    
    def check_pyinstaller(self):
        """Vérifier que PyInstaller est installé."""
        self.log("Vérification de PyInstaller...")
        try:
            import PyInstaller
            self.log(f"PyInstaller {PyInstaller.__version__} trouvé", "SUCCESS")
            return True
        except ImportError:
            self.log("PyInstaller non installé", "ERROR")
            self.log("Installation : pip install PyInstaller", "INFO")
            return False
    
    def clean_previous_builds(self):
        """Nettoyer les builds précédents."""
        self.log("Nettoyage des builds précédents...")
        for folder in [self.dist_folder, self.build_folder, self.spec_folder / "CADASTROMANCY.spec"]:
            if isinstance(folder, Path) and folder.exists():
                if folder.is_dir():
                    rmtree(folder)
                    self.log(f"  Supprimé : {folder.name}")
                else:
                    folder.unlink()
                    self.log(f"  Supprimé : {folder.name}")
    
    def find_libs_folders(self, package_names):
        """
        Détecte les dossiers *.libs* (DLL natives vendorisées par delvewheel)
        situés à côté d'un paquet dans site-packages.
        Concerne typiquement pyogrio, fiona, shapely, pyproj sous Windows :
        leurs DLL GDAL/GEOS/PROJ ne sont PAS dans le paquet lui-même, mais dans
        un dossier voisin (ex: "pyogrio.libs-a1b2c3d4"), que --collect-all
        ne ramasse pas forcément si les hooks PyInstaller sont absents/anciens.
        Retourne la liste des dossiers trouvés (chemins absolus).
        """
        import importlib

        trouves = []
        for name in package_names:
            try:
                mod = importlib.import_module(name)
            except ImportError:
                self.log(f"  {name} non installé dans cet environnement, ignoré", "WARNING")
                continue

            if not getattr(mod, "__file__", None):
                continue

            pkg_dir = Path(mod.__file__).resolve().parent
            site_packages = pkg_dir.parent  # dossier site-packages

            # delvewheel nomme les dossiers "<nom>.libs" ou "<nom>.libs-<hash>"
            for candidat in site_packages.glob(f"{name}.libs*"):
                if candidat.is_dir():
                    trouves.append(candidat)
                    self.log(f"  ✓ Dossier .libs trouvé : {candidat.name}", "SUCCESS")

        if not trouves:
            self.log("  Aucun dossier .libs trouvé pour ces paquets (normal si aucun "
                      "ne vendorise ses DLL via delvewheel sur cette machine)", "INFO")
        return trouves

    def build_exe(self):
        """Construire l'exécutable avec PyInstaller."""
        self.log("Construction de l'exécutable...")
        
        main_script = self.project_root / "cadastromancy_app.py"
        if not main_script.exists():
            self.log(f"Script principal introuvable : {main_script}", "ERROR")
            return False

        # Chemin vers l'icône
        icon_path = self.project_root / "assets" / "cadastromancy.ico"
        if not icon_path.exists():
            self.log(f"Icône introuvable : {icon_path}", "WARNING")
            icon_arg = "--icon=NONE"
        else:
            icon_arg = f"--icon={icon_path}"

        # Détection des dossiers .libs (DLL GDAL/GEOS/PROJ) à embarquer explicitement
        self.log("Recherche des dossiers .libs (DLL natives GDAL/GEOS/PROJ)...")
        # fiona volontairement exclu : geopandas utilise pyogrio comme moteur ;
        # embarquer aussi Fiona.libs créerait deux copies de GDAL en conflit
        # (chargement DLL ambigu -> "GDAL DLL could not be found").
        libs_folders = self.find_libs_folders(["pyogrio", "shapely", "pyproj"])

        # Commande PyInstaller
        cmd = [
            sys.executable, "-m", "PyInstaller",
            "--name=CADASTROMANCY",              # Nom de l'exécutable / du dossier
            "--onedir",                          # Dossier de sortie, PAS --onefile :
            # --onefile ré-extrait toutes les DLL dans %TEMP% à CHAQUE lancement.
            # Sur un poste avec antivirus strict ou stratégie de sécurité
            # (AppLocker/SRP, courant en collectivité), cette extraction répétée
            # dans un dossier utilisateur temporaire est bloquée -> "Accès refusé"
            # (déjà rencontré avec fiona, maintenant avec psycopg2 : même cause).
            # En --onedir, les DLL sont extraites UNE FOIS à la compilation, dans
            # un dossier stable livré avec l'exe : plus d'extraction au lancement.
            # PAS de --windowed : le script utilise print() pour la progression
            # (avec --windowed, sys.stdout est None sous Windows -> crash au 1er print())
            # La fenêtre tkinter s'ouvre normalement en plus de la console.
            icon_arg, # Pas d'icône (à ajouter si besoin)
            #"--add-data", f"config{os.pathsep}config",  # Ne pas Inclure config afin que l'uitilisateur puisse saisir ses propres param
            "--collect-all=pandas",                  # Inclure pandas
            "--collect-all=geopandas",               # Inclure geopandas
            "--collect-all=pyogrio",                 # Moteur GDAL de geopandas
            "--collect-all=pyproj",                  # proj.db (essentiel avec to_crs)
            "--collect-all=shapely",                 # DLL GEOS
            "--collect-all=certifi",                 # cacert.pem pour les téléchargements HTTPS
            "--copy-metadata=pandas",
            "--copy-metadata=geopandas",
            "--copy-metadata=pyproj",
            "--copy-metadata=shapely",
            "--copy-metadata=pyogrio",
            "--collect-all=sqlalchemy",              # Inclure sqlalchemy
            # geoalchemy2 : requis par gdf.to_postgis(), importé dynamiquement
            # par geopandas à l'intérieur de la méthode -> invisible pour
            # l'analyse statique de PyInstaller sans cette ligne explicite.
            "--collect-all=geoalchemy2",
            "--collect-all=dotenv",                  # Inclure python-dotenv
            "--collect-all=psycopg2",                # Inclure le driver PostgreSQL
            "--collect-all=bs4",                     # Inclure BeautifulSoup
            "--collect-all=requests",                # Inclure requests
            # Exclusion explicite : évite qu'une éventuelle installation de fiona
            # dans l'environnement de build soit embarquée en plus de pyogrio
            # (deux copies de GDAL en conflit = DLL introuvable/incompatible).
            "--exclude-module=fiona",
        ]

        # Ajout explicite des dossiers .libs trouvés (filet de sécurité si les hooks
        # PyInstaller ne les ont pas ramassés via les --collect-all ci-dessus)
        for dossier in libs_folders:
            cmd += ["--add-binary", f"{dossier}{os.pathsep}{dossier.name}"]

        cmd.append(str(main_script))
        
        try:
            result = subprocess.run(cmd, check=True, cwd=str(self.project_root))
            self.log("Construction réussie !", "SUCCESS")
            return True
        except subprocess.CalledProcessError as e:
            self.log(f"Erreur de construction : {e}", "ERROR")
            return False
        
    def copy_env_example(self):
        """Copie .env.example à côté de l'exe pour que l'utilisateur le copie."""
        self.log("Copie du fichier de configuration d'exemple...")
        
        env_example_src = self.project_root / "config" / ".env.example"
        config_dest = self.app_folder / "config"
        config_dest.mkdir(parents=True, exist_ok=True)
        
        env_example_dest = config_dest / ".env.example"
        if env_example_src.exists():
            shutil.copy(env_example_src, env_example_dest)
            self.log(f"✓ {env_example_dest} prêt à être copié en .env", "SUCCESS")
        else:
            self.log(f"⚠️  {env_example_src} introuvable", "WARNING")

    def create_installer_batch(self):
        """Créer un script batch pour faciliter la distribution."""
        batch_content = r"""@echo off
REM Script d'installation - Pipeline Cadastre DFI
REM A exécuter apres avoir extrait le .exe

echo.
echo ========================================
echo   CADASTROMANCY - Installation
echo ========================================
echo.

REM Verifier que PostgreSQL est accessible
echo Verifying PostgreSQL connection...
where psql >nul 2>nul
if errorlevel 1 (
    echo.
    echo ERREUR : PostgreSQL non trouve dans le PATH
    echo Veuillez installer PostgreSQL et relancer ce script
    echo.
    pause
    exit /b 1
)

REM Créer le dossier config s'il n'existe pas
if not exist config mkdir config

REM Vérifier si .env existe
if not exist config\.env (
    echo.
    echo PREMIERE UTILISATION : Creation de config\.env
    copy config\.env.example config\.env
    echo.
    echo IMPORTANT : Editez config\.env avec vos identifiants PostgreSQL
    echo.
    echo Appuyez sur une touche pour ouvrir config\.env dans notepad...
    pause
    notepad config\.env
)

echo.
echo Configuration : OK
echo.
echo Lancement du programme...
echo.

REM Lancer l'exe
CADASTROMANCY.exe

pause
"""
        
        batch_file = self.app_folder / "installer.bat"
        with open(batch_file, 'w', encoding='utf-8') as f:
            f.write(batch_content)
        
        self.log(f"Fichier installer.bat créé", "SUCCESS")
    
    def create_readme_exe(self):
        """Créer un README pour la distribution .exe."""
        readme_content = """# CADASTROMANCY - Version Compilée

## Prérequis

- **Windows 7+** (l'exécutable est inclus)
- **PostgreSQL 12+** avec **PostGIS** installés
- **Connexion PostgreSQL** fonctionnelle

## Démarrage rapide

### 1. Première utilisation

```bash
# Double-cliquer sur : installer.bat
# (Cela créera config/.env et ouvrira notepad pour l'éditer)
```

### 2. Remplir config/.env

Éditer `config/.env` avec vos identifiants PostgreSQL :

```
DB_USER=votre_utilisateur
DB_PASSWORD=votre_mot_de_passe
DB_HOST=localhost
DB_PORT=5432
DB_NAME=votre_bdd
DB_SCHEMA=ref_cadastre_nn
DEPARTEMENT=29
CODES_COMMUNE=017,040,076,084,...
```

### 3. Lancer le programme

**Option A :** Double-cliquer sur `installer.bat`  
**Option B :** Double-cliquer sur `CADASTROMANCY.exe`

## Utilisation

1. **Mise à jour du cadastre** : Cliquer "Lancer la mise à jour du cadastre"
2. **Traitement DFI** (optionnel) :
   - Télécharger le zip DFI sur https://data.economie.gouv.fr
   - Cliquer "Parcourir..." et sélectionner le fichier zip
   - Cliquer "Lancer la mise à jour du cadastre"

## Dépannage

### Erreur : "PostgreSQL non trouvé"

```
→ Installer PostgreSQL + PostGIS
→ Ajouter PostgreSQL au PATH Windows
→ Relancer l'installer.bat
```

### Erreur : "Connection refused"

```
→ Vérifier que PostgreSQL est en cours d'exécution
→ Vérifier les identifiants dans config/.env
→ Tester : psql -U user -h host -d database
```

### Erreur : "Table (votre_schéma).dfi n'existe pas"

```
→ Les tables seront créées automatiquement à la première utilisation
```

## Documentation complète

Consultez les fichiers .md dans le dossier du projet pour plus de détails.

## Sécurité

- Ne jamais partager votre `config/.env` (contient votre mot de passe)
- Stocker `config/.env` dans un endroit sécurisé
- Ne pas inclure `config/.env` dans les backups publics

## Version

- **Version** : {version} Compilée
- **Build date** : {build_date}
- **Python** : 3.10+ (inclus)

## Support

En cas de problème, consulter la documentation ou relancer le programme avec une ligne de commande pour voir les logs détaillés.

---

**Bonne utilisation ! **
""".format(build_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), version=__version__)
        
        readme_file = self.app_folder / "README_COMPILATION.txt"
        with open(readme_file, 'w', encoding='utf-8') as f:
            f.write(readme_content)
        
        self.log(f"README_COMPILATION.txt créé", "SUCCESS")
    
    def create_distribution_package(self):
        """Créer un package de distribution complet."""
        self.log("Création du package de distribution...")
        
        package = {
            "build_date": datetime.now().isoformat(),
            "version": __version__,
            "executable": "CADASTROMANCY.exe",
            "installer": "installer.bat",
            "files": {
                "exe": str(self.app_folder / "CADASTROMANCY.exe"),
                "batch": str(self.app_folder / "installer.bat"),
                "readme": str(self.app_folder / "README_COMPILATION.txt")
            }
        }
        
        manifest_file = self.app_folder / "manifest_distribution.json"
        with open(manifest_file, 'w') as f:
            json.dump(package, f, indent=2)
        
        self.log(f"Package de distribution créé", "SUCCESS")
    
    def print_summary(self):
        """Afficher le résumé de la compilation."""
        print("\n" + "="*70)
        print("                    COMPILATION RÉUSSIE ✅")
        print("="*70 + "\n")
        
        exe_file = self.app_folder / "CADASTROMANCY.exe"
        if exe_file.exists():
            taille_mo = sum(f.stat().st_size for f in self.app_folder.rglob("*") if f.is_file()) / (1024 * 1024)
            print(f"   Exécutable créé : {exe_file.name}")
            print(f"   Taille totale du dossier : {taille_mo:.1f} MB")
            print(f"   Chemin : {self.app_folder}")
        
        print("\n    Fichiers de distribution (dans dist/CADASTROMANCY/) :")
        print(f"   ✓ CADASTROMANCY.exe          (exécutable)")
        print(f"   ✓ installer.bat                 (installation facile)")
        print(f"   ✓ README_COMPILATION.txt        (aide)")
        print(f"   ✓ manifest_distribution.json    (metadata)")
        print(f"   ✓ _internal/                     (DLL et dépendances - NE PAS SUPPRIMER)")
        
        print("\n     Prochaines étapes :")
        print(f"   1. Copier le dossier 'dist/CADASTROMANCY' complet (avec _internal/)")
        print(f"   2. Renommer en : 'CADASTROMANCY_v{__version__}'")
        print(f"   3. Créer un .zip : 'CADASTROMANCY_v{__version__}.zip'")
        print(f"   4. Distribuer aux utilisateurs")
        
        print("\n💡 Installation par l'utilisateur :")
        print(f"   1. Extraire le .zip")
        print(f"   2. Double-cliquer sur 'installer.bat'")
        print(f"   3. Éditer config/.env avec ses identifiants")
        print(f"   4. Relancer 'installer.bat' ou CADASTROMANCY.exe")
        
        print("\n" + "="*70 + "\n")
    
    def build(self):
        """Lancer le build complet."""
        print("\n" + "="*70)
        print("      COMPILATION EXE - Pipeline Cadastre DFI")
        print("="*70 + "\n")
        
        # Vérification
        if not self.check_pyinstaller():
            self.log("Installation de PyInstaller...", "INFO")
            subprocess.run([sys.executable, "-m", "pip", "install", "PyInstaller"], check=True)
        
        # Nettoyage
        self.clean_previous_builds()
        
        # Build
        if not self.build_exe():
            return False

        # Copier .env.example pour que l'utilisateur le réutilise
        self.copy_env_example()
               
        # Fichiers additionnels
        self.create_installer_batch()
        self.create_readme_exe()
        self.create_distribution_package()
        
        # Résumé
        self.print_summary()
        
        return True


if __name__ == "__main__":
    builder = ExeBuilder()
    success = builder.build()
    sys.exit(0 if success else 1)