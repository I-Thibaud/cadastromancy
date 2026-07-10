# Interface tkinter simple pour CADASTROMANCY
# À remplacer à la fin de main.py

import tkinter as tk
from tkinter import filedialog, messagebox
import webbrowser
from pathlib import Path
import subprocess
import sys
import os

from cadastromancy_app import main, DOSSIER_CONFIG


def create_env_file():
    """Crée le fichier .env à partir du modèle."""
    config_dir = DOSSIER_CONFIG
    env_file = config_dir / ".env"
    env_example = config_dir / ".env.example"
    
    if env_file.exists():
        return str(env_file)
    
    if env_example.exists():
        try:
            env_file.write_text(env_example.read_text())
            messagebox.showinfo("✅ Configuration créée",
                              f"Fichier .env créé.\n\n"
                              f"Renseignez vos identifiants PostgreSQL.")
            return str(env_file)
        except Exception as e:
            messagebox.showerror("❌ Erreur", f"Impossible de créer .env : {e}")
            return None
    else:
        messagebox.showerror("❌ Erreur", f".env.example introuvable")
        return None


def open_env_editor():
    """Ouvre le fichier .env dans l'éditeur par défaut."""
    config_dir = DOSSIER_CONFIG
    env_file = config_dir / ".env"
    
    if not env_file.exists():
        result = messagebox.askyesno("⚠️ .env manquant",
                                    ".env n'existe pas.\n\n"
                                    "Voulez-vous le créer ?")
        if result:
            env_file = create_env_file()
            if not env_file:
                return
        else:
            return
    
    try:
        if sys.platform == "win32":
            os.startfile(str(env_file))
        elif sys.platform == "darwin":
            subprocess.run(["open", str(env_file)])
        else:
            subprocess.run(["xdg-open", str(env_file)])
    except Exception as e:
        messagebox.showerror("❌ Erreur", f"Impossible d'ouvrir .env : {e}")


def open_download_link():
    """Ouvre le lien de téléchargement DFI."""
    webbrowser.open("https://data.economie.gouv.fr/explore/dataset/"
                   "documents-de-filiation-informatises-dfi-des-parcelles")


def choisir_zip_dfi():
    """Dialogue pour sélectionner un fichier ZIP DFI."""
    chemin = filedialog.askopenfilename(
        title="Sélectionner l'archive zip des DFI",
        filetypes=[("Archive zip", "*.zip"), ("Tous les fichiers", "*.*")])
    if chemin:
        txt_dfi.delete(0, tk.END)
        txt_dfi.insert(0, chemin)


# ============================================================================
# INTERFACE MINIMALISTE
# ============================================================================

root = tk.Tk()
root.title("CADASTROMANCY - Mise à jour cad-astrale")
root.geometry("550x500")
root.configure(background="#f0f0f0")

# Variables locales
row = 0

# --- Titre ---
title = tk.Label(root, text="🔮 CADASTROMANCY", 
                font=("Arial", 18, "bold"), bg="#f0f0f0", fg="#1f6f8b")
title.grid(row=row, column=0, columnspan=3, pady=15)
row += 1

subtitle = tk.Label(root, text="Tenez vos parcelles cadastrales à jour et parcourez leur généalogie !",
                   font=("Arial", 10), bg="#f0f0f0", fg="#666")
subtitle.grid(row=row, column=0, columnspan=3, pady=(0, 20))
row += 1

# --- Config PostgreSQL ---
config_label = tk.Label(root, text="Configuration PostgreSQL :", 
                       font=("Arial", 10, "bold"), bg="#f0f0f0")
config_label.grid(row=row, column=0, columnspan=3, sticky="w", padx=20)
row += 1

config_info = tk.Label(root, text="Paramètres lus dans config/.env",
                      font=("Arial", 9), bg="#f0f0f0", fg="#666")
config_info.grid(row=row, column=0, columnspan=3, sticky="w", padx=20)
row += 1

btn_config = tk.Button(root, text="⚙️  Éditer la configuration (.env)",
                      command=open_env_editor, width=35, bg="#2a9d8f", 
                      fg="white", font=("Arial", 9), relief="flat", padx=10, pady=8)
btn_config.grid(row=row, column=0, columnspan=3, padx=20, pady=10)
row += 1

# --- Séparateur ---
separator = tk.Frame(root, height=1, bg="#ccc")
separator.grid(row=row, column=0, columnspan=3, sticky="ew", padx=20, pady=10)
row += 1

# --- Fichier DFI ---
dfi_label = tk.Label(root, text="Documents de Filiation Informatisés (DFI) :",
                    font=("Arial", 10, "bold"), bg="#f0f0f0")
dfi_label.grid(row=row, column=0, columnspan=3, sticky="w", padx=20)
row += 1

dfi_info = tk.Label(root, text="(Optionnel) Sélectionner une archive ZIP",
                   font=("Arial", 9), bg="#f0f0f0", fg="#666")
dfi_info.grid(row=row, column=0, columnspan=3, sticky="w", padx=20)
row += 1

# ZIP file
tk.Label(root, text="Fichier ZIP :", bg="#f0f0f0").grid(row=row, column=0, sticky="w", padx=20)
txt_dfi = tk.Entry(root, width=50)
txt_dfi.grid(row=row, column=1, padx=10)
btn_browse = tk.Button(root, text="Parcourir...", command=choisir_zip_dfi,
                       bg="#e76f51", fg="white", font=("Arial", 9), relief="flat", padx=10)
btn_browse.grid(row=row, column=2, padx=(0, 20))
row += 1

# Download link
tk.Label(root, text="Télécharger : ", bg="#f0f0f0", font=("Arial", 9)).grid(row=row, column=0, sticky="w", padx=20)
link = tk.Label(root, text="data.economie.gouv.fr", bg="#f0f0f0", fg="#2a9d8f", 
               font=("Arial", 9, "underline"), cursor="hand2")
link.grid(row=row, column=1, sticky="w")
link.bind("<Button-1>", lambda e: open_download_link())
row += 1

# --- Séparateur ---
separator = tk.Frame(root, height=1, bg="#ccc")
separator.grid(row=row, column=0, columnspan=3, sticky="ew", padx=20, pady=10)
row += 1

# --- Boutons action ---
btn_launch = tk.Button(root, text="▶️  Lancer la mise à jour",
                       command=lambda: main(txt_dfi.get().strip()), width=30, bg="#1f6f8b", fg="white",
                       font=("Arial", 11, "bold"), relief="flat", padx=20, pady=10)
btn_launch.grid(row=row, column=0, columnspan=2, padx=20, pady=15)

btn_close = tk.Button(root, text="Fermer", command=root.quit,
                      bg="#999", fg="white", font=("Arial", 9), relief="flat", padx=10)
btn_close.grid(row=row, column=2, padx=(0, 20), pady=15)

# ============================================================================
root.mainloop()
