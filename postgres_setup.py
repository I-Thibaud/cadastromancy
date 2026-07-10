# process_installation.py
# Module centralisé : initialisation du schéma de base + DFI
# Remplace : installation.sql, 01_preparation_dfi.sql, 02_fonctions_traitement_dfi.sql, 03_filiation_html.sql

from sqlalchemy import text


def init_base(engine, cfg):
    """
    Crée le schéma de base, les tables de référence et les vues matérialisées.
    Équivalent de installation.sql.
    
    Créé :
    - Schéma
    - Tables : date_maj, parcelles, batiments
    - Vues : mvw_parcelles, mvw_batiments
    """
    schema = cfg["schema"]
    
    sql = f"""
    -- Création du schéma
    CREATE SCHEMA IF NOT EXISTS {schema};
    
    COMMENT ON SCHEMA {schema}
        IS 'Cadastre non nominatif : parcelles, bâtiments, filiations (DFI)';
    
    -- Séquence pour date_maj
    CREATE SEQUENCE IF NOT EXISTS {schema}.date_maj_id_seq
        INCREMENT 1 START 1 MINVALUE 1 MAXVALUE 2147483647 CACHE 1;
    
    -- Table date_maj : suivi des mises à jour et charge une date bidon à 1900-01-01
    CREATE TABLE IF NOT EXISTS {schema}.date_maj
    (
        id integer NOT NULL DEFAULT nextval('{schema}.date_maj_id_seq'::regclass),
        last_date_maj date
    );

    INSERT INTO {schema}.date_maj (last_date_maj) VALUES ('1900-01-01');
    
    -- Séquence pour parcelles
    CREATE SEQUENCE IF NOT EXISTS {schema}.parcelles_id_auto_seq
        INCREMENT 1 START 1 MINVALUE 1 MAXVALUE 2147483647 CACHE 1;
    
    -- Table parcelles : données du cadastre Etalab
    CREATE TABLE IF NOT EXISTS {schema}.parcelles
    (
        id text,
        commune text,
        prefixe text,
        section text,
        numero text,
        contenance double precision,
        arpente boolean,
        created text,
        updated text,
        geometry geometry(Geometry, 2154),
        id_auto integer NOT NULL DEFAULT nextval('{schema}.parcelles_id_auto_seq'::regclass)
    );
    
    -- Séquence pour batiments
    CREATE SEQUENCE IF NOT EXISTS {schema}.batiments_id_seq
        INCREMENT 1 START 1 MINVALUE 1 MAXVALUE 2147483647 CACHE 1;
    
    -- Table batiments : données du cadastre Etalab
    CREATE TABLE IF NOT EXISTS {schema}.batiments
    (
        type text,
        nom text,
        commune text,
        created text,
        updated text,
        geometry geometry(MultiPolygon, 2154),
        id integer NOT NULL DEFAULT nextval('{schema}.batiments_id_seq'::regclass)
    );
    
    -- Vue matérialisée : parcelles
    CREATE MATERIALIZED VIEW IF NOT EXISTS {schema}.mvw_parcelles AS
    SELECT
        parcelles.id,
        parcelles.commune,
        parcelles.prefixe,
        parcelles.section,
        parcelles.numero,
        parcelles.contenance,
        parcelles.arpente,
        parcelles.created,
        parcelles.updated,
        parcelles.geometry,
        parcelles.id_auto
    FROM {schema}.parcelles;
    
    -- Vue matérialisée : bâtiments
    CREATE MATERIALIZED VIEW IF NOT EXISTS {schema}.mvw_batiments AS
    SELECT
        row_number() OVER () AS id_auto,
        batiments.type,
        batiments.nom,
        batiments.commune,
        batiments.created,
        batiments.updated,
        batiments.geometry,
        batiments.id
    FROM {schema}.batiments;
    """
    
    with engine.connect() as conn:
        for statement in sql.split(";"):
            stmt = statement.strip()
            if stmt:
                conn.execute(text(stmt))
        conn.commit()
    
    print(f"✓ Schéma de base {schema} initialisé (tables + vues).")


