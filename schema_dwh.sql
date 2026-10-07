-- Schéma du Data Warehouse Health Retailers (PostgreSQL)
-- Généré par build_schema.py. Charger ensuite chaque CSV de dataset/dwh avec :
--   \copy <table> FROM 'dataset/dwh/<table>.csv' WITH (FORMAT csv, HEADER true, NULL '')
-- Ordre de chargement : dimensions puis faits (même ordre que ci-dessous).

-- Dimension : 1 ligne = 1 jour (01/09/2024 → 31/12/2025)
CREATE TABLE dim_temps (
    "DateKey" INTEGER NOT NULL,
    "Date" DATE,
    "Annee" INTEGER,
    "Trimestre" INTEGER,
    "Mois" INTEGER,
    "NomMois" VARCHAR(255),
    "AnneeMois" VARCHAR(255),
    "SemaineISO" INTEGER,
    "AnneeSemaine" VARCHAR(255),
    "DebutSemaine" DATE,
    "Jour" INTEGER,
    "JourSemaine" INTEGER,
    "NomJour" VARCHAR(255),
    "EstWeekend" BOOLEAN,
    "EstFerie" BOOLEAN,
    "NomFerie" VARCHAR(255),
    "VacancesZoneA" BOOLEAN,
    "VacancesZoneB" BOOLEAN,
    "VacancesZoneC" BOOLEAN,
    "EstVacances" BOOLEAN,
    "Saison" VARCHAR(255),
    "DansPeriodeDonnees" BOOLEAN,
    "Meteo_TempMoy" NUMERIC(18,4),
    "Meteo_TempMin" NUMERIC(18,4),
    "Meteo_TempMax" NUMERIC(18,4),
    "Meteo_Pluie_mm" NUMERIC(18,4),
    "Meteo_Ensoleillement_h" NUMERIC(18,4),
    "Meteo_Rayonnement_MJm2" NUMERIC(18,4),
    "Senti_Grippe_Inc100" NUMERIC(18,4),
    "Senti_IRA_Inc100" NUMERIC(18,4),
    "Senti_Gastro_Inc100" NUMERIC(18,4),
    "Senti_Varicelle_Inc100" NUMERIC(18,4),
    CONSTRAINT pk_dim_temps PRIMARY KEY ("DateKey")
);

-- Dimension : 1 ligne = 1 ville (-1 = non renseigné)
CREATE TABLE dim_geographie (
    "Geo_Id" INTEGER NOT NULL,
    "Ville" VARCHAR(255),
    "Departement" VARCHAR(255),
    "Region" VARCHAR(255),
    "Pays" VARCHAR(255),
    CONSTRAINT pk_dim_geographie PRIMARY KEY ("Geo_Id")
);

-- Dimension : 1 ligne = 1 moyen de paiement (-1 = non renseigné)
CREATE TABLE dim_paiement (
    "PaymentMode_Id" INTEGER NOT NULL,
    "PaymentModeName" VARCHAR(255),
    "EstEspeces" BOOLEAN,
    "EstDiffere" BOOLEAN,
    CONSTRAINT pk_dim_paiement PRIMARY KEY ("PaymentMode_Id")
);

-- Dimension : 1 ligne = 1 utilisateur (vendeur / caissier)
CREATE TABLE dim_utilisateur (
    "User_Id" INTEGER NOT NULL,
    "FullName" VARCHAR(255),
    "IsStaff" BOOLEAN,
    CONSTRAINT pk_dim_utilisateur PRIMARY KEY ("User_Id")
);

-- Dimension : 1 ligne = 1 produit du référentiel interne
CREATE TABLE dim_produit (
    "Product_Id" INTEGER NOT NULL,
    "ProductStock_Id" INTEGER,
    "Libellé" VARCHAR(255),
    "Code" VARCHAR(255),
    "CodeBarre" VARCHAR(255),
    "Famille" VARCHAR(255),
    "FamilyGroup" VARCHAR(255),
    "Marque" VARCHAR(255),
    "MarqueSource" VARCHAR(255),
    "Prix d'achat HT" NUMERIC(18,4),
    "Prix de vente HT" NUMERIC(18,4),
    "Tva" NUMERIC(18,4),
    "Prix de vente TTC" NUMERIC(18,4),
    "CoutMoyenPondere" NUMERIC(18,4),
    "Quantité d'Alerte" NUMERIC(18,4),
    "AlerteSource" VARCHAR(255),
    "IsDeletedInSoftware" BOOLEAN,
    "ProductIdSource" VARCHAR(255),
    CONSTRAINT pk_dim_produit PRIMARY KEY ("Product_Id")
);

