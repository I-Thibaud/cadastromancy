# -----------------------------------------------------------------------------
# Outils de téléchargement et de chargement du cadastre non nominatif
# et des Documents de Filiation Informatisés (DFI) dans une BDD Postgres/PostGIS
# Auteur : Thibaud IDOUX
# -----------------------------------------------------------------------------
# 20230831 : Création de la première mouture du code
# 20230920 : Refresh des 2 Materialized Views Parcelles et Batiments
# 20240725 : Mise en place
# 20260707 : Refactorisation :
#            - configuration via config/.env (python-dotenv)
#            - DFI chargé depuis un fichier zip local (plus d'URL)
#            - intégration du chargement DFI (ex test_suite_dfi.py)
#            - insertion DFI en INSERT ... ON CONFLICT DO NOTHING
#            - lancement des traitements SQL (liens, statuts, géométries)
# -----------------------------------------------------------------------------

import os
import sys
import gzip
import zipfile
import shutil
from pathlib import Path
from datetime import datetime

# interface
from tkinter import *
from tkinter import messagebox

# data / spatial
import pandas as pd
import geopandas as gpd
from sqlalchemy import create_engine, URL, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

# web
import requests
from bs4 import BeautifulSoup

# configuration
from dotenv import load_dotenv

# autre librairie du projet
from postgres_setup import init_base, init_dfi_preparation, init_dfi_fonctions, init_dfi_filiation, init_all

# ============================================================================
#   GESTION DES VARIABLES GLOBALES
# ============================================================================

if getattr(sys, 'frozen', False):
    # On est dans un .exe compilé par PyInstaller
    # sys.executable = chemin vers l'exe (ex: C:\Users\...\CADASTROMANCY.exe)
    DOSSIER_PROJET = Path(sys.executable).parent
else:
    # On lance le script Python directement
    # __file__ = chemin du script (ex: C:\repos\cadastromancy_app.py)
    DOSSIER_PROJET = Path(__file__).resolve().parent

DOSSIER_CONFIG = DOSSIER_PROJET / "config"

# Dossier temp pour les téléchargements (ne pas utiliser le dossier du projet)
# Sinon, sans droits admin, on ne peut pas créer le dossier s'il est dans Program Files
import tempfile
DOSSIER_TELECHARGEMENT = Path(tempfile.gettempdir()) / "cadastromancy_telechargement"




# ----------------------------------------------
#   Fonction : charger la configuration .env
# ----------------------------------------------
def charger_config():
    """Charge config/.env et retourne un dictionnaire de configuration validé."""
    chemin_env = DOSSIER_CONFIG / ".env"
    
    if not chemin_env.exists():
        raise FileNotFoundError(
            f"Fichier de configuration introuvable : {chemin_env}\n"
            "Copiez config/.env.example vers config/.env et renseignez les valeurs."
        )
    
    load_dotenv(chemin_env)
    
    obligatoires = ["DB_USER", "DB_PASSWORD", "DB_HOST", "DB_PORT",
                    "DB_NAME", "DB_SCHEMA", "DEPARTEMENT", "CODES_COMMUNE"]
    manquantes = [v for v in obligatoires if not os.getenv(v)]
    if manquantes:
        raise ValueError("Variables manquantes dans config/.env : " + ", ".join(manquantes))

    dep = os.getenv("DEPARTEMENT").strip()            # ex : '29'
    codes_commune = [c.strip() for c in os.getenv("CODES_COMMUNE").split(",") if c.strip()]

    cfg = {
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "host": os.getenv("DB_HOST"),
        "port": int(os.getenv("DB_PORT")),
        "database": os.getenv("DB_NAME"),
        "schema": os.getenv("DB_SCHEMA"),
        "departement": dep,                            # '29'
        "dep_dfi": dep.ljust(3, "0"),                  # '290' (code département DFI sur 3 car.)
        "codes_commune": codes_commune,                # ['017', '040', ...]
        "lst_insee": [dep + c for c in codes_commune]  # ['29017', '29040', ...]
    }
    return cfg

# ----------------------------------------------
#   Fonction : se connecter à la BDD
# ----------------------------------------------
def connect_bdd(cfg):
    url = URL.create(
        drivername="postgresql",
        username=cfg["user"],
        password=cfg["password"],
        host=cfg["host"],
        database=cfg["database"],
        port=cfg["port"],
    )
    engine = create_engine(url)
    # Test de connexion immédiat (échoue tôt et proprement)
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return engine


