-- Schéma du Data Warehouse Health Retailers – version B (PostgreSQL)
-- Généré par build_schema.py. 4 dimensions, 3 tables de faits.
-- Chargement : \copy <table> FROM 'dataset/dwh/<table>.csv' WITH (FORMAT csv, HEADER true, NULL '')
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
    "Product_Id" INTEGER NOT NULL,
    "Libellé" TEXT,
    "Famille" TEXT,
    "Marque" TEXT,
    "QuantiteAlerte" NUMERIC(12,3),
    CONSTRAINT pk_dim_produit PRIMARY KEY ("Product_Id")
);

-- Dimension : 1 ligne = 1 client, y compris le client comptoir anonyme
CREATE TABLE dim_client (
    "Company_Id" INTEGER NOT NULL,
    "Nom" TEXT,
    "TypeClient" TEXT,
    "EstClientIdentifie" BOOLEAN,
    CONSTRAINT pk_dim_client PRIMARY KEY ("Company_Id")
);

-- Dimension : 1 ligne = 1 moyen de paiement
CREATE TABLE dim_paiement (
    "PaymentMode_Id" INTEGER NOT NULL,
    "PaymentModeName" TEXT,
    CONSTRAINT pk_dim_paiement PRIMARY KEY ("PaymentMode_Id")
);

-- Fait : 1 produit vendu dans 1 document à 1 date
CREATE TABLE fait_ventes (
    "Id" BIGINT NOT NULL,
    "Document_Id" BIGINT,
    "DateKey" INTEGER,
    "Product_Id" INTEGER,
    "Company_Id" INTEGER,
    "QuantiteVendue" NUMERIC(14,4),
    "Remise_HT" NUMERIC(14,4),
    "CA_HT" NUMERIC(14,4),
    "Cout_HT" NUMERIC(14,4),
    CONSTRAINT pk_fait_ventes PRIMARY KEY ("Id"),
    CONSTRAINT fk_fait_ventes_datekey FOREIGN KEY ("DateKey") REFERENCES dim_temps ("DateKey"),
    CONSTRAINT fk_fait_ventes_product_id FOREIGN KEY ("Product_Id") REFERENCES dim_produit ("Product_Id"),
    CONSTRAINT fk_fait_ventes_company_id FOREIGN KEY ("Company_Id") REFERENCES dim_client ("Company_Id")
);

-- Fait (snapshot) : 1 produit à la date de snapshot
CREATE TABLE fait_stock_actuel (
    "Product_Id" INTEGER NOT NULL,
    "DateKey" INTEGER,
    "Quantity" NUMERIC(14,3),
    CONSTRAINT pk_fait_stock_actuel PRIMARY KEY ("Product_Id"),
    CONSTRAINT fk_fait_stock_actuel_product_id FOREIGN KEY ("Product_Id") REFERENCES dim_produit ("Product_Id"),
    CONSTRAINT fk_fait_stock_actuel_datekey FOREIGN KEY ("DateKey") REFERENCES dim_temps ("DateKey")
);

-- Fait : 1 paiement
CREATE TABLE fait_paiements (
    "Id" BIGINT NOT NULL,
    "DateKey" INTEGER,
    "PaymentMode_Id" INTEGER,
    "Amount" NUMERIC(14,4),
    "EstPaiementFournisseur" BOOLEAN,
    CONSTRAINT pk_fait_paiements PRIMARY KEY ("Id"),
    CONSTRAINT fk_fait_paiements_datekey FOREIGN KEY ("DateKey") REFERENCES dim_temps ("DateKey"),
    CONSTRAINT fk_fait_paiements_paymentmode_id FOREIGN KEY ("PaymentMode_Id") REFERENCES dim_paiement ("PaymentMode_Id")
);

-- Chargement des données (psql)
\copy dim_temps FROM 'dataset/dwh/dim_temps.csv' WITH (FORMAT csv, HEADER true, NULL '')
\copy dim_produit FROM 'dataset/dwh/dim_produit.csv' WITH (FORMAT csv, HEADER true, NULL '')
\copy dim_client FROM 'dataset/dwh/dim_client.csv' WITH (FORMAT csv, HEADER true, NULL '')
\copy dim_paiement FROM 'dataset/dwh/dim_paiement.csv' WITH (FORMAT csv, HEADER true, NULL '')
\copy fait_ventes FROM 'dataset/dwh/fait_ventes.csv' WITH (FORMAT csv, HEADER true, NULL '')
\copy fait_stock_actuel FROM 'dataset/dwh/fait_stock_actuel.csv' WITH (FORMAT csv, HEADER true, NULL '')
\copy fait_paiements FROM 'dataset/dwh/fait_paiements.csv' WITH (FORMAT csv, HEADER true, NULL '')