-- Dimension : 1 ligne = 1 client (-1 = non renseigné, 2 = client comptoir anonyme)
CREATE TABLE dim_client (
    "Company_Id" INTEGER NOT NULL,
    "Code" VARCHAR(255),
    "Nom" VARCHAR(255),
    "TypeClient" VARCHAR(255),
    "Ville" VARCHAR(255),
    "Geo_Id" INTEGER,
    "Solde" NUMERIC(18,4),
    "EstClientIdentifie" BOOLEAN,
    "CompanyType" VARCHAR(255),
    CONSTRAINT pk_dim_client PRIMARY KEY ("Company_Id"),
    CONSTRAINT fk_dim_client_geo_id FOREIGN KEY ("Geo_Id") REFERENCES dim_geographie ("Geo_Id")
);

-- Dimension : 1 ligne = 1 fournisseur (-1 = non renseigné)
CREATE TABLE dim_fournisseur (
    "Company_Id" INTEGER NOT NULL,
    "Code" VARCHAR(255),
    "Nom" VARCHAR(255),
    "Ville" VARCHAR(255),
    "Geo_Id" INTEGER,
    "Solde" NUMERIC(18,4),
    CONSTRAINT pk_dim_fournisseur PRIMARY KEY ("Company_Id"),
    CONSTRAINT fk_dim_fournisseur_geo_id FOREIGN KEY ("Geo_Id") REFERENCES dim_geographie ("Geo_Id")
);

-- Dimension : 1 ligne = 1 document (-1 = aucun document)
CREATE TABLE dim_document (
    "Document_Id" INTEGER NOT NULL,
    "DocumentNumber" VARCHAR(255),
    "DateKey" INTEGER,
    "DocumentType_Id" INTEGER,
    "TypeDocument" VARCHAR(255),
    "Flow" VARCHAR(255),
    "Canal" VARCHAR(255),
    "State" INTEGER,
    "IsValidated" BOOLEAN,
    "EstFactureDeBL" BOOLEAN,
    "PaymentMode_Id" INTEGER,
    "CreatedBy" INTEGER,
    "Heure" INTEGER,
    "TotalNetHt" NUMERIC(18,4),
    "TotalTtc" NUMERIC(18,4),
    CONSTRAINT pk_dim_document PRIMARY KEY ("Document_Id"),
    CONSTRAINT fk_dim_document_datekey FOREIGN KEY ("DateKey") REFERENCES dim_temps ("DateKey"),
    CONSTRAINT fk_dim_document_paymentmode_id FOREIGN KEY ("PaymentMode_Id") REFERENCES dim_paiement ("PaymentMode_Id"),
    CONSTRAINT fk_dim_document_createdby FOREIGN KEY ("CreatedBy") REFERENCES dim_utilisateur ("User_Id")
);

-- Fait : 1 ligne = 1 produit vendu (ou retourné) dans 1 document validé à 1 date
CREATE TABLE fait_ventes (
    "Id" INTEGER NOT NULL,
    "Document_Id" INTEGER,
    "DocumentNumber" VARCHAR(255),
    "DateKey" INTEGER,
    "Date" DATE,
    "Heure" INTEGER,
    "Product_Id" INTEGER,
    "Company_Id" INTEGER,
    "PaymentMode_Id" INTEGER,
    "DocumentType_Id" INTEGER,
    "Canal" VARCHAR(255),
    "CreatedBy" INTEGER,
    "Signe" INTEGER,
    "Quantity" NUMERIC(18,4),
    "PrixHt" NUMERIC(18,4),
    "DiscountPourcentage" NUMERIC(18,4),
    "Tva" NUMERIC(18,4),
    "PrixTotalHt" NUMERIC(18,4),
    "TotalTva" NUMERIC(18,4),
    "PrixTotalTtc" NUMERIC(18,4),
    "QuantiteVendue" NUMERIC(18,4),
    "Remise_HT" NUMERIC(18,4),
    "CA_HT" NUMERIC(18,4),
    "TVA_Montant" NUMERIC(18,4),
    "CA_TTC" NUMERIC(18,4),
    "CoutUnitaire" NUMERIC(18,4),
    "SourceCout" VARCHAR(255),
    "Cout_HT" NUMERIC(18,4),
    "Marge_HT" NUMERIC(18,4),
    "VenteSousCout" BOOLEAN,
    CONSTRAINT pk_fait_ventes PRIMARY KEY ("Id"),
    CONSTRAINT fk_fait_ventes_document_id FOREIGN KEY ("Document_Id") REFERENCES dim_document ("Document_Id"),
    CONSTRAINT fk_fait_ventes_datekey FOREIGN KEY ("DateKey") REFERENCES dim_temps ("DateKey"),
    CONSTRAINT fk_fait_ventes_product_id FOREIGN KEY ("Product_Id") REFERENCES dim_produit ("Product_Id"),
    CONSTRAINT fk_fait_ventes_company_id FOREIGN KEY ("Company_Id") REFERENCES dim_client ("Company_Id"),
    CONSTRAINT fk_fait_ventes_paymentmode_id FOREIGN KEY ("PaymentMode_Id") REFERENCES dim_paiement ("PaymentMode_Id"),
    CONSTRAINT fk_fait_ventes_createdby FOREIGN KEY ("CreatedBy") REFERENCES dim_utilisateur ("User_Id")
);

