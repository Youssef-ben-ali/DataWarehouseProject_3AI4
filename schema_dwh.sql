-- Schéma du Data Warehouse Health Retailers – version B (PostgreSQL)
-- Généré par build_schema.py. 5 dimensions, 5 tables de faits.
-- Le schéma est le modèle cible : les CSV de dataset-dwh portent encore les identifiants du logiciel, les SK seront attribuées au chargement.
-- Ordre : dimensions puis faits (même ordre que ci-dessous).

-- Dimension : 1 ligne = 1 date
CREATE TABLE dim_temps (
    "DateKey" INTEGER NOT NULL,
    "Date" DATE,
    "Annee" SMALLINT,
    "Trimestre" SMALLINT,
    "Mois" SMALLINT,
    "SemaineISO" SMALLINT,
    "EstFerie" BOOLEAN,
    CONSTRAINT pk_dim_temps PRIMARY KEY ("DateKey")
);

-- Dimension : 1 ligne = 1 produit
CREATE TABLE dim_produit (
    "Produit_SK" INTEGER NOT NULL,
    "Product_Id" INTEGER,
    "Libellé" TEXT,
    "Famille" TEXT,
    "Marque" TEXT,
    CONSTRAINT pk_dim_produit PRIMARY KEY ("Produit_SK"),
    CONSTRAINT uq_dim_produit_product_id UNIQUE ("Product_Id")
);

-- Dimension : 1 ligne = 1 client, y compris le client comptoir anonyme
CREATE TABLE dim_client (
    "Client_SK" INTEGER NOT NULL,
    "Company_Id" INTEGER,
    "Nom" TEXT,
    "TypeClient" TEXT,
    "EstClientIdentifie" BOOLEAN,
    CONSTRAINT pk_dim_client PRIMARY KEY ("Client_SK"),
    CONSTRAINT uq_dim_client_company_id UNIQUE ("Company_Id")
);

-- Dimension : 1 ligne = 1 fournisseur
CREATE TABLE dim_fournisseur (
    "Fournisseur_SK" INTEGER NOT NULL,
    "Fournisseur_Id" INTEGER,
    "Nom" TEXT,
    CONSTRAINT pk_dim_fournisseur PRIMARY KEY ("Fournisseur_SK"),
    CONSTRAINT uq_dim_fournisseur_fournisseur_id UNIQUE ("Fournisseur_Id")
);

-- Dimension : 1 ligne = 1 moyen de paiement
CREATE TABLE dim_paiement (
    "Paiement_SK" INTEGER NOT NULL,
    "PaymentMode_Id" INTEGER,
    "PaymentModeName" TEXT,
    CONSTRAINT pk_dim_paiement PRIMARY KEY ("Paiement_SK"),
    CONSTRAINT uq_dim_paiement_paymentmode_id UNIQUE ("PaymentMode_Id")
);

-- Fait : 1 produit vendu dans 1 document à 1 date
CREATE TABLE fait_ventes (
    "Id" BIGINT NOT NULL,
    "Document_Id" BIGINT,
    "DateKey" INTEGER,
    "Produit_SK" INTEGER,
    "Client_SK" INTEGER,
    "QuantiteVendue" NUMERIC(14,4),
    "Remise_HT" NUMERIC(14,4),
    "CA_HT" NUMERIC(14,4),
    "Cout_HT" NUMERIC(14,4),
    CONSTRAINT pk_fait_ventes PRIMARY KEY ("Id"),
    CONSTRAINT fk_fait_ventes_datekey FOREIGN KEY ("DateKey") REFERENCES dim_temps ("DateKey"),
    CONSTRAINT fk_fait_ventes_produit_sk FOREIGN KEY ("Produit_SK") REFERENCES dim_produit ("Produit_SK"),
    CONSTRAINT fk_fait_ventes_client_sk FOREIGN KEY ("Client_SK") REFERENCES dim_client ("Client_SK")
);

-- Fait : 1 encaissement imputé à 1 vente réglée
CREATE TABLE fait_encaissements (
    "Id" BIGINT NOT NULL,
    "Payment_Id" BIGINT,
    "Document_Id" BIGINT,
    "DateKey" INTEGER,
    "Paiement_SK" INTEGER,
    "Client_SK" INTEGER,
    "Amount" NUMERIC(14,4),
    CONSTRAINT pk_fait_encaissements PRIMARY KEY ("Id"),
    CONSTRAINT fk_fait_encaissements_datekey FOREIGN KEY ("DateKey") REFERENCES dim_temps ("DateKey"),
    CONSTRAINT fk_fait_encaissements_paiement_sk FOREIGN KEY ("Paiement_SK") REFERENCES dim_paiement ("Paiement_SK"),
    CONSTRAINT fk_fait_encaissements_client_sk FOREIGN KEY ("Client_SK") REFERENCES dim_client ("Client_SK")
);

-- Fait : 1 produit acheté dans 1 facture fournisseur à 1 date
CREATE TABLE fait_achats (
    "Id" BIGINT NOT NULL,
    "Document_Id" BIGINT,
    "DateKey" INTEGER,
    "Produit_SK" INTEGER,
    "Fournisseur_SK" INTEGER,
    "QuantiteAchetee" NUMERIC(14,4),
    "MontantAchat_HT" NUMERIC(14,4),
    CONSTRAINT pk_fait_achats PRIMARY KEY ("Id"),
    CONSTRAINT fk_fait_achats_datekey FOREIGN KEY ("DateKey") REFERENCES dim_temps ("DateKey"),
    CONSTRAINT fk_fait_achats_produit_sk FOREIGN KEY ("Produit_SK") REFERENCES dim_produit ("Produit_SK"),
    CONSTRAINT fk_fait_achats_fournisseur_sk FOREIGN KEY ("Fournisseur_SK") REFERENCES dim_fournisseur ("Fournisseur_SK")
);

-- Fait : 1 décaissement imputé à 1 facture fournisseur réglée
CREATE TABLE fait_decaissements (
    "Id" BIGINT NOT NULL,
    "Payment_Id" BIGINT,
    "Document_Id" BIGINT,
    "DateKey" INTEGER,
    "Paiement_SK" INTEGER,
    "Fournisseur_SK" INTEGER,
    "Amount" NUMERIC(14,4),
    CONSTRAINT pk_fait_decaissements PRIMARY KEY ("Id"),
    CONSTRAINT fk_fait_decaissements_datekey FOREIGN KEY ("DateKey") REFERENCES dim_temps ("DateKey"),
    CONSTRAINT fk_fait_decaissements_paiement_sk FOREIGN KEY ("Paiement_SK") REFERENCES dim_paiement ("Paiement_SK"),
    CONSTRAINT fk_fait_decaissements_fournisseur_sk FOREIGN KEY ("Fournisseur_SK") REFERENCES dim_fournisseur ("Fournisseur_SK")
);

-- Fait (snapshot) : 1 produit à la date de snapshot
CREATE TABLE fait_stock_actuel (
    "Produit_SK" INTEGER NOT NULL,
    "DateKey" INTEGER,
    "Quantity" NUMERIC(14,3),
    "QuantiteAlerte" NUMERIC(12,3),
    CONSTRAINT pk_fait_stock_actuel PRIMARY KEY ("Produit_SK"),
    CONSTRAINT fk_fait_stock_actuel_produit_sk FOREIGN KEY ("Produit_SK") REFERENCES dim_produit ("Produit_SK"),
    CONSTRAINT fk_fait_stock_actuel_datekey FOREIGN KEY ("DateKey") REFERENCES dim_temps ("DateKey")
);