# ---------------------------------
#   Fonction : procédure principale
# ---------------------------------
def main(txt_dfi):
    try:
        cfg = charger_config()
        engine = connect_bdd(cfg)
    except Exception as e:
        messagebox.showerror(title="Erreur de configuration",
                             message=f"Impossible de démarrer :\n{e}")
        return

    try:
        # initialisation lors de la 1ère utilisation
        init_first_use(engine, cfg)
        verifier_et_initialiser_schema(engine, cfg)  # Schéma DFI

        # maj du cadastre nn
        print("\n🔮 Mise à jour du cadastre non nominatif...")
        main_cadastrenn(engine, cfg)

        # maj DFI (généalogie parcelles) si un zip a été sélectionné
        chemin_zip = txt_dfi
        if chemin_zip:
            # Vérifier/initialiser le schéma DFI avant de traiter
            print("\n🔮 Mise à jour des Documents de Filiation Informatisés (DFI)...")
            try:
                verifier_et_initialiser_schema(engine, cfg)
            except Exception as e:
                messagebox.showerror(title="Erreur d'initialisation SQL",
                                     message=f"Impossible d'initialiser le schéma DFI :\n{e}")
                return
            main_dfi(engine, cfg, chemin_zip)
            messagebox.showinfo(title="Réussite", message=f"Mise à jour terminée !\nCadastre et DFI sont à jour.")
    finally:
        engine.dispose()
    


# ---------------------------------
#   Fonction : date de la dernière mise à jour du cadastre sur data.gouv
# ---------------------------------
def recup_last_date():
    url = "https://cadastre.data.gouv.fr/data/etalab-cadastre/"
    response = requests.get(url, timeout=60)
    soup = BeautifulSoup(response.content, "html.parser")

    list_of_links = [link.get("href") for link in soup.find_all("a") if link.get("href")]

    if len(list_of_links) >= 2:
        date_maj = str(list_of_links[-2])
        print(f"Millésime disponible en ligne  : {date_maj}")
    else:
        date_maj = "01/01/1900"
    return date_maj


# ---------------------------------
#   Fonction : téléchargement d'un fichier
# ---------------------------------
def telecharger_data(url, nom_fichier):
    DOSSIER_TELECHARGEMENT.mkdir(exist_ok=True)
    chemin_fichier_local = DOSSIER_TELECHARGEMENT / nom_fichier

    response = requests.get(url, timeout=600)
    if response.status_code == 200:
        with open(chemin_fichier_local, "wb") as fichier_local:
            fichier_local.write(response.content)
        print("Téléchargement réussi :", nom_fichier)
        return str(chemin_fichier_local)
    else:
        print("Échec du téléchargement. Code de statut :", response.status_code)
        return 0


def decompress_cadastrenn(chemin_fichier_local):
    chemin_fichier_decompresse = os.path.splitext(chemin_fichier_local)[0]  # retire .gz
    with gzip.open(chemin_fichier_local, "rb") as fichier_gz, \
         open(chemin_fichier_decompresse, "wb") as fichier_decompresse:
        shutil.copyfileobj(fichier_gz, fichier_decompresse)
    print("Décompression réussie.")


# ---------------------------------
#   Fonction : initialisation des tables et schéma
# ---------------------------------
def init_first_use(engine, cfg):
    """Crée le schéma de base, les tables et vues matérialisées."""
    init_base(engine, cfg)