-- Fait : 1 ligne = 1 produit acheté sur 1 document fournisseur validé
CREATE TABLE fait_achats (
    "Id" INTEGER NOT NULL,
    "Document_Id" INTEGER,
    "DocumentNumber" VARCHAR(255),
    "DateKey" INTEGER,
    "Date" DATE,
    "Product_Id" INTEGER,
    "Company_Id" INTEGER,
    "DocumentType_Id" INTEGER,
    "Signe" INTEGER,
    "Quantity" NUMERIC(18,4),
    "PrixHt" NUMERIC(18,4),
    "DiscountPourcentage" NUMERIC(18,4),
    "PrixTotalHt" NUMERIC(18,4),
    "QuantiteAchetee" NUMERIC(18,4),
    "MontantAchat_HT" NUMERIC(18,4),
    "MontantAchat_TTC" NUMERIC(18,4),
    "EstUniteGratuite" BOOLEAN,
    CONSTRAINT pk_fait_achats PRIMARY KEY ("Id"),
    CONSTRAINT fk_fait_achats_document_id FOREIGN KEY ("Document_Id") REFERENCES dim_document ("Document_Id"),
    CONSTRAINT fk_fait_achats_datekey FOREIGN KEY ("DateKey") REFERENCES dim_temps ("DateKey"),
    CONSTRAINT fk_fait_achats_product_id FOREIGN KEY ("Product_Id") REFERENCES dim_produit ("Product_Id"),
    CONSTRAINT fk_fait_achats_company_id FOREIGN KEY ("Company_Id") REFERENCES dim_fournisseur ("Company_Id")
);

-- Fait : 1 ligne = 1 paiement
CREATE TABLE fait_paiements (
    "Id" INTEGER NOT NULL,
    "DateKey" INTEGER,
    "Date" DATE,
    "Heure" INTEGER,
    "Company_Id" INTEGER,
    "Client_Id" INTEGER,
    "Fournisseur_Id" INTEGER,
    "PaymentMode_Id" INTEGER,
    "Amount" NUMERIC(18,4),
    "UsedAmount" NUMERIC(18,4),
    "IsPurchase" BOOLEAN,
    "EstPaiementFournisseur" BOOLEAN,
    "DocumentNumber" VARCHAR(255),
    "Document_Id" INTEGER,
    "CaisseId" VARCHAR(255),
    "CaisseName" VARCHAR(255),
    "BankAccountId" VARCHAR(255),
    "Extra_gA" NUMERIC(18,4),
    "Extra_rA" NUMERIC(18,4),
    CONSTRAINT pk_fait_paiements PRIMARY KEY ("Id"),
    CONSTRAINT fk_fait_paiements_datekey FOREIGN KEY ("DateKey") REFERENCES dim_temps ("DateKey"),
    CONSTRAINT fk_fait_paiements_client_id FOREIGN KEY ("Client_Id") REFERENCES dim_client ("Company_Id"),
    CONSTRAINT fk_fait_paiements_fournisseur_id FOREIGN KEY ("Fournisseur_Id") REFERENCES dim_fournisseur ("Company_Id"),
    CONSTRAINT fk_fait_paiements_paymentmode_id FOREIGN KEY ("PaymentMode_Id") REFERENCES dim_paiement ("PaymentMode_Id"),
    CONSTRAINT fk_fait_paiements_document_id FOREIGN KEY ("Document_Id") REFERENCES dim_document ("Document_Id")
);

