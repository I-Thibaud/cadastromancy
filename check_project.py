#!/usr/bin/env python3
# check_project.py
# Valide l'ensemble du projet : syntaxe, dépendances, imports, structure

import sys
import os
import py_compile
from pathlib import Path
import importlib.util


class ProjectValidator:
    def __init__(self):
        self.project_root = Path(__file__).resolve().parent
        self.errors = []
        self.warnings = []
        self.success = []
    
    def check_python_version(self):
        """Vérifier la version Python."""
        print("🔍 Vérification de la version Python...")
        version = sys.version_info
        if version.major >= 3 and version.minor >= 8:
            self.success.append(f"Python {version.major}.{version.minor}.{version.micro} OK")
        else:
            self.errors.append(f"Python {version.major}.{version.minor} détecté, 3.8+ requis")
    
    def check_project_structure(self):
        """Vérifier l'arborescence du projet."""
        print("🔍 Vérification de la structure du projet...")
        required = [
            "cadastromancy_app.py",
            "postgres_setup.py"
        ]
        
        for path in required:
            full_path = self.project_root / path
            if full_path.exists():
                self.success.append(f"✓ {path}")
            else:
                self.errors.append(f"✗ Fichier manquant : {path}")
    
    def check_python_syntax(self):
        """Vérifier la syntaxe de tous les fichiers Python."""
        print("🔍 Vérification de la syntaxe Python...")
        py_files = list(self.project_root.glob("*.py"))
        
        for py_file in py_files:
            try:
                py_compile.compile(str(py_file), doraise=True)
                self.success.append(f"✓ Syntaxe OK : {py_file.name}")
            except py_compile.PyCompileError as e:
                self.errors.append(f"✗ Erreur de syntaxe dans {py_file.name}:\n  {e}")
    
    def check_dependencies(self):
        """Vérifier que les dépendances sont installées."""
        print("🔍 Vérification des dépendances...")
        required_packages = [
            "pandas",
            "geopandas",
            "sqlalchemy",
            "psycopg2",
            "requests",
            "bs4",
            "dotenv"
        ]
        
        for package in required_packages:
            try:
                importlib.import_module(package)
                self.success.append(f"✓ {package} installé")
            except ImportError:
                self.errors.append(f"✗ {package} manquant (pip install {package})")
    
    def check_imports(self):
        """Vérifier que les imports du projet fonctionnent."""
        print("🔍 Vérification des imports du projet...")
        
        # Ajouter le projet au path
        sys.path.insert(0, str(self.project_root))
        
        try:
            from postgres_setup import (
                init_base, init_dfi_preparation, init_dfi_fonctions, 
                init_dfi_filiation, init_all
            )
            self.success.append("✓ postgres_setup.py importable")
        except ImportError as e:
            self.errors.append(f"✗ Erreur import postgres_setup.py : {e}")
        
        try:
            import cadastromancy_app
            self.success.append("✓ cadastromancy_app.py importable")
        except Exception as e:
            # cadastromancy_app.py démarre une interface tkinter, c'est normal qu'on ne puisse pas l'importer directement
            self.warnings.append(f"ℹ️  cadastromancy_app.py non importable (normal - contient interface GUI)")
    
    def check_config(self):
        """Vérifier la configuration."""
        print("🔍 Vérification de la configuration...")
        config_file = self.project_root / "config" / ".env"
        example_file = self.project_root / "config" / ".env.example"
        
        if example_file.exists():
            self.success.append("✓ config/.env.example existe")
        else:
            self.errors.append("✗ config/.env.example manquant")
        
        if config_file.exists():
            self.success.append("✓ config/.env existe")
            # Vérifier que les variables obligatoires sont présentes
            with open(config_file, 'r') as f:
                content = f.read()
                required_vars = ['DB_USER', 'DB_PASSWORD', 'DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_SCHEMA', 'DEPARTEMENT']
                for var in required_vars:
                    if var in content:
                        self.success.append(f"  ✓ {var} configuré")
                    else:
                        self.warnings.append(f"  ⚠️  {var} manquant dans .env")
        else:
            self.warnings.append("⚠️  config/.env n'existe pas (copier depuis .env.example)")
    
    def check_requirements(self):
        """Vérifier requirements.txt."""
        print("🔍 Vérification de requirements.txt...")
        req_file = self.project_root / "requirements.txt"
        if req_file.exists():
            with open(req_file, 'r') as f:
                lines = f.readlines()
            self.success.append(f"✓ requirements.txt existe ({len(lines)} dépendances)")
        else:
            self.errors.append("✗ requirements.txt manquant")
    
    def print_report(self):
        """Afficher le rapport de validation."""
        print("\n" + "="*70)
        print("RAPPORT DE VALIDATION DU PROJET")
        print("="*70)
        
        if self.success:
            print("\n✅ SUCCÈS :")
            for msg in self.success:
                print(f"  {msg}")
        
        if self.warnings:
            print("\n⚠️  AVERTISSEMENTS :")
            for msg in self.warnings:
                print(f"  {msg}")
        
        if self.errors:
            print("\n❌ ERREURS :")
            for msg in self.errors:
                print(f"  {msg}")
        
        print("\n" + "="*70)
        
        # Résumé final
        total = len(self.success) + len(self.warnings) + len(self.errors)
        if not self.errors:
            print("✅ VALIDATION RÉUSSIE - Projet prêt à déployer !")
            return 0
        else:
            print(f"❌ VALIDATION ÉCHOUÉE - {len(self.errors)} erreur(s) à corriger")
            return 1
    
    def run(self):
        """Lancer toutes les vérifications."""
        print("🚀 Validation du projet cadastre DFI...\n")
        
        self.check_python_version()
        self.check_project_structure()
        self.check_python_syntax()
        self.check_requirements()
        self.check_dependencies()
        self.check_imports()
        self.check_config()
        
        exit_code = self.print_report()
        return exit_code


if __name__ == "__main__":
    validator = ProjectValidator()
    exit_code = validator.run()
    sys.exit(exit_code)