# -----------------------------------------------------------------------------
#                       MISE A JOUR DU CADASTRE NN
# -----------------------------------------------------------------------------
def main_cadastrenn(engine, cfg):
    schema = cfg["schema"]

    # ------------------------------------------------------------------
    # ETAPE 1 : VERIFICATION DE LA DATE POUR VOIR SI BESOIN DE METTRE A JOUR
    # ------------------------------------------------------------------
    date_maj_datagouv = recup_last_date()[0:-1]
    date_maj_datagouv = datetime.strptime(date_maj_datagouv, "%Y-%m-%d").date()

    # Requête paramétrée (évite l'injection SQL)
    with engine.connect() as connection:
        result = connection.execute(
            text(f"SELECT * FROM {schema}.date_maj WHERE last_date_maj = :d"),
            {"d": date_maj_datagouv},
        ).scalar()



    # ------------------------------------------------------------------
    # ETAPE 2 : MISE A JOUR
    # ------------------------------------------------------------------
    if result is None:
        dep = cfg["departement"]
        lst_data = [
            (f"cadastre-{dep}-batiments.json.gz", "batiments"),
            (f"cadastre-{dep}-parcelles.json.gz", "parcelles"),
        ]

        nb_err = 0
        for nom_gz, table in lst_data:
            url = (f"https://cadastre.data.gouv.fr/data/etalab-cadastre/latest/"
                   f"geojson/departements/{dep}/{nom_gz}")
            chemin_fichier_local = telecharger_data(url, nom_gz)
            if chemin_fichier_local != 0:
                decompress_cadastrenn(chemin_fichier_local)
                fichier_geojson = os.path.splitext(chemin_fichier_local)[0]

                # Lecture + filtre sur les communes de la config
                gdf = gpd.read_file(fichier_geojson)
                gdf_filtered = gdf[gdf["commune"].isin(cfg["lst_insee"])]

                # Reprojection en Lambert 93
                gdf_reprojected = gdf_filtered.to_crs("EPSG:2154")

                with engine.connect() as connection:
                    connection.execute(text(f"TRUNCATE {schema}.{table} RESTART IDENTITY;"))
                    connection.commit()

                gdf_reprojected.to_postgis(table, engine, schema=schema,
                                           if_exists="append", index=False)

                with engine.connect() as connection:
                    connection.execute(text(f"REFRESH MATERIALIZED VIEW {schema}.mvw_{table};"))
                    connection.commit()
            else:
                nb_err += 1
        
        print(f"Nombre d'erreurs : {nb_err}")

        if nb_err == 0:
            with engine.connect() as connection:
                connection.execute(
                    text(f"UPDATE {schema}.date_maj SET last_date_maj = :d"),
                    {"d": date_maj_datagouv},
                )
                connection.commit()
            print("Le cadastre a été mis à jour. Le nouveau millésime est à la date du " + str(date_maj_datagouv))
            #messagebox.showinfo(title="Travail terminé",message="Le cadastre a été mis à jour. Le nouveau millésime est à la date du " + str(date_maj_datagouv))
        else:
            print("Erreur lors du téléchargement du cadastre non nominatif - la base de données n'a pas été mise à jour")
            #messagebox.showinfo(title="Travail terminé",message="Erreur lors du téléchargement du cadastre non nominatif - la base de données n'a pas été mise à jour")
    else:
        print("Le cadastre est déjà à jour sur le serveur. Le millésime est à la date du " + str(date_maj_datagouv))
        messagebox.showinfo(title="Travail terminé",
                            message="Le cadastre est déjà à jour sur le serveur. "
                                    "Le millésime est à la date du " + str(date_maj_datagouv))


# -----------------------------------------------------------------------------
#                       MISE A JOUR DES DFI (généalogie des parcelles)
# -----------------------------------------------------------------------------
def extraire_fichier_departement(zip_file_path, dep_dfi, dir_export):
    """Extrait de l'archive zip le fichier du département (ex : contenant 'dep290')."""
    motif = f"dep{dep_dfi}"
    with zipfile.ZipFile(zip_file_path, "r") as zip_ref:
        for file_info in zip_ref.infolist():
            if motif in file_info.filename:
                zip_ref.extract(file_info.filename, path=dir_export)
                return os.path.join(dir_export, file_info.filename)
    print(f"Aucun fichier contenant '{motif}' n'a été trouvé dans l'archive.")
    return None


def normaliser_ligne_dfi(ligne):
    """
    Le fichier DFI contient 10 champs (avec colonne XNUMX) + parcelles.
    Structure : dep;commune;prefixe;id_dfi;nature_dfi;date;XNUMX;n_lot;type;parcelles
    On regroupe toutes les parcelles en 10e colonne.
    """
    ligne = ligne.strip().rstrip(";")
    champs = ligne.split(";")
    
    # Si plus de 10 champs, les champs après le 10e sont des parcelles
    if len(champs) > 10:
        # Garder les 10 premiers + regrouper les parcelles
        return ";".join(champs[:10] + [",".join(champs[10:])])
    
    return ligne