def init_dfi_preparation(engine, cfg):
    """
    Prépare le modèle DFI : colonnes, table de liens, contrainte d'unicité, index.
    Équivalent de 01_preparation_dfi.sql.
    
    Créé :
    - Colonnes dfi : geom, lst_parcelle, statut_dfi
    - Table dfi_lien : éclatement des listes de parcelles
    - Contrainte unique sur dfi
    - Index de performance
    """
    schema = cfg["schema"]
    
    sql = f"""
    -- Ajouter les colonnes de résultat à la table dfi
        --table dfi :
    CREATE TABLE IF NOT EXISTS {schema}.dfi
    (
        dep text COLLATE pg_catalog."default",
        code_commune text COLLATE pg_catalog."default",
        prefixe_section text COLLATE pg_catalog."default",
        id_dfi text COLLATE pg_catalog."default",
        nature_dfi text COLLATE pg_catalog."default",
        date_valide_dfi text COLLATE pg_catalog."default",
        n_lot_dfi text COLLATE pg_catalog."default",
        type text COLLATE pg_catalog."default",
        parcelles text COLLATE pg_catalog."default",
        geom geometry(MultiPolygon,2154),
        lst_parcelle text COLLATE pg_catalog."default",
        statut_dfi text COLLATE pg_catalog."default",
        geometrie_partielle boolean DEFAULT false,
        CONSTRAINT dfi_unique UNIQUE (dep, code_commune, prefixe_section, id_dfi, n_lot_dfi, type)
    );
    
   
    -- Table de liens : éclate les listes de parcelles
    CREATE TABLE IF NOT EXISTS {schema}.dfi_lien (
        dep             text NOT NULL,
        code_commune    text NOT NULL,
        prefixe_section text NOT NULL,
        id_dfi          text NOT NULL,
        n_lot_dfi       text NOT NULL,
        type            text NOT NULL,
        parcelle        text NOT NULL,
        date_valide_dfi text,
        CONSTRAINT dfi_lien_pk PRIMARY KEY
            (dep, code_commune, prefixe_section, id_dfi, n_lot_dfi, type, parcelle)
    );
    
    -- Index pour recherche inverse : "dans quels lots cette parcelle apparaît-elle ?"
    CREATE INDEX IF NOT EXISTS idx_dfi_lien_parcelle
        ON {schema}.dfi_lien (dep, code_commune, prefixe_section, parcelle, type);
    
    -- Index partiel : lots mères sans géométrie
    CREATE INDEX IF NOT EXISTS idx_dfi_meres_sans_geom
        ON {schema}.dfi (dep, code_commune, prefixe_section, id_dfi, n_lot_dfi)
        WHERE type = '1' AND geom IS NULL;
    
    -- Index sur parcelles.id (recherche par identifiant)
    CREATE INDEX IF NOT EXISTS idx_parcelles_id ON {schema}.parcelles (id);
    
    ANALYZE {schema}.dfi;
    """
    
    with engine.connect() as conn:
        for statement in sql.split(";"):
            stmt = statement.strip()
            if stmt:
                conn.execute(text(stmt))
        conn.commit()
    
    print(f"✓ Préparation DFI : colonnes, table de liens, contraintes, index.")