-- Fait : 1 ligne = 1 mouvement de stock d'un produit
CREATE TABLE fait_stock_mouvements (
    "Id" INTEGER NOT NULL,
    "DateKey" INTEGER,
    "Date" DATE,
    "Heure" INTEGER,
    "Product_Id" INTEGER,
    "ProductStock_Id" INTEGER,
    "DocumentId" INTEGER,
    "Document_Id" INTEGER,
    "Action" VARCHAR(255),
    "SourceKind" VARCHAR(255),
    "Direction" VARCHAR(255),
    "Quantity" NUMERIC(18,4),
    "CurrentBalance" NUMERIC(18,4),
    "Extra_cump" NUMERIC(18,4),
    "ValeurMouvement_HT" NUMERIC(18,4),
    "User_Id" INTEGER,
    CONSTRAINT pk_fait_stock_mouvements PRIMARY KEY ("Id"),
    CONSTRAINT fk_fait_stock_mouvements_datekey FOREIGN KEY ("DateKey") REFERENCES dim_temps ("DateKey"),
    CONSTRAINT fk_fait_stock_mouvements_product_id FOREIGN KEY ("Product_Id") REFERENCES dim_produit ("Product_Id"),
    CONSTRAINT fk_fait_stock_mouvements_document_id FOREIGN KEY ("Document_Id") REFERENCES dim_document ("Document_Id"),
    CONSTRAINT fk_fait_stock_mouvements_user_id FOREIGN KEY ("User_Id") REFERENCES dim_utilisateur ("User_Id")
);

-- Fait : 1 ligne = 1 produit × 1 semaine (clé composée)
CREATE TABLE fait_stock_hebdo (
    "Product_Id" INTEGER NOT NULL,
    "SemaineDebut" DATE NOT NULL,
    "DateKey" INTEGER,
    "AnneeSemaine" VARCHAR(255),
    "StockFinSemaine" NUMERIC(18,4),
    "QteEntree" NUMERIC(18,4),
    "QteSortie" NUMERIC(18,4),
    "QteVendue" NUMERIC(18,4),
    "CA_HT" NUMERIC(18,4),
    "EnRupture" BOOLEAN,
    "SemaineComplete" BOOLEAN,
    CONSTRAINT pk_fait_stock_hebdo PRIMARY KEY ("Product_Id", "SemaineDebut"),
    CONSTRAINT fk_fait_stock_hebdo_product_id FOREIGN KEY ("Product_Id") REFERENCES dim_produit ("Product_Id"),
    CONSTRAINT fk_fait_stock_hebdo_datekey FOREIGN KEY ("DateKey") REFERENCES dim_temps ("DateKey")
);

-- Fait : 1 ligne = 1 produit (photo au 30/04/2025)
CREATE TABLE fait_stock_actuel (
    "Product_Id" INTEGER NOT NULL,
    "DateKey" INTEGER,
    "Quantity" NUMERIC(18,4),
    "Quantité d'Alerte" NUMERIC(18,4),
    "EnRupture" BOOLEAN,
    "StockNegatif" BOOLEAN,
    "StockFaible" BOOLEAN,
    "QteVendue_Periode" NUMERIC(18,4),
    "CA_HT_Periode" NUMERIC(18,4),
    "StockMoyenHebdo" NUMERIC(18,4),
    "Rotation" NUMERIC(18,4),
    "CouvertureJours" NUMERIC(18,4),
    "DateDerniereVente" DATE,
    "JoursDepuisDerniereVente" INTEGER,
    "ValeurStock_HT" NUMERIC(18,4),
    "ClasseABC" VARCHAR(255),
    "EstProduitActif" BOOLEAN,
    CONSTRAINT pk_fait_stock_actuel PRIMARY KEY ("Product_Id"),
    CONSTRAINT fk_fait_stock_actuel_product_id FOREIGN KEY ("Product_Id") REFERENCES dim_produit ("Product_Id"),
    CONSTRAINT fk_fait_stock_actuel_datekey FOREIGN KEY ("DateKey") REFERENCES dim_temps ("DateKey")
);