def nettoyer_fichier_dfi(chemin_source, chemin_sortie):
    """Pré-traite le fichier brut DFI vers un fichier à 10 colonnes."""
    with open(chemin_source, "r", encoding="latin-1") as f_in:
        lignes = [normaliser_ligne_dfi(l) for l in f_in if l.strip()]
    with open(chemin_sortie, "w", encoding="utf-8") as f_out:
        f_out.write("\n".join(lignes))
    return chemin_sortie


def inserer_on_conflict_do_nothing(table, conn, keys, data_iter):
    """
    Méthode d'insertion pandas -> PostgreSQL en INSERT ... ON CONFLICT DO NOTHING.
    Nécessite la contrainte d'unicité dfi_unique (voir sql/01_preparation_dfi.sql).
    """
    data = [dict(zip(keys, row)) for row in data_iter]
    if not data:
        return 0
    stmt = pg_insert(table.table).values(data).on_conflict_do_nothing(
        index_elements=["dep", "code_commune", "prefixe_section",
                        "id_dfi", "n_lot_dfi", "type"]
    )
    result = conn.execute(stmt)
    return result.rowcount

def valider_format_dfi(chemin_fichier_brut, nb_colonnes_attendu=10):
    """
    Vérifie que le format du fichier DFI brut correspond à ce qui est attendu.
    Compte le nombre de champs sur les lignes de type 1 (mères, sans parcelles filles
    variables) pour éviter les faux positifs liés au nombre de parcelles.
    
    nb_colonnes_attendu = nombre de colonnes de MÉTADONNÉES (hors parcelles).
    Actuellement : dep, code_commune, prefixe_section, id_dfi, nature_dfi,
                   date_valide_dfi, geometre, xnumx, n_lot_dfi, type = 10 colonnes
    
    Retourne (ok: bool, message: str, nb_detecte: int)
    """
    nb_champs_detectes = {}
    
    with open(chemin_fichier_brut, "r", encoding="latin-1") as f:
        for i, ligne in enumerate(f):
            if i > 200:  # échantillon suffisant, pas besoin de tout lire
                break
            ligne = ligne.strip().rstrip(";")
            if not ligne:
                continue
            champs = ligne.split(";")
            # On ne garde que les lignes de type "1" avec 1 seule parcelle mère
            # (nb_champs total = nb_colonnes_attendu + 1 parcelle)
            if len(champs) == nb_colonnes_attendu + 1 and champs[nb_colonnes_attendu - 1] == "1":
                nb_champs_detectes[len(champs)] = nb_champs_detectes.get(len(champs), 0) + 1
    
    if not nb_champs_detectes:
        return False, (
            f"⚠️  Impossible de détecter le format du fichier "
            f"(aucune ligne de référence trouvée dans les 200 premières lignes)."
        ), None
    
    nb_detecte = max(nb_champs_detectes, key=nb_champs_detectes.get) - 1  # -1 pour retirer la parcelle
    
    if nb_detecte == nb_colonnes_attendu:
        return True, f"✓ Format DFI conforme ({nb_detecte} colonnes de métadonnées).", nb_detecte
    else:
        return False, (
            f"⚠️  ALERTE : format DFI différent de celui attendu !\n"
            f"   Colonnes détectées : {nb_detecte}\n"
            f"   Colonnes attendues : {nb_colonnes_attendu}\n"
            f"   Le fichier a peut-être changé de structure (nouveau millésime DGFiP).\n"
            f"   Vérifiez manuellement les premières lignes avant de continuer."
        ), nb_detecte
    