def init_dfi_fonctions(engine, cfg):
    """
    Crée les trois fonctions de traitement DFI.
    Équivalent de 02_fonctions_traitement_dfi.sql.
    
    Fonctions :
    - dfi_preparer_liens() : éclate les listes
    - dfi_typer_statut() : type les filiations
    - dfi_assembler_parcelles() : reconstruit les géométries
    """
    schema = cfg["schema"]
    
    # Fonction 1 : Éclatement des liens
    sql_func_liens = f"""
    CREATE OR REPLACE FUNCTION {schema}.dfi_preparer_liens()
        RETURNS integer
        LANGUAGE plpgsql
        VOLATILE
    AS $BODY$
    DECLARE
        nb integer;
    BEGIN
        TRUNCATE {schema}.dfi_lien;

        INSERT INTO {schema}.dfi_lien
            (dep, code_commune, prefixe_section, id_dfi, n_lot_dfi, type,
             parcelle, date_valide_dfi)
        SELECT DISTINCT
            d.dep, d.code_commune, d.prefixe_section, d.id_dfi, d.n_lot_dfi, d.type,
            lpad(trim(p.parcelle), 6, '0'),
            d.date_valide_dfi
        FROM {schema}.dfi d
        CROSS JOIN LATERAL unnest(string_to_array(d.parcelles, ',')) AS p(parcelle)
        WHERE d.parcelles IS NOT NULL
          AND trim(p.parcelle) <> '';

        GET DIAGNOSTICS nb = ROW_COUNT;
        ANALYZE {schema}.dfi_lien;
        RAISE NOTICE 'dfi_lien : % liens créés', nb;
        RETURN nb;
    END;
    $BODY$;
    """
    
    # Fonction 2 : Typage des filiations
    sql_func_statut = f"""
    CREATE OR REPLACE FUNCTION {schema}.dfi_typer_statut()
        RETURNS integer
        LANGUAGE plpgsql
        VOLATILE
    AS $BODY$
    DECLARE
        nb integer;
    BEGIN
        WITH comptage AS (
            SELECT
                d1.dep, d1.code_commune, d1.prefixe_section, d1.id_dfi, d1.n_lot_dfi,
                COALESCE(array_length(string_to_array(NULLIF(d1.parcelles, ''), ','), 1), 0) AS nb_meres,
                COALESCE(array_length(string_to_array(NULLIF(d2.parcelles, ''), ','), 1), 0) AS nb_filles,
                d2.parcelles AS filles
            FROM {schema}.dfi d1
            LEFT JOIN {schema}.dfi d2
                   ON  d2.dep = d1.dep
                   AND d2.code_commune = d1.code_commune
                   AND d2.prefixe_section = d1.prefixe_section
                   AND d2.id_dfi = d1.id_dfi
                   AND d2.n_lot_dfi = d1.n_lot_dfi
                   AND d2.type = '2'
            WHERE d1.type = '1'
        )
        UPDATE {schema}.dfi d
        SET statut_dfi = CASE
                WHEN c.nb_meres = 0 AND c.nb_filles = 0 THEN 'NR'
                WHEN c.nb_meres = 0 AND c.nb_filles > 0 THEN 'Extraction domaine non cadastré'
                WHEN c.nb_meres > 0 AND c.nb_filles = 0 THEN 'Passage domaine public'
                WHEN c.nb_meres = 1 AND c.nb_filles = 1 THEN 'Renommage'
                WHEN c.nb_meres > 1 AND c.nb_filles = 1 THEN 'Assemblage'
                WHEN c.nb_meres = 1 AND c.nb_filles > 1 THEN 'Division'
                ELSE 'Assemblage/Division'
            END,
            lst_parcelle = c.filles
        FROM comptage c
        WHERE d.type = '1'
          AND d.dep = c.dep
          AND d.code_commune = c.code_commune
          AND d.prefixe_section = c.prefixe_section
          AND d.id_dfi = c.id_dfi
          AND d.n_lot_dfi = c.n_lot_dfi;

        GET DIAGNOSTICS nb = ROW_COUNT;
        RAISE NOTICE 'Typage : % lots mis à jour', nb;
        RETURN nb;
    END;
    $BODY$;
    """
    
    # Fonction 3 : Assemblage des géométries (très longue, besoin d'échapper les guillemets)
    sql_func_assembler = f"""
    CREATE OR REPLACE FUNCTION {schema}.dfi_assembler_parcelles(
            reinitialiser boolean DEFAULT false)
        RETURNS integer
        LANGUAGE plpgsql
        VOLATILE
    AS $BODY$
    DECLARE
        nb        integer;
        nb_partiel integer;
        total     integer := 0;
        passe     integer := 0;
    BEGIN
        IF reinitialiser THEN
            UPDATE {schema}.dfi
            SET geom = NULL
            WHERE type = '1' AND geom IS NOT NULL;
        END IF;

        LOOP
            -- ================= PHASE 1 : passes strictes =================
            LOOP
                passe := passe + 1;

                WITH a_traiter AS (
                    SELECT d.dep, d.code_commune, d.prefixe_section,
                           d.id_dfi, d.n_lot_dfi,
                           COALESCE(d.date_valide_dfi, '') AS date_dfi
                    FROM {schema}.dfi d
                    WHERE d.type = '1'
                      AND d.geom IS NULL
                      AND EXISTS (SELECT 1
                                  FROM {schema}.dfi_lien l
                                  WHERE l.dep = d.dep
                                    AND l.code_commune = d.code_commune
                                    AND l.prefixe_section = d.prefixe_section
                                    AND l.id_dfi = d.id_dfi
                                    AND l.n_lot_dfi = d.n_lot_dfi
                                    AND l.type = '2')
                ),
                resolution AS (
                    SELECT t.dep, t.code_commune, t.prefixe_section,
                           t.id_dfi, t.n_lot_dfi,
                           CASE WHEN lot_post.id_dfi IS NOT NULL
                                THEN lot_post.geom
                                ELSE p.geometry
                           END AS g
                    FROM a_traiter t
                    JOIN {schema}.dfi_lien l
                      ON  l.dep = t.dep
                      AND l.code_commune = t.code_commune
                      AND l.prefixe_section = t.prefixe_section
                      AND l.id_dfi = t.id_dfi
                      AND l.n_lot_dfi = t.n_lot_dfi
                      AND l.type = '2'
                    LEFT JOIN LATERAL (
                            SELECT d2.id_dfi, d2.geom
                            FROM {schema}.dfi_lien lm
                            JOIN {schema}.dfi d2
                              ON  d2.dep = lm.dep
                              AND d2.code_commune = lm.code_commune
                              AND d2.prefixe_section = lm.prefixe_section
                              AND d2.id_dfi = lm.id_dfi
                              AND d2.n_lot_dfi = lm.n_lot_dfi
                              AND d2.type = '1'
                            WHERE lm.dep = t.dep
                              AND lm.code_commune = t.code_commune
                              AND lm.prefixe_section = t.prefixe_section
                              AND lm.parcelle = l.parcelle
                              AND lm.type = '1'
                              AND COALESCE(lm.date_valide_dfi, '') >= t.date_dfi
                              AND NOT (lm.id_dfi = t.id_dfi AND lm.n_lot_dfi = t.n_lot_dfi)
                            ORDER BY lm.date_valide_dfi, lm.id_dfi
                            LIMIT 1
                    ) lot_post ON true
                    LEFT JOIN {schema}.parcelles p
                           ON p.id = left(t.dep, 2) || t.code_commune
                                   || t.prefixe_section || l.parcelle
                ),
                agg AS (
                    SELECT dep, code_commune, prefixe_section, id_dfi, n_lot_dfi,
                           ST_Multi(ST_CollectionExtract(
                               ST_UnaryUnion(ST_Collect(ST_MakeValid(g))), 3)) AS geom
                    FROM resolution
                    GROUP BY dep, code_commune, prefixe_section, id_dfi, n_lot_dfi
                    HAVING bool_and(g IS NOT NULL)
                )
                UPDATE {schema}.dfi d
                SET geom = agg.geom
                FROM agg
                WHERE d.type = '1'
                  AND d.dep = agg.dep
                  AND d.code_commune = agg.code_commune
                  AND d.prefixe_section = agg.prefixe_section
                  AND d.id_dfi = agg.id_dfi
                  AND d.n_lot_dfi = agg.n_lot_dfi;

                GET DIAGNOSTICS nb = ROW_COUNT;
                total := total + nb;
                RAISE NOTICE 'Passe % : % lots résolus', passe, nb;

                EXIT WHEN nb = 0 OR passe > 100;
            END LOOP;

            -- ================= PHASE 2 : géométries partielles =================
            WITH a_traiter AS (
                SELECT d.dep, d.code_commune, d.prefixe_section,
                       d.id_dfi, d.n_lot_dfi,
                       COALESCE(d.date_valide_dfi, '') AS date_dfi
                FROM {schema}.dfi d
                WHERE d.type = '1'
                  AND d.geom IS NULL
                  AND EXISTS (SELECT 1
                              FROM {schema}.dfi_lien l
                              WHERE l.dep = d.dep
                                AND l.code_commune = d.code_commune
                                AND l.prefixe_section = d.prefixe_section
                                AND l.id_dfi = d.id_dfi
                                AND l.n_lot_dfi = d.n_lot_dfi
                                AND l.type = '2')
            ),
            resolution AS (
                SELECT t.dep, t.code_commune, t.prefixe_section,
                       t.id_dfi, t.n_lot_dfi,
                       CASE WHEN lot_post.id_dfi IS NOT NULL
                            THEN lot_post.geom
                            ELSE p.geometry
                       END AS g
                FROM a_traiter t
                JOIN {schema}.dfi_lien l
                  ON  l.dep = t.dep
                  AND l.code_commune = t.code_commune
                  AND l.prefixe_section = t.prefixe_section
                  AND l.id_dfi = t.id_dfi
                  AND l.n_lot_dfi = t.n_lot_dfi
                  AND l.type = '2'
                LEFT JOIN LATERAL (
                        SELECT d2.id_dfi, d2.geom
                        FROM {schema}.dfi_lien lm
                        JOIN {schema}.dfi d2
                          ON  d2.dep = lm.dep
                          AND d2.code_commune = lm.code_commune
                          AND d2.prefixe_section = lm.prefixe_section
                          AND d2.id_dfi = lm.id_dfi
                          AND d2.n_lot_dfi = lm.n_lot_dfi
                          AND d2.type = '1'
                        WHERE lm.dep = t.dep
                          AND lm.code_commune = t.code_commune
                          AND lm.prefixe_section = t.prefixe_section
                          AND lm.parcelle = l.parcelle
                          AND lm.type = '1'
                          AND COALESCE(lm.date_valide_dfi, '') >= t.date_dfi
                          AND NOT (lm.id_dfi = t.id_dfi AND lm.n_lot_dfi = t.n_lot_dfi)
                        ORDER BY lm.date_valide_dfi, lm.id_dfi
                        LIMIT 1
                ) lot_post ON true
                LEFT JOIN {schema}.parcelles p
                       ON p.id = left(t.dep, 2) || t.code_commune
                               || t.prefixe_section || l.parcelle
            ),
            agg AS (
                SELECT dep, code_commune, prefixe_section, id_dfi, n_lot_dfi,
                       ST_Multi(ST_CollectionExtract(
                           ST_UnaryUnion(ST_Collect(ST_MakeValid(g))), 3)) AS geom
                FROM resolution
                WHERE g IS NOT NULL
                GROUP BY dep, code_commune, prefixe_section, id_dfi, n_lot_dfi
            )
            UPDATE {schema}.dfi d
            SET geom = agg.geom,
                geometrie_partielle = true
            FROM agg
            WHERE d.type = '1'
            AND d.geom IS NULL
            AND d.dep = agg.dep
            AND d.code_commune = agg.code_commune
            AND d.prefixe_section = agg.prefixe_section
            AND d.id_dfi = agg.id_dfi
            AND d.n_lot_dfi = agg.n_lot_dfi;

            GET DIAGNOSTICS nb_partiel = ROW_COUNT;
            total := total + nb_partiel;
            RAISE NOTICE 'Passe partielle : % lots résolus partiellement', nb_partiel;

            EXIT WHEN nb_partiel = 0;
        END LOOP;

        RAISE NOTICE 'Assemblage terminé : % lots au total', total;
        RETURN total;
    END;
    $BODY$;
    """
    
    with engine.connect() as conn:
        conn.execute(text(sql_func_liens))
        conn.commit()
        conn.execute(text(sql_func_statut))
        conn.commit()
        conn.execute(text(sql_func_assembler))
        conn.commit()
    
    print(f"✓ 3 fonctions de traitement créées (liens, typage, assemblage).")