def charger_dfi(engine, cfg, chemin_fichier_clean):
    """Charge le fichier DFI nettoyé, filtre sur les communes et insère en base."""
    noms_colonnes = ["dep", "code_commune", "prefixe_section", "id_dfi","nature_dfi",
                      "date_valide_dfi", "geometre", "xnumx","n_lot_dfi", "type", "parcelles"]

    df_dfi = pd.read_csv(chemin_fichier_clean, sep=";", names=noms_colonnes, dtype=str)

    # Filtre département + communes
    df_dfi = df_dfi[df_dfi["dep"] == cfg["dep_dfi"]]
    df_dfi = df_dfi[df_dfi["code_commune"].isin(cfg["codes_commune"])]

    # Colonnes utiles (le nom du géomètre, anonymisé, est écarté)
    col_utiles = ["dep", "code_commune", "prefixe_section", "id_dfi", "nature_dfi",
              "date_valide_dfi", "n_lot_dfi", "type", "parcelles"]
    df_dfi = df_dfi[col_utiles]

    # Nettoyage : espaces dans la liste des parcelles, listes vides -> NULL
    df_dfi["parcelles"] = df_dfi["parcelles"].str.replace(" ", "", regex=False)
    df_dfi["parcelles"] = df_dfi["parcelles"].replace("", None)

    # Insertion sans doublons (ON CONFLICT DO NOTHING)
    nb = df_dfi.to_sql(name="dfi", con=engine, schema=cfg["schema"],
                       if_exists="append", index=False, chunksize=1000,
                       method=inserer_on_conflict_do_nothing)
    print(f"DFI : {len(df_dfi)} lignes lues, {nb} nouvelles lignes insérées "
          f"({len(df_dfi) - (nb or 0)} déjà présentes).")
    return len(df_dfi), nb

def verifier_et_reparer_installation():
    """Diagnostic complet + réparation."""
    try:
        cfg = charger_config()
        engine = connect_bdd(cfg)
        print("\n✅ Vérification complète de l'installation...")
        init_first_use(engine, cfg)              # Tables de base
        verifier_et_initialiser_schema(engine, cfg)  # Schéma DFI
        engine.dispose()
        messagebox.showinfo("Installation OK",
                        "✓ Schéma de base OK\n"
                        "✓ Schéma DFI OK\n"
                        "Prêt à fonctionner !")
    except Exception as e:
        messagebox.showerror("Erreur", str(e))

def verifier_et_initialiser_schema(engine, cfg):
    """Vérifie et initialise le schéma DFI."""
    schema = cfg["schema"]
    
    def existe_colonne(conn, table, col):
        result = conn.execute(
            text("SELECT EXISTS("
                 "  SELECT 1 FROM information_schema.columns "
                 "  WHERE table_schema = :s AND table_name = :t AND column_name = :c)")
            , {"s": schema, "t": table, "c": col}
        ).scalar()
        return result
    
    def existe_table(conn, table):
        result = conn.execute(
            text("SELECT EXISTS("
                 "  SELECT 1 FROM information_schema.tables "
                 "  WHERE table_schema = :s AND table_name = :t)")
            , {"s": schema, "t": table}
        ).scalar()
        return result
    
    def existe_fonction(conn, nom_fonction, nb_params=None):
        query = (
            "SELECT EXISTS("
            "  SELECT 1 FROM pg_proc p "
            "  JOIN pg_namespace n ON p.pronamespace = n.oid "
            "  WHERE n.nspname = :s AND p.proname = :f"
        )
        if nb_params is not None:
            query += " AND array_length(p.proargtypes, 1) = :np"
        query += ")"
        params = {"s": schema, "f": nom_fonction}
        if nb_params is not None:
            params["np"] = nb_params
        result = conn.execute(text(query), params).scalar()
        return result
    
    with engine.connect() as conn:
        manque_01 = False
        if not existe_table(conn, "dfi"):
            print(f"  ⚠ Table 'dfi' manquante")
            manque_01 = True

        if not existe_table(conn, "dfi_lien"):
            print("  ⚠ Table 'dfi_lien' manquante")
            manque_01 = True
        
        manque_02 = False
        for func_name, nb_p in [("dfi_preparer_liens", 0),
                                ("dfi_typer_statut", 0),
                                ("dfi_assembler_parcelles", 1)]:
            if not existe_fonction(conn, func_name, nb_p):
                print(f"  ⚠ Fonction '{func_name}' manquante")
                manque_02 = True
        
        manque_03 = False
        if not existe_fonction(conn, "dfi_html_filiation", 1):
            print(f"  ⚠ Fonction 'dfi_html_filiation' manquante")
            manque_03 = True
    
    # Si manquements, réinitialiser tout
    if manque_01 or manque_02 or manque_03:
        init_dfi_preparation(engine, cfg)
        init_dfi_fonctions(engine, cfg)
        init_dfi_filiation(engine, cfg)
    else:
        print(f"✓ Schéma {schema} déjà initialisé.")
    
    return True