def init_dfi_filiation(engine, cfg):
    """
    Crée la fonction de génération de frise HTML et les vues associées.
    Équivalent de 03_filiation_html.sql.
    
    Crée :
    - dfi_html_filiation() : génère la frise chronologique
    - vw_parcelles_filiation : vue avec colonne filiation
    """
    schema = cfg["schema"]
    
    sql_func_filiation = f"""
    CREATE OR REPLACE FUNCTION {schema}.dfi_html_filiation(p_id_parcelle text)
        RETURNS text
        LANGUAGE plpgsql
        STABLE
    AS $BODY$
    DECLARE
        v_dep      text := left(p_id_parcelle, 2) || '0';
        v_commune  text := substr(p_id_parcelle, 3, 3);
        v_prefixe  text := substr(p_id_parcelle, 6, 3);
        v_token    text := substr(p_id_parcelle, 9, 6);
        v_html     text;
        v_libelle  text;
        rec        record;
        nb_evt     integer := 0;
    BEGIN
        IF NOT EXISTS (SELECT 1
                       FROM {schema}.dfi_lien l
                       WHERE l.dep = v_dep
                         AND l.code_commune = v_commune
                         AND l.prefixe_section = v_prefixe
                         AND l.parcelle = v_token
                         AND l.type = '2') THEN
            RETURN NULL;
        END IF;

        v_libelle := ltrim(substr(v_token, 1, 2), '0') || ' ' || ltrim(substr(v_token, 3, 4), '0');

        v_html :=
            '<div style="font-family:Segoe UI,Arial,sans-serif;font-size:12px;'
            || 'color:#2b2b2b;max-width:430px;">'
            || '<div style="font-size:14px;font-weight:bold;margin-bottom:8px;">'
            || 'Filiation de la parcelle ' || v_libelle || '</div>'
            || '<div style="border-left:3px solid #1f6f8b;margin-left:6px;padding-left:14px;">';

        FOR rec IN
            WITH RECURSIVE hist AS (
                SELECT l.id_dfi, l.n_lot_dfi, 1 AS niveau
                FROM {schema}.dfi_lien l
                WHERE l.dep = v_dep
                  AND l.code_commune = v_commune
                  AND l.prefixe_section = v_prefixe
                  AND l.parcelle = v_token
                  AND l.type = '2'
                UNION
                SELECT l2.id_dfi, l2.n_lot_dfi, h.niveau + 1
                FROM hist h
                JOIN {schema}.dfi_lien lm
                  ON  lm.dep = v_dep
                  AND lm.code_commune = v_commune
                  AND lm.prefixe_section = v_prefixe
                  AND lm.id_dfi = h.id_dfi
                  AND lm.n_lot_dfi = h.n_lot_dfi
                  AND lm.type = '1'
                JOIN {schema}.dfi_lien l2
                  ON  l2.dep = v_dep
                  AND l2.code_commune = v_commune
                  AND l2.prefixe_section = v_prefixe
                  AND l2.parcelle = lm.parcelle
                  AND l2.type = '2'
                  AND COALESCE(l2.date_valide_dfi, '') <= COALESCE(lm.date_valide_dfi, '99999999')
                WHERE h.niveau < 15
            )
            SELECT DISTINCT
                   d1.id_dfi,
                   d1.n_lot_dfi,
                   d1.date_valide_dfi,
                   d1.nature_dfi,
                   COALESCE(d1.statut_dfi, 'NR')  AS statut_dfi,
                   NULLIF(d1.parcelles, '')       AS meres,
                   NULLIF(d1.lst_parcelle, '')    AS filles
            FROM hist h
            JOIN {schema}.dfi d1
              ON  d1.dep = v_dep
              AND d1.code_commune = v_commune
              AND d1.prefixe_section = v_prefixe
              AND d1.id_dfi = h.id_dfi
              AND d1.n_lot_dfi = h.n_lot_dfi
              AND d1.type = '1'
            ORDER BY d1.date_valide_dfi DESC, d1.id_dfi DESC
        LOOP
            nb_evt := nb_evt + 1;

            v_html := v_html
                || '<div style="margin-bottom:13px;">'
                || '<span style="display:inline-block;width:9px;height:9px;'
                || 'background:#e94f37;border:2px solid #ffffff;border-radius:50%;'
                || 'margin-left:-21px;margin-right:8px;"></span>'
                || '<b>'
                || COALESCE(to_char(to_date(rec.date_valide_dfi, 'YYYYMMDD'), 'DD/MM/YYYY'),
                            'date inconnue')
                || '</b> &#183; '
                || CASE rec.nature_dfi
                       WHEN '1' THEN 'Document d''arpentage'
                       WHEN '2' THEN 'Croquis de conservation'
                       WHEN '4' THEN 'Remaniement'
                       WHEN '5' THEN 'Document d''arpentage numérique'
                       WHEN '6' THEN 'Lotissement numérique'
                       WHEN '7' THEN 'Lotissement'
                       WHEN '8' THEN 'Rénovation'
                       ELSE 'Nature inconnue'
                   END
                || ' <span style="color:#888;">(DFI ' || rec.id_dfi
                || ' / lot ' || rec.n_lot_dfi || ')</span><br>'
                || '<span style="color:#1f6f8b;font-weight:bold;">'
                || rec.statut_dfi || '</span><br>'
                || '<span style="color:#444;">'
                || COALESCE(replace(rec.meres, ',', ', '),
                            '<i>domaine non cadastré</i>')
                || ' &#8594; '
                || COALESCE(replace(rec.filles, ',', ', '),
                            '<i>domaine public</i>')
                || '</span>'
                || '</div>';
        END LOOP;

        v_html := v_html || '</div>'
            || '<div style="color:#888;font-size:10px;margin-top:4px;">'
            || nb_evt || ' évènement(s) de filiation &#183; source : DFI DGFiP</div>'
            || '</div>';

        RETURN v_html;
    END;
    $BODY$;
    """
    
    sql_vue = f"""
    CREATE OR REPLACE VIEW {schema}.vw_parcelles_filiation AS
    SELECT p.*,
           {schema}.dfi_html_filiation(p.id) AS filiation
    FROM {schema}.parcelles p;
    """
    
    with engine.connect() as conn:
        conn.execute(text(sql_func_filiation))
        conn.commit()
        conn.execute(text(sql_vue))
        conn.commit()
    
    print(f"✓ Fonction filiation HTML + vue créées.")


def init_all(engine, cfg):
    """
    Lance l'initialisation complète du schéma, dans l'ordre :
    1. Schéma de base (tables + vues)
    2. Préparation DFI (colonnes, table de liens, index)
    3. Fonctions de traitement DFI
    4. Fonction de filiation HTML
    """
    print(f"\n⚙️  Initialisation complète du schéma {cfg['schema']}...")
    
    try:
        init_base(engine, cfg)
        init_dfi_preparation(engine, cfg)
        init_dfi_fonctions(engine, cfg)
        init_dfi_filiation(engine, cfg)
        print(f"\n✅ Schéma {cfg['schema']} entièrement initialisé.")
        return True
    except Exception as e:
        print(f"\n❌ Erreur lors de l'initialisation : {e}")
        raise