def traiter_dfi(engine, cfg):
    """
    Lance les traitements SQL post-chargement :
      1. éclatement des listes de parcelles dans la table de liens
      2. typage des filiations (division, assemblage, renommage, ...)
      3. reconstruction des géométries des parcelles mères
    """
    schema = cfg["schema"]
    with engine.connect() as connection:
        print("Préparation de la table de liens...")
        connection.execute(text(f"SELECT {schema}.dfi_preparer_liens();"))
        print("Typage des filiations...")
        connection.execute(text(f"SELECT {schema}.dfi_typer_statut();"))
        print("Reconstruction des géométries mères...")
        connection.execute(text(f"SELECT {schema}.dfi_assembler_parcelles(false);"))
        connection.commit()
    print("Traitement DFI terminé.")


def main_dfi(engine, cfg, chemin_zip):
    """Chaîne complète DFI : extraction du zip local -> nettoyage -> chargement -> traitement."""
    if not os.path.exists(chemin_zip):
        messagebox.showerror(title="Erreur DFI",
                             message=f"Fichier zip introuvable :\n{chemin_zip}")
        return

    DOSSIER_TELECHARGEMENT.mkdir(exist_ok=True)

    # 1. Extraire de l'archive le fichier du département
    fichier_dep = extraire_fichier_departement(chemin_zip, cfg["dep_dfi"],
                                            str(DOSSIER_TELECHARGEMENT))
    if fichier_dep is None:
        messagebox.showerror("Erreur DFI",f"Aucun fichier 'dep{cfg['dep_dfi']}' trouvé dans l'archive.")
        return

    # 2. Décompresser si c'est un ZIP imbriqué
    fichier_txt = str(DOSSIER_TELECHARGEMENT / f"dfi{cfg['departement']}.txt")
    if fichier_dep.endswith(".zip"):
        print(f"  ZIP imbriqué détecté, extraction...")
        with zipfile.ZipFile(fichier_dep, "r") as z:
            z.extractall(path=DOSSIER_TELECHARGEMENT)
        # Chercher le fichier .txt extrait
        fichier_txt_trouve = None
        for f in DOSSIER_TELECHARGEMENT.glob("*.txt"):
            if "dep" in f.name.lower():
                fichier_txt_trouve = str(f)
                break
        if not fichier_txt_trouve:
            messagebox.showerror("Erreur DFI", "Fichier .txt non trouvé après décompression du ZIP imbriqué.")
            return
        fichier_txt = fichier_txt_trouve
    elif fichier_dep.endswith(".gz"):
        with gzip.open(fichier_dep, "rb") as f_in, open(fichier_txt, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)
    else:
        shutil.copyfile(fichier_dep, fichier_txt)

    # 3 . Vérification du format du fichier DFI
    ok, message, nb_detecte = valider_format_dfi(fichier_txt)
    print(message)

    if not ok:
        result = messagebox.askyesno(
            "⚠️ Format DFI inattendu",
            message + "\n\nVoulez-vous continuer quand même ?\n"
                     "(Risque : 0 ligne chargée ou données incorrectes)"
        )
        if not result:
            return
        
    # 4. Nettoyage du fichier (regroupement des parcelles en 10ème colonne)
    fichier_clean = str(DOSSIER_TELECHARGEMENT / f"dfi{cfg['departement']}_clean.txt")
    nettoyer_fichier_dfi(fichier_txt, fichier_clean)

    # 5. Chargement en base (ON CONFLICT DO NOTHING)
    try:
        charger_dfi(engine, cfg, fichier_clean)
    except Exception as e:
        messagebox.showerror(title="Erreur DFI",
                             message=f"Erreur lors du chargement en base :\n{e}")
        return

    # 6. Traitements SQL (liens, statuts, géométries)
    try:
        traiter_dfi(engine, cfg)
    except Exception as e:
        messagebox.showerror(title="Erreur DFI",
                             message=f"Erreur lors du traitement SQL :\n{e}")
        return

    messagebox.showinfo(title="Travail terminé",
                        message="Les DFI ont été chargés et traités "
                                "(filiations typées, géométries mères reconstruites).")


# -----------------------------------------------------------------------------
#                              LANCEMENT DU PROGRAMME PRINCIPAL
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    from ui_cadastromancy import *
