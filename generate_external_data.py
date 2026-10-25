#!/usr/bin/env python3
"""
Health Retailers – génération de DONNÉES EXTERNES SYNTHÉTIQUES.

L'export réel couvre 7 mois (30/09/2024 → 30/04/2025). Ce script en produit la suite
(01/05/2025 → 29/09/2026) pour disposer de 2 ans d'historique au total.

Les données générées sont écrites À PART, dans ./externe/donnees_synthetiques/ :
elles ne sont jamais mélangées aux fichiers réels de ./fichiers/ (lus, jamais modifiés).

Principe : chaque fichier généré a exactement le même nom, les mêmes colonnes et le même
format que le fichier réel correspondant (séparateur, décimales, dates, encodage), ses
identifiants continuent ceux de l'export, et il référence les mêmes données de référence
(produits, clients, fournisseurs, utilisateurs, caisses). Toutes les distributions sont
apprises sur l'export réel ; les hypothèses ajoutées sont listées dans le README produit.

Entrée  : ./fichiers/                          export réel
          ./externe/sentinelles_inc-3-PAY.csv  incidence grippe (optionnel, réseau Sentinelles)
Sortie  : ./externe/donnees_synthetiques/      10 CSV + README.md + comparaison_mensuelle.csv
                                               + parametres_generation.json

Bibliothèque standard uniquement :
    python generate_external_data.py                  # calendrier français (défaut)
    python generate_external_data.py --calendar TN    # calendrier tunisien (fériés + Ramadan)
    python generate_external_data.py --seed 7 --end 2026-09-29
"""
import argparse
import csv
import html
import io
import json
import math
import random
import re
import statistics
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from itertools import accumulate
from pathlib import Path
from types import SimpleNamespace

csv.field_size_limit(2**31 - 1)

HERE = Path(__file__).resolve().parent
SRC = HERE / "fichiers"
EXT = HERE / "externe"
OUT = EXT / "donnees_synthetiques"

ORIG_START, ORIG_END = date(2024, 9, 30), date(2025, 4, 30)
GEN_START = date(2025, 5, 1)
RECENT = date(2025, 1, 1)          # comportement « récent » de l'export : janvier → avril 2025
MID_ORIG = date(2025, 1, 15)       # point de référence de la tendance

GROWTH_PER_YEAR = 0.06             # hypothèse : +6 %/an de fréquentation
REORDER_DAYS, TARGET_DAYS = 10, 25 # hypothèse : on commande sous 10 jours de demande, pour couvrir 25 jours
SALE_TYPES = ("6", "5", "1")       # vente comptoir, bon de livraison, facture client
TYPE_LABEL = {"6": "Vente Comptoir", "5": "Bon de livraison", "1": "Facture client", "20": "Facture fournisseur"}
TYPE_PREFIX = {"6": "VC", "5": "BL", "1": "FV"}
STOCK_FACTOR = {"6": -1, "5": -1, "1": -1, "20": 1}

# Indices mensuels des mois ABSENTS de l'export (mai → septembre) : hypothèse, relative à la moyenne observée.
ASSUMED_MONTH_INDEX = {"FR": {5: 1.00, 6: 1.04, 7: 1.05, 8: 0.88, 9: 1.00},
                       "TN": {5: 1.00, 6: 1.05, 7: 1.05, 8: 1.00, 9: 1.00}}

# Saisonnalité par famille de produits (repérée par mots-clés dans le libellé) : hypothèse.
SUN_RE = re.compile(r"\b(SPF\s?\d*|SOLAIRES?|ECRAN|SOLEIL|BRONZ\w*|AUTOBRONZ\w*|ANTHELIOS|PHOTODERM|PHOTOPROTEC\w*|SUN)\b")
MOSQUITO_RE = re.compile(r"MOUSTI|INSECT|REPULSI|ANTI[- ]?PIQ")
COLD_RE = re.compile(r"\b(GORGE|RHUME|TOUX|NASAL|NEZ|ORL|IMMUN\w*|PROPOLIS|ZINC|ECHINAC\w*|GRIPP\w*|PASTILLES?|SIROP|"
                     r"EUCALYPTUS|VITAMINE C|VIT C|DEFENSES?)\b")
SEASON_PROFILE = {
    "sun": {1: .35, 2: .35, 3: .55, 4: .85, 5: 1.4, 6: 2.1, 7: 2.5, 8: 2.1, 9: 1.2, 10: .6, 11: .4, 12: .35},
    "mosquito": {1: .4, 2: .4, 3: .5, 4: .8, 5: 1.3, 6: 1.9, 7: 2.3, 8: 2.2, 9: 1.4, 10: .7, 11: .45, 12: .4},
}
EPIDEMIC_AMPLITUDE = 0.35          # hypothèse : sensibilité des produits ORL / immunité à l'incidence grippe

# Hausses de prix (hypothèse) : (date, part des produits concernés, hausse min, hausse max)
PRICE_EVENTS = [(date(2025, 9, 1), .15, .02, .05), (date(2026, 1, 1), .60, .02, .07), (date(2026, 7, 1), .15, .01, .04)]

# Calendrier tunisien (celui que suit réellement l'export : fermetures du 15/10, 17/12, 20/03, Aïd, 09/04)
TN_HOLIDAYS = {date(2025, 5, 1), date(2025, 6, 6), date(2025, 6, 7), date(2025, 6, 26), date(2025, 7, 25),
               date(2025, 8, 13), date(2025, 9, 4), date(2025, 10, 15), date(2025, 12, 17), date(2026, 1, 1),
               date(2026, 3, 20), date(2026, 3, 21), date(2026, 4, 9), date(2026, 5, 1), date(2026, 5, 27),
               date(2026, 5, 28), date(2026, 6, 16), date(2026, 7, 25), date(2026, 8, 13), date(2026, 8, 25)}
RAMADAN = [(date(2025, 3, 1), date(2025, 3, 29)), (date(2026, 2, 18), date(2026, 3, 19))]

RNG = random.Random(42)


# --------------------------------------------------------------------------- #
# utilitaires
# --------------------------------------------------------------------------- #
class Dist:
    """Distribution empirique (valeur → effectif) dans laquelle on tire au sort."""

    def __init__(self, counter, default=""):
        items = [(k, v) for k, v in counter.items() if v > 0] or [(default, 1)]
        self.vals = [k for k, _ in items]
        self.cum = list(accumulate(v for _, v in items))

    def sample(self):
        return RNG.choices(self.vals, cum_weights=self.cum)[0]


def fl(s):
    """'55,9' / '55.9' / '' → float ou None."""
    s = (s or "").strip().replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def num(x, dec=3, sep="."):
    """Nombre au format de l'export : décimales significatives seulement (125 ; 44.72 ; 53.217)."""
    s = f"{x:.{dec}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    if s in ("-0", ""):
        s = "0"
    return s.replace(".", sep)


def poisson(lam):
    if lam <= 0:
        return 0
    if lam > 40:
        return max(0, round(RNG.gauss(lam, math.sqrt(lam))))
    k, p, limit = 0, 1.0, math.exp(-lam)
    while True:
        p *= RNG.random()
        if p <= limit:
            return k
        k += 1


def guid():
    return str(uuid.UUID(int=RNG.getrandbits(128), version=4)).upper()


def clean_name(desc):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", desc or ""))).strip().upper()


# dates – l'export mélange 3 formats : M/D/YYYY H:MM (UTC), DD/MM/YYYY HH:MM (heure locale) et ISO
def us_parse(s):
    return datetime.strptime(s.strip(), "%m/%d/%Y %H:%M")


def fr_parse(s):
    return datetime.strptime(s.strip(), "%d/%m/%Y %H:%M")


def us_dt(dt):
    return f"{dt.month}/{dt.day}/{dt.year} {dt.hour}:{dt.minute:02d}"


def us_day(d):
    return f"{d.month}/{d.day}/{d.year} 0:00"


def fr_dt(dt):
    return dt.strftime("%d/%m/%Y %H:%M")


def iso_z(dt):
    ms = f"{dt.microsecond // 1000:03d}".rstrip("0")
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + (f".{ms}" if ms else "") + "Z"


def last_sunday(y, m):
    d = (date(y, m + 1, 1) if m < 12 else date(y + 1, 1, 1)) - timedelta(1)
    return d - timedelta((d.weekday() + 1) % 7)


def utc_offset(local_dt):
    """Heure de Paris (le serveur du logiciel suit l'heure d'été : +1 h l'hiver, +2 h l'été)."""
    y = local_dt.year
    start = datetime.combine(last_sunday(y, 3), time(2))
    end = datetime.combine(last_sunday(y, 10), time(3))
    return 2 if start <= local_dt < end else 1


def to_utc(local_dt):
    return local_dt - timedelta(hours=utc_offset(local_dt))


def to_local(utc_dt):
    return utc_dt + timedelta(hours=utc_offset(utc_dt + timedelta(hours=1)))


def easter(y):
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 19 * l) // 433
    month = (h + l - 7 * m + 90) // 25
    return date(y, month, (h + l - 7 * m + 33 * month + 19) % 32)


def fr_holidays(y):
    e = easter(y)
    return {date(y, 1, 1), e + timedelta(1), date(y, 5, 1), date(y, 5, 8), e + timedelta(39),
            date(y, 7, 14), date(y, 8, 15), date(y, 11, 1), date(y, 11, 11), date(y, 12, 25)}


def is_open(d, cal):
    if d.weekday() == 6:
        return False
    return d not in (TN_HOLIDAYS if cal == "TN" else fr_holidays(d.year))


def in_ramadan(d):
    return any(a <= d <= b for a, b in RAMADAN)


# --------------------------------------------------------------------------- #
# lecture / écriture au format exact de l'export
# --------------------------------------------------------------------------- #
class Table:
    """Un CSV de l'export réel : contenu + format (encodage, BOM, fin de ligne, séparateur)."""

    def __init__(self, name, delim):
        raw = (SRC / name).read_bytes()
        self.name, self.delim = name, delim
        self.bom = raw.startswith(b"\xef\xbb\xbf")
        try:
            text, self.enc = raw.decode("utf-8-sig"), "utf-8"
        except UnicodeDecodeError:
            text, self.enc = raw.decode("cp1252", errors="replace"), "cp1252"
        self.eol = "\r\n" if b"\r\n" in raw[:20000] else "\n"
        rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delim))
        self.header, self.rows = rows[0], [r for r in rows[1:] if any(c.strip() for c in r)]

    def dicts(self):
        return [dict(zip(self.header, r)) for r in self.rows]


def write_table(table, rows):
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=table.delim, lineterminator=table.eol)
    w.writerow(table.header)
    for r in rows:
        w.writerow([r.get(h, "") for h in table.header])
    data = buf.getvalue().encode(table.enc, errors="replace")
    (OUT / table.name).write_bytes((b"\xef\xbb\xbf" if table.bom else b"") + data)
    print(f"  {table.name:28s} {len(rows):>8,} lignes")


def read_domain_events():
    """DomainEvents.csv : chaque ligne entière est entre guillemets (particularité de l'export)."""
    raw = (SRC / "DomainEvents.csv").read_bytes()
    text = raw.decode("cp1252", errors="replace")
    outer = list(csv.reader(io.StringIO(text, newline="")))
    header = outer[0]
    rows = [next(csv.reader([o[0]])) if len(o) == 1 else o for o in outer[1:] if o]
    eol = "\r\n" if b"\r\n" in raw[:20000] else "\n"
    return header, [r for r in rows if len(r) == 8], eol


def write_domain_events(header, rows, eol):
    out = [",".join(header)]
    for r in rows:
        b = io.StringIO()
        csv.writer(b, lineterminator="").writerow(r)
        out.append('"' + b.getvalue().replace('"', '""') + '"')
    (OUT / "DomainEvents.csv").write_bytes((eol.join(out) + eol).encode("cp1252", errors="replace"))
    print(f"  {'DomainEvents.csv':28s} {len(rows):>8,} lignes")


# --------------------------------------------------------------------------- #
# 1. apprentissage sur l'export réel
# --------------------------------------------------------------------------- #
def learn(cal):
    M = SimpleNamespace(cal=cal)
    t = M.t = {n: Table(n, d) for n, d in (
        ("Documents.csv", ","), ("documentItemm.csv", ";"), ("Transactions.csv", ";"),
        ("TransactionPayments.csv", ","), ("PaymentsList.csv", ";"), ("TresoreriePayments.csv", ","),
        ("CaisseOperations.csv", ","), ("StockMovements.csv", ";"), ("ProductStocks.csv", ";"),
        ("Produits - 24112025081625 (2).csv", ";"))}
    docs = t["Documents.csv"].dicts()
    trans = {r["Id"]: r for r in t["Transactions.csv"].dicts()}
    items = t["documentItemm.csv"].dicts()
    for d in docs:
        d["_loc"] = to_local(us_parse(d["CreatedDate"]))
        d["_company"] = trans.get(d["Transaction_Id"], {}).get("Company_Id", "")
    D = {d["Id"]: d for d in docs}
    M.trans = trans
    # factures client qui refacturent des bons de livraison (RelatedDocuments) : leur CA est déjà compté sur les BL,
    # elles sont exclues des ventes du DWH -> on ne les prend pas comme modèle de « facture client »
    linked = {r["Document1_Id"] for r in Table("RelatedDocuments.csv", ";").dicts()
              if D.get(r["Document1_Id"], {}).get("DocumentType_Id") == "1"}

    # ---- identifiants et numéros : on continue après les valeurs réelles
    M.max = dict(doc=max(int(d["Id"]) for d in docs), trans=max(int(i) for i in trans),
                 item=max(int(r["Id"]) for r in items),
                 tp=max(int(r[0]) for r in t["TransactionPayments.csv"].rows),
                 pl=max(int(r[0]) for r in t["PaymentsList.csv"].rows),
                 sm=max(int(r[0]) for r in t["StockMovements.csv"].rows))
    # proportion d'identifiants « sautés » dans l'export (documents supprimés) : reproduite
    M.gap = dict(doc=1 - len(docs) / M.max["doc"], trans=1 - len(trans) / M.max["trans"],
                 item=1 - len(items) / M.max["item"])
    M.number = {}
    for ty, pre in TYPE_PREFIX.items():
        M.number[ty] = max(int(m.group(1)) for d in docs if d["DocumentType_Id"] == ty
                           for m in [re.match(pre + r"(\d+)/", d["DocumentNumber"])] if m)

    # ---- lignes de documents par produit et par canal
    by_doc = defaultdict(list)
    prod = {}
    for it in items:
        d = D.get(it["Document_Id"])
        if not d or d["Id"] in linked:
            continue
        by_doc[it["Document_Id"]].append(it)
        pid = it["ProductStock_Id"].strip()
        if not pid:
            continue
        ty = d["DocumentType_Id"]
        p = prod.setdefault(pid, dict(desc=None, name="", price={}, tva=None, tva_ff=None, base=Counter(),
                                      disc=defaultdict(list), qty=defaultdict(list), supp=Counter(), units=0.0))
        p["desc"], p["name"] = it["Description"], clean_name(it["Description"])
        if d["State"] != "1":
            continue
        price = fl(it["PrixHt"])
        if price is not None and price > 0:
            p["price"][ty] = price
        if ty in SALE_TYPES:
            p["tva"] = it["Tva"]
        if ty == "20":
            p["tva_ff"] = it["Tva"]
            p["supp"][d["_company"]] += 1
        p["base"][ty] += 2 if d["_loc"].date() >= RECENT else 1
        p["disc"][ty].append((d["_loc"].date() >= RECENT, it["DiscountPourcentage"]))
        if fl(it["Quantity"]):
            p["qty"][ty].append(it["Quantity"])
        if ty in SALE_TYPES and d["_loc"].date() > ORIG_END - timedelta(60):
            p["units"] += max(fl(it["Quantity"]) or 0, 0)
        if ty in SALE_TYPES:
            p["last_sale"] = max(p.get("last_sale", date.min), d["_loc"].date())
    for p in prod.values():
        if p["tva"] is None:
            p["tva"] = p["tva_ff"] if p["tva_ff"] is not None else "19"
        bought = sorted(q for q in (fl(x) for x in p["qty"].get("20", [])) if q and q > 0)
        p["min_order"] = bought[len(bought) // 4] if bought else 1    # quantité minimale habituelle chez le fournisseur
    M.prod = prod
    M.last_sale = {pid: p["last_sale"] for pid, p in prod.items() if "last_sale" in p}
    M.blank_template = next(it for it in items if not it["ProductStock_Id"].strip())

    # prix : ratios médians entre canaux, pour les produits qui n'ont jamais été vendus sur un canal
    def ratio(a, b):
        r = [p["price"][a] / p["price"][b] for p in prod.values() if a in p["price"] and b in p["price"]]
        return statistics.median(r) if r else 1.0
    M.ratio = {ty: ratio(ty, "6") for ty in ("5", "1", "20")}
    produits = t["Produits - 24112025081625 (2).csv"]
    M.catalog_price = {}
    for r in produits.rows:
        name, buy, sell = clean_name(r[1]), fl(r[5]), fl(r[6])
        if name:
            M.catalog_price[name] = (buy, sell)

    # ---- comportement de chaque canal (type de document)
    tp_by_trans = defaultdict(list)
    pl = {r["Id"]: r for r in t["PaymentsList.csv"].dicts()}
    for r in t["TransactionPayments.csv"].dicts():
        if r["Payment_Id"] in pl:
            tp_by_trans[r["Transaction_Id"]].append(pl[r["Payment_Id"]])
    open_days = sorted({d["_loc"].date() for d in docs if d["DocumentType_Id"] == "6" and d["State"] == "1"})
    M.n_open = len(open_days)
    companies = {r[0] for r in Table("CompaniesList.csv", ";").rows}
    M.used_numbers = {d["DocumentNumber"] for d in docs}
    M.ch = {}
    for ty in ("6", "5", "1", "20"):
        allt = [d for d in docs if d["DocumentType_Id"] == ty and d["Id"] not in linked]
        rec = [d for d in allt if d["_loc"].date() >= RECENT] if ty == "6" else allt
        val = [d for d in rec if d["State"] == "1"]
        prod_lines = lambda d: [it for it in by_doc[d["Id"]] if it["ProductStock_Id"].strip()]
        c = SimpleNamespace()
        c.n_lines = Dist(Counter(len(prod_lines(d)) for d in val))
        c.n_blank = Dist(Counter(len(by_doc[d["Id"]]) - len(prod_lines(d)) for d in val))
        c.qty = Dist(Counter(it["Quantity"] for d in val for it in prod_lines(d) if (fl(it["Quantity"]) or 0) > 0), "1")
        # ligne de retour (quantité négative) : tirée à la fréquence réelle du canal, pas parmi les quantités d'un produit,
        # séparément pour les documents d'une ligne (retour seul, rare) et de plusieurs lignes (échange, plus fréquent)
        ret = {True: [0, 0], False: [0, 0]}
        for d in val:
            q = [fl(it["Quantity"]) or 0 for it in prod_lines(d)]
            k = ret[len(q) == 1]
            k[0] += sum(x < 0 for x in q)
            k[1] += sum(x != 0 for x in q)
        c.p_return_line = {single: n / max(1, tot) for single, (n, tot) in ret.items()}
        c.disc = Dist(Counter(it["DiscountPourcentage"] for d in val for it in prod_lines(d)))
        c.doc_disc = Dist(Counter(d["DiscountPercentage"] for d in val))
        c.p_timbre = sum(d["Timbre"] == "1" for d in val) / len(val)
        # seulement des sociétés qui existent encore (l'export référence aussi des sociétés supprimées et 1 facture sans client)
        c.company = Dist(Counter(d["_company"] for d in val if d["_company"] in companies))
        c.price_name = Dist(Counter(d["ProductPriceName_Id"] for d in val), "1")
        c.doc_mode = Dist(Counter(d["PaymentMode_Id"] for d in val))
        c.delivered = Dist(Counter(d["IsDelivered"] for d in val), "FALSE")
        c.creator = Dist(Counter(d["CreatedBy"] for d in val), "3")
        c.hours = Dist(Counter(d["_loc"].hour for d in rec), 10)
        c.p_draft = sum(d["State"] == "0" for d in allt) / len(allt)
        c.p_paid = sum(trans[d["Transaction_Id"]]["IsPayed"] == "VRAI" for d in val) / len(val)
        c.per_day = len([d for d in allt if d["_loc"].date() >= RECENT]) / len([x for x in open_days if x >= RECENT])
        pays = [tp_by_trans[d["Transaction_Id"]] for d in val]
        c.n_pay = Dist(Counter(len(p) for p in pays if p), 1)
        c.pay_mode = Dist(Counter(x["PaymentMode_Id"] for p in pays for x in p))
        delays = Counter()
        for d, p in zip(val, pays):
            for x in p:
                delays[max(0, (fr_parse(x["PaymentDate"]).date() - d["_loc"].date()).days)] += 1
        c.pay_delay = Dist(delays, 0)
        M.ch[ty] = c
    M.vc_unpaid = 1 - M.ch["6"].p_paid

    # caissier d'une vente comptoir selon (jour, heure)
    M.cashier = defaultdict(Counter)
    for d in docs:
        if d["DocumentType_Id"] == "6" and d["_loc"].date() >= RECENT:
            M.cashier[(d["_loc"].weekday(), d["_loc"].hour)][d["CreatedBy"]] += 1
    M.cashier = {k: Dist(v) for k, v in M.cashier.items()}

    # ---- fournisseurs (factures fournisseur)
    ff = sorted((d for d in docs if d["DocumentType_Id"] == "20" and d["State"] == "1"), key=lambda d: d["_loc"])
    M.supp = {}
    ff_lines = defaultdict(list)
    for d in ff:
        ff_lines[d["_company"]].append(d)
    for s, dl in ff_lines.items():
        if s not in companies:
            continue
        lines = [it for d in dl for it in by_doc[d["Id"]] if it["ProductStock_Id"].strip()]
        taxed = [d for d in dl if any(fl(it["TotalTaxes"]) for it in by_doc[d["Id"]])]
        M.supp[s] = SimpleNamespace(rate=len(dl) / M.n_open, line_disc=Dist(Counter(it["DiscountPourcentage"] for it in lines)),
                                    doc_disc=Dist(Counter(d["DiscountPercentage"] for d in dl)),
                                    p_timbre=sum(d["Timbre"] == "1" for d in dl) / len(dl),
                                    p_taxed=len(taxed) / len(dl), last_number=dl[-1]["DocumentNumber"], products=[])
    # produit → fournisseur : le plus fréquent ; sinon celui de la même marque (1er mot du libellé)
    by_token = defaultdict(Counter)
    for p in prod.values():
        for s in list(p["supp"]):
            if s not in M.supp:
                del p["supp"][s]
        if p["supp"]:
            by_token[p["name"].split(" ")[0]][p["supp"].most_common(1)[0][0]] += 1
    supp_dist = Dist(Counter({s: len(v) for s, v in ff_lines.items() if s in M.supp}))
    M.product_supplier = {}
    for pid, p in prod.items():
        if p["supp"]:
            s = p["supp"].most_common(1)[0][0]
        elif by_token.get(p["name"].split(" ")[0]):
            s = by_token[p["name"].split(" ")[0]].most_common(1)[0][0]
        else:
            s = supp_dist.sample()
        M.product_supplier[pid] = s
        if s in M.supp:
            M.supp[s].products.append(pid)

    # ---- trésorerie : caisse de chaque utilisateur, compte bancaire de chaque mode de paiement
    tr = t["TresoreriePayments.csv"].dicts()
    user_caisse, mode_bank = defaultdict(Counter), defaultdict(Counter)
    for r in tr:
        if r["CaisseId"]:
            user_caisse[r["CreatedBy"]][r["CaisseId"]] += 1
        if r["BankAccountId"] and r["SalePaymentId"] in pl:
            mode_bank[pl[r["SalePaymentId"]]["PaymentMode_Id"]][r["BankAccountId"]] += 1
    M.user_caisse = {u: c.most_common(1)[0][0] for u, c in user_caisse.items()}
    M.default_caisse = Counter(r["CaisseId"] for r in tr if r["CaisseId"]).most_common(1)[0][0]
    M.mode_bank = {m: c.most_common(1)[0][0] for m, c in mode_bank.items()}
    M.default_bank = Counter(r["BankAccountId"] for r in tr if r["BankAccountId"]).most_common(1)[0][0]
    M.mode_name = {r["PaymentMode_Id"]: r["PaymentMethodName"] for r in pl.values() if r["PaymentMethodName"]}
    # paiements saisis puis supprimés, et délai avant leur annulation en caisse
    M.p_removed = sum(r["IsRemoved"] == "VRAI" for r in pl.values()) / len(pl)
    M.cancel_delay = [max(0.0, (us_parse(r["CancelledAtUtc"]) - us_parse(r["AddedAtUtc"])).total_seconds() / 60)
                      for r in t["CaisseOperations.csv"].dicts() if r["Status"] == "2" and r["CancelledAtUtc"]] or [10.0]

    # ---- événements de trésorerie : versions, solde de chaque caisse, écarts de caisse
    M.de_header, de_rows, M.de_eol = read_domain_events()
    M.max["de"] = max(int(r[0]) for r in de_rows)
    M.de_version, M.caisse_bal = {}, defaultdict(float)
    opens, closes, close_disc = Counter(), Counter(), []
    caisse_days = defaultdict(set)
    for r in de_rows:
        M.de_version[r[1]] = int(r[2])
        ev, data = r[4].split(".")[-1], json.loads(r[5])
        cid = r[1]
        if ev == "CaisseOpened":
            M.caisse_bal[cid] = 0.0
            opens[cid] += 1
        elif ev == "CaisseTransactionAdded":
            M.caisse_bal[cid] += data["amount"]
            caisse_days[cid].add(r[6].split()[0])
        elif ev == "CaisseClosed":
            M.caisse_bal[cid] = data["balance"]
            closes[cid] += 1
        elif ev == "CaisseDiscrepancyIdentified" and "closeCaisseOperationId" in data.get("source", {}):
            close_disc.append(data["amount"])
    M.p_session = {c: min(1.0, opens[c] / len(caisse_days[c])) for c in caisse_days}
    small = [a for a in close_disc if abs(a) < 500]
    M.p_close_disc = len(small) / max(1, sum(closes.values()))
    M.close_disc = small

    # ---- stock : solde, prix d'achat et CUMP à la fin de l'export ; corrections ; modifications manuelles
    sm = t["StockMovements.csv"].dicts()
    M.stock, M.prc, M.cump = {}, {}, {}
    validated, corrected, corr_delay = defaultdict(set), defaultdict(set), []
    first_val = {}
    manual = []
    for r in sorted(sm, key=lambda r: int(r["Id"])):
        pid = r["ProductStock_Id"]
        M.stock[pid] = fl(r["CurrentBalance"]) or 0.0
        try:
            ex = json.loads(r["Extra"] or "{}")
            M.prc[pid], M.cump[pid] = ex.get("prc", M.prc.get(pid)), ex.get("cump", M.cump.get(pid))
        except json.JSONDecodeError:
            pass
        doc = D.get(r["DocumentId"])
        when = fr_parse(r["MovementDate"])
        if r["Description"].startswith("Modification manuelle"):
            manual.append(r)
        elif doc:
            ty = doc["DocumentType_Id"]
            if r["Description"].startswith("Validation"):
                validated[ty].add(doc["Id"])
                first_val.setdefault(doc["Id"], when)
            elif r["Description"].startswith("Correction"):
                if doc["Id"] not in corrected[ty] and doc["Id"] in first_val:
                    corr_delay.append(max(1, (when - first_val[doc["Id"]]).total_seconds() / 60))
                corrected[ty].add(doc["Id"])
    for r in t["ProductStocks.csv"].dicts():
        M.stock.setdefault(r["Id"], fl(r["Quantity"]) or 0.0)
    M.p_corr = {ty: len(corrected[ty]) / max(1, len(validated[ty])) for ty in TYPE_LABEL}
    M.corr_delay = corr_delay or [30]
    M.manual_rate = len(manual) / M.n_open
    M.manual_qty = Dist(Counter(r["Quantity"] for r in manual), "1")
    M.manual_user = Dist(Counter(r["User_Id"] for r in manual), "3")
    M.sold_products = [pid for pid, p in prod.items() if p["base"]["6"]]

    # ---- demande récente (60 derniers jours) pour le réapprovisionnement
    days60 = len([d for d in open_days if d > ORIG_END - timedelta(60)])
    M.demand = {pid: p["units"] / days60 for pid, p in prod.items() if p["units"]}

    # ---- soldes clients / fournisseurs (champ Extra « cosld ») à la fin de l'export
    M.balance = defaultdict(float)
    for d in sorted(docs, key=lambda d: d["_loc"]):
        m = re.search(r'"cosld":(-?[\d.]+)', d["Extra"])
        if m and d["_company"]:
            M.balance[d["_company"]] = float(m.group(1))

    # ---- niveau des ventes comptoir : jour de semaine, mois, Ramadan
    daily = Counter(d["_loc"].date() for d in docs if d["DocumentType_Id"] == "6")
    normal = [d for d in open_days if d > ORIG_START and not in_ramadan(d)]
    mean_all = statistics.mean(daily[d] for d in normal)
    M.vc_level = mean_all
    M.wd = {w: statistics.mean([daily[d] for d in normal if d.weekday() == w] or [mean_all]) / mean_all for w in range(6)}
    idx = {}
    for m in (10, 11, 12, 1, 2, 4):
        vals = [daily[d] / M.wd[d.weekday()] for d in normal if d.month == m]
        idx[m] = statistics.mean(vals) / mean_all
    idx[3] = (idx[2] + idx[4]) / 2          # mars 2025 = Ramadan dans l'export : remplacé par la moyenne fév./avr.
    norm = statistics.mean(idx.values())
    M.month_index = {m: v / norm for m, v in idx.items()}
    M.month_index.update(ASSUMED_MONTH_INDEX[cal])
    ram = [daily[d] / M.wd[d.weekday()] for d in open_days if in_ramadan(d)]
    ref = [daily[d] / M.wd[d.weekday()] for d in normal if d.month in (2, 4)]
    M.ramadan_factor = statistics.mean(ram) / statistics.mean(ref) if ram and ref else 1.0
    M.orig_docs, M.orig_sm = docs, sm
    return M


def load_epidemics():
    """Incidence hebdomadaire de la grippe (réseau Sentinelles) : (année ISO, semaine) → taux / 100 000."""
    p = EXT / "sentinelles_inc-3-PAY.csv"
    if not p.exists():
        return {}
    lines = [l for l in p.read_text(encoding="utf-8", errors="replace").splitlines() if l and not l.startswith("#")]
    out = {}
    for r in csv.DictReader(lines):
        w = r.get("week", "")
        if len(w) == 6 and fl(r.get("inc100")) is not None:
            out[(int(w[:4]), int(w[4:]))] = fl(r["inc100"])
    return out


# --------------------------------------------------------------------------- #
# 2. modèle des produits : poids de vente qui évoluent dans le temps, prix
# --------------------------------------------------------------------------- #
def build_product_model(M, end):
    epi = load_epidemics()
    orig_weeks = {d.isocalendar()[:2] for d in (ORIG_START + timedelta(i) for i in range((ORIG_END - ORIG_START).days + 1))}
    ref = statistics.mean([epi[w] for w in orig_weeks if w in epi] or [1.0])
    M.epi = {w: v / ref for w, v in epi.items()}
    M.epi_used = bool(epi)
    orig_months = (10, 11, 12, 1, 2, 3, 4)
    gen_days = (end - GEN_START).days
    for pid, p in M.prod.items():
        n = p["name"]
        p["kind"] = "sun" if SUN_RE.search(n) else "mosquito" if MOSQUITO_RE.search(n) else None
        p["cold"] = bool(COLD_RE.search(n))
        # désaisonnalisation : l'export ne couvre qu'octobre → avril
        p["deseason"] = statistics.mean(SEASON_PROFILE[p["kind"]][m] for m in orig_months) if p["kind"] else 1.0
        p["slope"] = max(-0.8, min(0.6, RNG.gauss(0, 0.25)))      # tendance propre au produit (cycle de vie)
        p["stop"] = GEN_START + timedelta(RNG.randrange(gen_days)) if RNG.random() < 0.04 else None
        p["launch"] = None
        mult, d_events = 1.0, []
        for d0, share, lo, hi in PRICE_EVENTS:
            if RNG.random() < share:
                mult *= 1 + RNG.uniform(lo, hi)
                d_events.append((d0, mult))
        p["price_steps"] = d_events
    # quelques produits du catalogue jamais vendus au comptoir sont « lancés » pendant la période générée
    vc_bases = sorted(p["base"]["6"] for p in M.prod.values() if p["base"]["6"])
    median_base = vc_bases[len(vc_bases) // 2]
    candidates = [pid for pid, p in M.prod.items() if not p["base"]["6"] and unit_price(M, pid, "6", GEN_START)]
    for pid in RNG.sample(candidates, min(150, len(candidates))):
        p = M.prod[pid]
        p["launch"] = GEN_START + timedelta(RNG.randrange(gen_days))
        p["base"]["6"] = median_base * RNG.uniform(0.3, 1.5)
    M.weight_cache = {}


def price_mult(p, d):
    m = 1.0
    for d0, v in p["price_steps"]:
        if d >= d0:
            m = v
    return m


def unit_price(M, pid, ty, d):
    p = M.prod[pid]
    base = p["price"].get(ty)
    if base is None:
        vc = p["price"].get("6")
        cat = M.catalog_price.get(p["name"], (None, None))
        if vc is None:
            vc = cat[1] or next((p["price"][k] / M.ratio[k] for k in ("5", "1", "20") if k in p["price"]), None)
        if vc is None:
            return None
        base = (cat[0] if ty == "20" and cat[0] else vc * (M.ratio[ty] if ty != "6" else 1.0))
    return round(base * price_mult(p, d), 3)


def weights(M, ty, d):
    """Poids de tirage des produits pour un canal, recalculés chaque semaine."""
    key = (ty, d.isocalendar()[:2])
    if key in M.weight_cache:
        return M.weight_cache[key]
    t_years = (d - MID_ORIG).days / 365.25
    epi = M.epi.get(d.isocalendar()[:2], M.epi.get(max(M.epi), 1.0) if M.epi else 1.0) if M.epi_used else 1.0
    pids, w = [], []
    for pid, p in M.prod.items():
        b = p["base"][ty]
        if not b or (p["stop"] and d >= p["stop"]) or (p["launch"] and d < p["launch"]):
            continue
        x = b * math.exp(p["slope"] * t_years)
        if p["kind"]:
            x *= SEASON_PROFILE[p["kind"]][d.month] / p["deseason"]
        if p["cold"]:
            x *= max(0.7, min(2.0, 1 + EPIDEMIC_AMPLITUDE * (epi - 1)))
        if p["launch"]:
            x *= min(1.0, (d - p["launch"]).days / 60 + 0.1)
        if unit_price(M, pid, ty, d):
            pids.append(pid)
            w.append(x)
    M.weight_cache[key] = (pids, list(accumulate(w)))
    return M.weight_cache[key]


def pick_products(M, ty, d, k):
    pids, cw = weights(M, ty, d)
    chosen, tries = [], 0
    while len(chosen) < k and tries < 10 * k + 10:
        pid = RNG.choices(pids, cum_weights=cw)[0]
        if pid not in chosen:
            chosen.append(pid)
        tries += 1
    return chosen


def pick_discount(M, pid, ty):
    obs = M.prod[pid]["disc"].get(ty, [])
    recent = [v for r, v in obs if r]
    pool = recent if len(recent) >= 3 else [v for _, v in obs]
    return RNG.choice(pool) if len(pool) >= 3 else M.ch[ty].disc.sample()


def pick_quantity(M, pid, ty, single):
    """Quantité tirée parmi celles vendues pour CE produit sur ce canal (un produit cher ne part pas par 100).
    Les retours sont tirés à part, à la fréquence réelle des lignes négatives du canal (document d'une seule ligne
    ou de plusieurs) : tirer parmi les quantités observées d'un produit peu vendu donnerait un retour une fois sur
    deux s'il a été retourné une fois."""
    obs = [q for q in M.prod[pid]["qty"].get(ty, []) if (fl(q) or 0) > 0]
    q = fl(RNG.choice(obs) if len(obs) >= 2 else M.ch[ty].qty.sample()) or 1.0
    return -q if RNG.random() < M.ch[ty].p_return_line[single] else q


# --------------------------------------------------------------------------- #
# 3. simulation jour par jour
# --------------------------------------------------------------------------- #
def compute_line(price, qty, disc_s, tva_s, g, tax_rate):
    """Reproduit les calculs du logiciel : remise ligne, puis remise document (colonnes Sum…), TVA, taxe 1 %."""
    d, rate = fl(disc_s) or 0.0, fl(tva_s)
    pth = round(price * qty * (1 - d / 100), 3)
    tva = round(pth * rate / 100, 3) if rate is not None else None
    pttc = round(pth + (tva or 0), 3)
    s_ht = pth * (1 - g / 100)
    s_tva = s_ht * (rate or 0) / 100
    s_tax = s_ht * tax_rate
    s_ttc = s_ht + s_tva + s_tax
    q = qty or 1
    return dict(pth=pth, tva=tva, pttc=pttc, pttc_unit=pttc / q, s_net=price * (1 - d / 100) * (1 - g / 100),
                s_disc=price * qty - s_ht, s_ht=s_ht, s_tva=s_tva, s_tax=s_tax, s_ttc=s_ttc, s_ttc_unit=s_ttc / q)


class Sim:
    def __init__(self, M, end):
        self.M, self.end = M, end
        self.ids = dict(M.max)
        self.number = dict(M.number)
        self.supp_number = {s: v.last_number for s, v in M.supp.items()}
        self.used = set(M.used_numbers)
        self.last_sale = dict(M.last_sale)
        self.stock = defaultdict(float, M.stock)
        self.demand = defaultdict(float, M.demand)
        self.balance = defaultdict(float, M.balance)
        self.docs, self.items, self.trans, self.sm, self.payments = [], [], [], [], []
        self.seq = 0

    def nid(self, kind):
        gap = self.M.gap.get(kind, 0)
        self.ids[kind] += 1
        while gap and RNG.random() < gap:
            self.ids[kind] += 1
        return self.ids[kind]

    def next_supplier_number(self, s):
        """Numéro suivant dans la série du fournisseur, jamais déjà utilisé (certaines séries réelles ne sont pas croissantes)."""
        new = self.supp_number.get(s) or f"FA{GEN_START:%y}-0000"
        while new in self.used:
            m = re.search(r"(\d+)(\D*)$", new)
            new = new + "-1" if not m else new[:m.start(1)] + str(int(m.group(1)) + 1).zfill(len(m.group(1))) + m.group(2)
        self.used.add(new)
        self.supp_number[s] = new
        return new

    def next_number(self, ty):
        while True:
            self.number[ty] += 1
            new = f"{TYPE_PREFIX[ty]}{self.number[ty]:04d}/24"
            if new not in self.used:
                self.used.add(new)
                return new

    def local_time(self, day, hours):
        h = hours.sample()
        return datetime.combine(day, time(h, RNG.randrange(60), RNG.randrange(60), RNG.randrange(1000) * 1000))

    def run(self):
        M = self.M
        day = GEN_START
        while day <= self.end:
            if is_open(day, M.cal):
                self.simulate_day(day)
            day += timedelta(1)

    def simulate_day(self, day):
        M = self.M
        growth = (1 + GROWTH_PER_YEAR) ** ((day - MID_ORIG).days / 365.25)
        lam = M.vc_level * M.wd[day.weekday()] * M.month_index[day.month] * growth
        if M.cal == "TN" and in_ramadan(day):
            lam *= M.ramadan_factor
        events = [(self.local_time(day, M.ch["6"].hours), "6", None) for _ in range(poisson(lam * RNG.lognormvariate(0, .12)))]
        for ty in ("5", "1"):
            events += [(self.local_time(day, M.ch[ty].hours), ty, None) for _ in range(poisson(M.ch[ty].per_day * growth))]
        # réapprovisionnement : chaque fournisseur commande quand des produits passent sous le seuil
        # (chaque fournisseur est consulté au moins tous les ~30 jours ouvrés ; à chaque commande on ajoute
        #  aussi les produits en rupture vendus dans les 120 derniers jours)
        for s, sp in M.supp.items():
            if RNG.random() >= min(0.9, max(sp.rate * 1.2, 0.035)):
                continue
            need = []
            for pid in sp.products:
                dmd, st = self.demand[pid], self.stock[pid]
                p = M.prod[pid]
                if p["stop"] and day >= p["stop"]:
                    continue
                recent_sale = (day - self.last_sale.get(pid, date.min)).days <= 120
                if (dmd > 0.002 and st <= max(1.0, dmd * REORDER_DAYS)) or (st <= 0 and recent_sale):
                    q = max(1, math.ceil(dmd * TARGET_DAYS - max(st, 0.0)))   # un stock négatif n'est pas « rattrapé »
                    q = q if q <= 3 else (math.ceil(q / 3) * 3 if q < 12 else math.ceil(q / 6) * 6)
                    q = max(q, p["min_order"])
                    need.append((st - dmd * REORDER_DAYS, pid, q))
            if need:
                need.sort()                       # les plus urgents d'abord ; nb de lignes tiré dans la distribution réelle
                ruptures = sum(1 for key, pid, _ in need if self.stock[pid] <= 0)
                k = min(45, max(1, int(M.ch["20"].n_lines.sample()), ruptures))
                events.append((self.local_time(day, M.ch["20"].hours), "20", (s, [(pid, q) for _, pid, q in need[:k]])))
        events.sort(key=lambda e: e[0])
        sold = Counter()
        for loc, ty, extra in events:
            self.make_document(ty, loc, extra, sold)
        for _ in range(poisson(M.manual_rate)):
            pid = RNG.choice(M.sold_products)
            q = fl(M.manual_qty.sample()) or 1
            loc = datetime.combine(day, time(RNG.randrange(8, 18), RNG.randrange(60)))
            self.add_sm(loc, pid, q, "0", "Modification manuelle de stock", M.manual_user.sample(), None)
            self.stock[pid] += q
        for pid in set(self.demand) | set(sold):
            self.demand[pid] = 0.95 * self.demand[pid] + 0.05 * sold[pid]

    def add_sm(self, loc, pid, qty, doc_id, desc, user, cost):
        self.seq += 1
        self.sm.append(dict(loc=loc, seq=self.seq, pid=pid, qty=qty, doc=str(doc_id), desc=desc, user=user, cost=cost))

    def make_document(self, ty, loc, extra, sold):
        M, c = self.M, self.M.ch[ty]
        day = loc.date()
        did, tid = self.nid("doc"), self.nid("trans")
        state = "0" if RNG.random() < c.p_draft else "1"
        if ty == "20":
            company, wanted = extra
            sp = M.supp[company]
            number = self.next_supplier_number(company)
            doc_disc, p_timbre = sp.doc_disc.sample(), sp.p_timbre
            taxed = RNG.random() < sp.p_taxed
            creator = c.creator.sample()
        else:
            company = c.company.sample()
            number = self.next_number(ty)
            wanted = [(pid, None) for pid in pick_products(M, ty, day, c.n_lines.sample())]
            doc_disc, p_timbre, taxed = c.doc_disc.sample(), c.p_timbre, False
            if ty == "6":
                cd = M.cashier.get((loc.weekday(), loc.hour))
                creator = cd.sample() if cd else c.creator.sample()
            else:
                creator = c.creator.sample()
        g = fl(doc_disc) or 0.0
        lines = []
        for pid, q in wanted:
            price = unit_price(M, pid, ty, day)
            if price is None:
                continue
            qty = q if q is not None else pick_quantity(M, pid, ty, len(wanted) == 1)
            disc = M.supp[company].line_disc.sample() if ty == "20" else pick_discount(M, pid, ty)
            tva = M.prod[pid]["tva"]
            lines.append((pid, qty, price, disc, tva, compute_line(price, qty, disc, tva, g, .01 if taxed and RNG.random() < .6 else 0)))
        # lignes du document
        order = 2
        for pid, qty, price, disc, tva, L in lines:
            self.items.append({
                "Id": self.nid("item"), "DisplayOrder": order, "Description": M.prod[pid]["desc"],
                "Quantity": num(qty, 3, ","), "PrixHt": num(price, 3, ","), "Tva": tva,
                "PrixTotalHt": num(L["pth"], 3, ","), "PrixTotalTtc": num(L["pttc"], 3, ","), "DiscountPourcentage": disc,
                "Document_Id": did, "ProductStock_Id": pid, "TotalTva": "" if L["tva"] is None else num(L["tva"], 3, ","),
                "TotalTaxes": num(L["s_tax"], 3, ",") if L["s_tax"] else "",
                "SumPrixNetHt": num(L["s_net"], 4, ","), "SumQuantityUnit": num(qty, 3, ","),
                "SumDiscountTotal": num(L["s_disc"], 4, ","), "SumPrixTotalHt": num(L["s_ht"], 4, ","),
                "SumTotalTva": num(L["s_tva"], 4, ","), "SumIncludedTaxes": "0", "SumTotalTaxes": num(L["s_tax"], 4, ","),
                "SumPrixTotalTtc": num(L["s_ttc"], 4, ","), "PrixTtc": num(L["pttc_unit"], 3, ","),
                "SumPrixNetTtc": num(L["s_ttc_unit"], 4, ","), "Extra": "{}"})
            order += 1
        for _ in range(c.n_blank.sample()):        # lignes vides (mise en page des factures), comme dans l'export
            row = dict(M.blank_template)
            row.update(Id=self.nid("item"), Document_Id=did, DisplayOrder=order)
            self.items.append(row)
            order += 1
        total_ht = round(sum(L["pth"] for *_, L in lines), 3)
        net_ht = round(sum(L["s_ht"] for *_, L in lines), 3)
        tot_tva = round(sum(L["s_tva"] for *_, L in lines), 3)
        tot_tax = round(sum(L["s_tax"] for *_, L in lines), 3)
        ttc = round(net_ht + tot_tva + tot_tax, 3)
        timbre = 1 if RNG.random() < p_timbre else 0
        final = round(ttc + timbre, 3)

        # validation, éventuelle correction (le document est modifié puis revalidé plus tard)
        validated = loc
        if state == "1" and RNG.random() < M.p_corr[ty]:
            delay = RNG.choice(M.corr_delay)
            validated = min(loc + timedelta(minutes=delay), datetime.combine(self.end, time(23, 0)))
        if state == "1":
            for pid, qty, price, disc, tva, L in lines:
                q = qty * STOCK_FACTOR[ty]
                cost = L["s_net"] if ty == "20" else None
                self.add_sm(loc, pid, q, did, f"Validation de {TYPE_LABEL[ty]} - {number}", creator, (cost, price) if cost else None)
                if validated != loc:
                    self.add_sm(validated, pid, -q, did, f"Correction de {TYPE_LABEL[ty]} - {number}", creator, None)
                    self.add_sm(validated, pid, q, did, f"Validation de {TYPE_LABEL[ty]} - {number}", creator, None)
                self.stock[pid] += q
                if ty in SALE_TYPES:
                    sold[pid] += max(qty, 0)
                    self.last_sale[pid] = day

        # paiements
        paid_total, pays = 0.0, []
        # un ticket ou une facture de total nul ou négatif (retour) ne crée aucun paiement : dans l'export, tous les
        # paiements sont positifs, l'argent rendu n'est pas enregistré comme paiement
        if state == "1" and ty != "5" and final > 0:
            p_paid = 1 - M.vc_unpaid if ty == "6" else c.p_paid
            if RNG.random() < p_paid:
                n = 1 if ty in ("6", "20") else max(1, int(c.n_pay.sample()))
                shares = [RNG.uniform(.2, 1) for _ in range(n)]
                amounts = [round(final * s / sum(shares), 3) for s in shares]
                amounts[-1] = round(final - sum(amounts[:-1]), 3)
                for i, a in enumerate(amounts):
                    if ty == "6":
                        when = loc
                    else:
                        when = datetime.combine(day + timedelta(int(c.pay_delay.sample())), time(RNG.randrange(8, 18), RNG.randrange(60)))
                        when = max(when, loc + timedelta(minutes=5))
                    if when.date() > self.end:
                        continue
                    pays.append(dict(when=when, amount=a, mode=c.pay_mode.sample(), company=company, trans=tid, doc_type=ty,
                                     number=number, user=creator, advance=(n > 1 and i < n - 1), purchase=ty == "20"))
                    paid_total += a
        self.payments += pays
        is_paid = state == "1" and (paid_total >= final - 0.001 if ty != "5" else RNG.random() < c.p_paid)
        cosld = self.balance[company]
        if state == "1":
            self.balance[company] += final - paid_total
        extra_json = "{}" if ty == "5" or state == "0" else ('{"cosld":0.0}' if abs(cosld) < 5e-5 else f'{{"cosld":{cosld:.4f}}}')

        self.docs.append({
            "Id": did, "DocumentNumber": number, "DocumentDate": us_day(day), "State": state,
            "TotalHt": num(total_ht), "TotalNetHt": num(net_ht), "DiscountPercentage": doc_disc, "TotalTva": num(tot_tva),
            "TotalTtc": num(ttc), "Timbre": str(timbre), "FinalPrice": num(final), "IsDelivered": c.delivered.sample(),
            "DocumentType_Id": ty, "Transaction_Id": tid, "PaymentMode_Id": c.doc_mode.sample(),
            "ProductPriceName_Id": c.price_name.sample(), "DefaultStock_Id": "1", "TotalDiscount": num(total_ht - net_ht),
            "IncludedTaxes": "0", "TotalTaxes": num(tot_tax), "TotalExtraTaxes": str(timbre),
            "CreatedDate": us_dt(to_utc(loc)), "CreatedBy": creator, "ModifiedDate": us_dt(to_utc(validated)),
            "ModifiedBy": creator, "ValidatedDate": us_dt(to_utc(validated)) if state == "1" else "",
            "ValidatedBy": creator if state == "1" else "", "Extra": extra_json,
            "TotalRetenueSurHt": "0", "TotalRetenueSurTva": "0", "TotalRetenueSurTtc": "0",
            "_loc": loc, "_final": final})
        link = str(did) if state == "1" or ty == "6" else ""
        self.trans.append({
            "Id": tid, "IsPayed": "VRAI" if is_paid else "FAUX", "PayedAmount": num(paid_total, 3, ","),
            "IsDestocked": "VRAI" if state == "1" else "FAUX", "IsRestocked": "FAUX", "Company_Id": company,
            "PaymentDocument_Id": link if ty != "5" else "", "DestockDocument_Id": link})


# --------------------------------------------------------------------------- #
# 4. trésorerie : paiements, caisses, comptes bancaires, événements
# --------------------------------------------------------------------------- #
def build_treasury(M, S):
    pl, tp, tr, co, events = [], [], [], [], []
    cash_by_caisse_day = defaultdict(list)
    ev_seq = [0]

    def event(utc, agg, agg_name, name, data, user):
        ev_seq[0] += 1
        events.append(dict(utc=utc, seq=ev_seq[0], agg=agg, agg_name=agg_name, name=name,
                           data=json.dumps(data, separators=(",", ":")), user=user))

    def ts7(dt):     # horodatage à 7 décimales des événements d'annulation (« 2024-10-12T11:36:01.6474661Z »)
        return dt.strftime("%Y-%m-%dT%H:%M:%S") + f".{dt.microsecond:06d}{RNG.randrange(10)}Z"

    def emit(p, removed):
        """Un paiement : PaymentsList, (TransactionPayments), Tresorerie, (CaisseOperations), événements.
        removed=True : paiement saisi puis supprimé (non rattaché à la transaction), comme ~1 % des paiements réels."""
        S.ids["pl"] += 1
        pid, loc, utc, mode, amount, user = S.ids["pl"], p["when"], to_utc(p["when"]), p["mode"], p["amount"], p["user"]
        sign = -1 if p["purchase"] else 1             # achats : montant positif dans PaymentsList, négatif en trésorerie
        what = {"6": "Vente Comptoir", "1": "Facture client", "20": "Facture fournisseur"}[p["doc_type"]]
        desc = (f"Avance sur {what} N� {p['number']}" if p["advance"]
                else f"Paiement de la pi�ce : {what} N� {p['number']}")
        extra = "{}"
        if mode == "11" and not p["purchase"]:
            given = math.ceil(amount / 10) * 10 if amount > 20 else math.ceil(amount / 5) * 5
            extra = f'{{"gA":{given:.1f},"rA":{num(given - amount)}}}'
        pl.append({"Id": pid, "IsRemoved": "VRAI" if removed else "FAUX", "Company_Id": p["company"],
                   "Amount": num(amount, 3, ","), "PaymentDate": fr_dt(loc), "Reference": "", "Description": desc,
                   "PaymentMode_Id": mode, "PaymentMethodName": M.mode_name.get(mode, ""), "Extra": extra})
        if not removed:
            S.ids["tp"] += 1
            tp.append({"Id": S.ids["tp"], "Amount": num(amount), "Transaction_Id": p["trans"], "Payment_Id": pid})
        tid = guid()
        cash = mode in ("", "11")
        caisse = M.user_caisse.get(user, M.default_caisse) if cash else ""
        bank = "" if cash else M.mode_bank.get(mode, M.default_bank)
        tr.append({"Id": tid, "SalePaymentId": pid, "Amount": num(sign * amount), "IsPurchase": "TRUE" if p["purchase"] else "FALSE",
                   "BankAccountId": bank, "CaisseId": caisse, "CreatedAtUtc": us_dt(utc), "CreatedBy": user,
                   "Removed": "TRUE" if removed else "FALSE"})
        data = {"paymentId": tid.lower(), "salePaymentId": pid}
        data["caisseId" if cash else "bankAccountId"] = (caisse or bank).lower()
        data["amount"] = round(sign * amount, 4)
        if mode:
            data["paymentMode"] = M.mode_name.get(mode, "")
        data.update(isCashPaymentMode=cash, date=iso_z(loc), isPurchase=p["purchase"])
        event(utc, tid, "Tresorerie.Payments.Payment", "Tresorerie.PaymentAdded", data, user)
        cancel = min(utc + timedelta(minutes=RNG.choice(M.cancel_delay)),
                     to_utc(datetime.combine(S.end, time(23, 59)))) if removed else None
        if cash:
            co.append({"Id": guid(), "CaisseId": caisse, "TransactionId": tid, "AddedAtUtc": us_dt(utc),
                       "CancelledAtUtc": us_dt(cancel) if removed else "", "AddedByUserId": user,
                       "CancelledByUserId": user if removed else "", "Amount": num(sign * amount),
                       "Status": "2" if removed else "1" if p["purchase"] else "0", "PaymentId": tid})
            event(utc, caisse, "Tresorerie.Caisses.Caisse", "Tresorerie.CaisseTransactionAdded",
                  {"caisseId": caisse.lower(), "transactionId": tid.lower(), "utcTimestamp": iso_z(utc),
                   "source": {"paymentId": tid.lower()}, "amount": round(sign * amount, 4),
                   "status": "debited" if p["purchase"] else "cashed", "workflowId": guid().lower()}, user)
            if not removed:
                cash_by_caisse_day[(caisse, loc.date())].append((utc, sign * amount, user))
        else:
            midnight = to_utc(datetime.combine(loc.date(), time(0)))
            event(utc, bank, "Tresorerie.BankAccount", "Tresorerie.BankAccountTransactionAdded",
                  {"bankAccountId": bank.lower(), "transactionId": tid.lower(), "utcTimestamp": iso_z(midnight),
                   "source": {"paymentId": tid.lower()}, "amount": round(sign * amount, 4),
                   "status": "emitted" if p["purchase"] else "received", "workflowId": guid().lower()}, user)
        if removed:
            event(cancel, tid, "Tresorerie.Payments.Payment", "Tresorerie.PaymentRemoved", {"paymentId": tid.lower()}, user)
            if cash:
                event(cancel, caisse, "Tresorerie.Caisses.Caisse", "Tresorerie.CaisseTransactionCancelled",
                      {"transactionId": tid.lower(), "caisseId": caisse.lower(), "timestamp": ts7(cancel)}, user)
            else:
                event(cancel, bank, "Tresorerie.BankAccount", "Tresorerie.BankAccountTransactionCancelled",
                      {"transactionId": tid.lower(), "bankAccountId": bank.lower(), "timestamp": ts7(cancel)}, user)

    for p in sorted(S.payments, key=lambda p: p["when"]):
        if RNG.random() < M.p_removed:
            emit(p, removed=True)
        emit(p, removed=False)

    # sessions de caisse : ouverture (solde 0 → écart = argent retiré), fermeture (écart de comptage)
    bal = defaultdict(float, M.caisse_bal)
    for (caisse, d), txns in sorted(cash_by_caisse_day.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        txns.sort()
        user = txns[0][2]
        if RNG.random() < M.p_session.get(caisse, 0.6):
            t_open = txns[0][0] - timedelta(minutes=RNG.uniform(3, 40))
            op = guid().lower()
            event(t_open, caisse, "Tresorerie.Caisses.Caisse", "Tresorerie.CaisseOpened",
                  {"caisseId": caisse.lower(), "balance": 0.0, "operationId": op}, user)
            if abs(bal[caisse]) > 5e-4:
                event(t_open, caisse, "Tresorerie.Caisses.Caisse", "Tresorerie.CaisseDiscrepancyIdentified",
                      {"caisseId": caisse.lower(), "discrepancyId": guid().lower(), "expectedBalance": round(bal[caisse], 4),
                       "foundBalance": 0.0, "amount": round(-bal[caisse], 4), "source": {"openCaisseOperationId": op}}, user)
            bal[caisse] = 0.0
            bal[caisse] += sum(a for _, a, _ in txns)
            t_close = txns[-1][0] + timedelta(minutes=RNG.uniform(3, 30))
            delta = RNG.choice(M.close_disc) if M.close_disc and RNG.random() < M.p_close_disc else 0.0
            found = round(bal[caisse] + delta, 3)
            op = guid().lower()
            event(t_close, caisse, "Tresorerie.Caisses.Caisse", "Tresorerie.CaisseClosed",
                  {"caisseId": caisse.lower(), "operationId": op, "balance": found}, txns[-1][2])
            if delta:
                event(t_close, caisse, "Tresorerie.Caisses.Caisse", "Tresorerie.CaisseDiscrepancyIdentified",
                      {"caisseId": caisse.lower(), "discrepancyId": guid().lower(), "expectedBalance": round(bal[caisse], 4),
                       "foundBalance": found, "amount": round(found - bal[caisse], 4),
                       "source": {"closeCaisseOperationId": op}}, txns[-1][2])
            bal[caisse] = found
        else:
            bal[caisse] += sum(a for _, a, _ in txns)

    # numérotation : Id global dans l'ordre du temps, version par agrégat (continue celles de l'export)
    version = defaultdict(int, M.de_version)
    de_rows = []
    for e in sorted(events, key=lambda e: (e["utc"], e["seq"])):
        S.ids["de"] += 1
        version[e["agg"]] += 1
        de_rows.append([str(S.ids["de"]), e["agg"], str(version[e["agg"]]), e["agg_name"], e["name"], e["data"],
                        us_dt(e["utc"]), str(e["user"])])
    return pl, tp, tr, co, de_rows


# --------------------------------------------------------------------------- #
# 5. mouvements de stock : solde courant, prix d'achat, CUMP (coût moyen pondéré)
# --------------------------------------------------------------------------- #
def build_stock_movements(M, S):
    bal = defaultdict(float, M.stock)
    prc, cump = dict(M.prc), dict(M.cump)
    rows = []
    for m in sorted(S.sm, key=lambda m: (m["loc"], m["seq"])):
        pid, q = m["pid"], m["qty"]
        if m["cost"]:
            cost, price = m["cost"]
            before = max(bal[pid], 0.0)
            old = cump.get(pid) or cost
            cump[pid] = (before * old + q * cost) / (before + q) if before + q > 0 else cost
            prc[pid] = price
        bal[pid] += q
        if prc.get(pid) is None:
            prc[pid] = unit_price(M, pid, "20", m["loc"].date()) or 0.0
        if cump.get(pid) is None:
            cump[pid] = prc[pid]
        S.ids["sm"] += 1
        rows.append({"Id": S.ids["sm"], "DocumentId": m["doc"], "MovementDate": fr_dt(m["loc"]), "Quantity": num(q, 3, ","),
                     "CurrentBalance": num(bal[pid], 3, ","), "Description": m["desc"], "ProductStock_Id": pid, "User_Id": m["user"],
                     "Extra": f'{{"prc":{prc[pid]:.3f},"cump":{cump[pid]:.3f}}}'})
    return rows, bal


# --------------------------------------------------------------------------- #
# 6. sorties : CSV, comparaison mensuelle, paramètres, README
# --------------------------------------------------------------------------- #
def monthly_comparison(M, S, sm_rows):
    def agg(docs, sm_dates, source):
        out = defaultdict(lambda: Counter())
        for d in docs:
            if d["State"] != "1":
                continue
            m, ty = d["_loc"].strftime("%Y-%m"), d["DocumentType_Id"]
            o = out[m]
            if ty == "6":
                o["nb_ventes_comptoir"] += 1
                o["ca_ttc_comptoir"] += fl(d["FinalPrice"]) or 0
            elif ty == "5":
                o["nb_bons_livraison"] += 1
            elif ty == "1":
                o["nb_factures_client"] += 1
            elif ty == "20":
                o["nb_factures_fournisseur"] += 1
                o["achats_ttc"] += fl(d["FinalPrice"]) or 0
        for dt in sm_dates:
            out[dt.strftime("%Y-%m")]["nb_mouvements_stock"] += 1
        rows = []
        for m in sorted(out):
            o = out[m]
            rows.append(dict(mois=m, source=source, nb_ventes_comptoir=o["nb_ventes_comptoir"],
                             ca_ttc_comptoir=round(o["ca_ttc_comptoir"], 2),
                             panier_moyen_ttc=round(o["ca_ttc_comptoir"] / o["nb_ventes_comptoir"], 2) if o["nb_ventes_comptoir"] else "",
                             nb_bons_livraison=o["nb_bons_livraison"], nb_factures_client=o["nb_factures_client"],
                             nb_factures_fournisseur=o["nb_factures_fournisseur"], achats_ttc=round(o["achats_ttc"], 2),
                             nb_mouvements_stock=o["nb_mouvements_stock"]))
        return rows
    orig = agg(M.orig_docs, [fr_parse(r["MovementDate"]) for r in M.orig_sm if r["MovementDate"] >= ""], "original")
    gen = agg(S.docs, [fr_parse(r["MovementDate"]) for r in sm_rows], "synthetique")
    return [r for r in orig if r["mois"] >= "2024-09"] + gen


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    global RNG
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--calendar", choices=["FR", "TN"], default="FR", help="jours de fermeture : France (défaut) ou Tunisie")
    ap.add_argument("--seed", type=int, default=42, help="graine aléatoire (même graine = mêmes données)")
    ap.add_argument("--end", default="2026-09-29", help="dernier jour généré (AAAA-MM-JJ)")
    args = ap.parse_args()
    RNG = random.Random(args.seed)
    end = date.fromisoformat(args.end)

    print("1. Apprentissage sur l'export réel ...")
    M = learn(args.calendar)
    build_product_model(M, end)
    print("2. Simulation du", GEN_START, "au", end, f"(calendrier {args.calendar}) ...")
    S = Sim(M, end)
    S.run()
    print("3. Trésorerie et stock ...")
    pl, tp, tr, co, de_rows = build_treasury(M, S)
    sm_rows, final_stock = build_stock_movements(M, S)

    print("4. Écriture dans", OUT)
    OUT.mkdir(parents=True, exist_ok=True)
    t = M.t
    write_table(t["Documents.csv"], S.docs)
    write_table(t["documentItemm.csv"], S.items)
    write_table(t["Transactions.csv"], S.trans)
    write_table(t["TransactionPayments.csv"], tp)
    write_table(t["PaymentsList.csv"], pl)
    write_table(t["TresoreriePayments.csv"], tr)
    write_table(t["CaisseOperations.csv"], co)
    write_table(t["StockMovements.csv"], sm_rows)
    write_domain_events(M.de_header, de_rows, M.de_eol)
    ps = []
    for r in t["ProductStocks.csv"].dicts():
        q = num(final_stock.get(r["Id"], fl(r["Quantity"]) or 0), 3, ",")
        ps.append({**r, "Quantity": q, "TotalQuantity": q})
    write_table(t["ProductStocks.csv"], ps)

    comp = monthly_comparison(M, S, sm_rows)
    write_csv(OUT / "comparaison_mensuelle.csv", comp)
    params = dict(
        graine=args.seed, calendrier=args.calendar, periode_generee=[str(GEN_START), str(end)],
        croissance_frequentation_par_an=GROWTH_PER_YEAR, indices_mensuels=dict(sorted(M.month_index.items())),
        indices_mensuels_supposes=ASSUMED_MONTH_INDEX[args.calendar],
        facteur_jour_semaine={["lun", "mar", "mer", "jeu", "ven", "sam"][k]: round(v, 3) for k, v in M.wd.items()},
        ventes_comptoir_par_jour_ouvre_reference=round(M.vc_level, 1), facteur_ramadan_observe=round(M.ramadan_factor, 3),
        hausses_de_prix=[dict(date=str(d), part_produits=s, hausse_min=a, hausse_max=b) for d, s, a, b in PRICE_EVENTS],
        saisonnalite_produits=SEASON_PROFILE, amplitude_effet_grippe=EPIDEMIC_AMPLITUDE if M.epi_used else 0,
        produits_saisonniers=dict(solaires=sum(p["kind"] == "sun" for p in M.prod.values()),
                                  anti_moustiques=sum(p["kind"] == "mosquito" for p in M.prod.values()),
                                  orl_immunite=sum(p["cold"] for p in M.prod.values())),
        produits_lances=sum(1 for p in M.prod.values() if p["launch"]),
        produits_arretes=sum(1 for p in M.prod.values() if p["stop"]),
        probabilite_correction=M.p_corr, probabilite_paiement_supprime=round(M.p_removed, 4),
        stock_negatif_fin=sum(1 for v in final_stock.values() if v < 0), identifiants_depart=M.max)
    (OUT / "parametres_generation.json").write_text(json.dumps(params, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    write_readme(M, S, args, end, comp, params)
    print("Terminé.")


def write_readme(M, S, args, end, comp, params):
    def table(rows):
        cols = ["mois", "source", "nb_ventes_comptoir", "ca_ttc_comptoir", "panier_moyen_ttc", "nb_bons_livraison",
                "nb_factures_client", "nb_factures_fournisseur", "achats_ttc"]
        out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
        out += ["| " + " | ".join(str(r[c]) for c in cols) + " |" for r in rows]
        return "\n".join(out)
    sp = params["produits_saisonniers"]
    cal_txt = ("français (dimanches, 1er janv., lundi de Pâques, 1er et 8 mai, Ascension, 14 juil., 15 août, "
               "1er et 11 nov., 25 déc. ; le lundi de Pentecôte reste ouvert)" if args.calendar == "FR" else
               "tunisien (fériés civils et religieux 2025-2026, Ramadan 2026 du 18/02 au 19/03 avec le facteur observé "
               f"en mars 2025 : ×{M.ramadan_factor:.2f})")
    text = f"""# Données externes synthétiques — suite de l'export (01/05/2025 → {end:%d/%m/%Y})

> **Ces données sont générées par simulation. Elles ne sont pas réelles.**
> Elles prolongent l'export réel du logiciel (30/09/2024 → 30/04/2025, 7 mois) pour disposer de
> **2 ans d'historique** au total. Elles sont rangées ici, dans `externe/`, et ne sont jamais mélangées
> aux fichiers réels de `fichiers/`. Dans l'entrepôt, la délimitation se fait **par la date** : réel jusqu'au
> 30/04/2025 inclus, synthétique à partir du 01/05/2025 (aucune colonne dédiée).

Produit par `generate_external_data.py` (bibliothèque standard Python), graine `{args.seed}`, calendrier `{args.calendar}` :

```bash
python generate_external_data.py                    # régénère exactement les mêmes fichiers
python generate_external_data.py --calendar TN      # variante avec le calendrier tunisien
```

## Fichiers

Même nom, mêmes colonnes et **même format** que le fichier réel correspondant (séparateur, virgule décimale,
formats de date, `VRAI/FAUX`, encodage, guillemets de `DomainEvents.csv`). Le script de nettoyage
`clean_data.py` s'applique donc tel quel.

| Fichier | Lignes | Contenu |
|---|---|---|
| `Documents.csv` | {len(S.docs):,} | ventes comptoir, bons de livraison, factures client, factures fournisseur |
| `documentItemm.csv` | {len(S.items):,} | lignes de ces documents (y compris les lignes vides de mise en page des factures) |
| `Transactions.csv` | {len(S.trans):,} | une transaction par document |
| `TransactionPayments.csv`, `PaymentsList.csv` | {S.ids['tp'] - M.max['tp']:,} | paiements |
| `TresoreriePayments.csv`, `CaisseOperations.csv` | — | affectation des paiements aux caisses / comptes bancaires |
| `StockMovements.csv` | {S.ids['sm'] - M.max['sm']:,} | mouvements de stock (ventes, achats, corrections, modifications manuelles) |
| `DomainEvents.csv` | {S.ids['de'] - M.max['de']:,} | événements de trésorerie : paiements, ouvertures / fermetures de caisse, écarts |
| `ProductStocks.csv` | {len(M.t['ProductStocks.csv'].rows):,} | **état du stock au {end:%d/%m/%Y}** (remplace l'état réel pour la fin de période) |
| `comparaison_mensuelle.csv` | — | indicateurs mensuels réels et générés côte à côte (contrôle de vraisemblance) |
| `parametres_generation.json` | — | tous les paramètres appris ou supposés |

**Non générés** (inchangés, à prendre dans `fichiers/`) : les données de référence (`Produits`, `ProductBrands`,
`Barcodes`, `ProductPrices`, `Clients`, `Fournisseurs`, `CompaniesList`, `users`, `DocumentTypes`, taxes,
paramètres), ainsi que `ItemTaxes`, `DocumentsReports`, `Events`, `RelatedDocuments`, `InventaireItems` et
`Payment.csv` (doublons ou faible valeur analytique, voir le guide des données).

## Continuité avec l'export réel

- **Identifiants** : chaque table repart après le plus grand identifiant réel (documents > {M.max['doc']},
  lignes > {M.max['item']}, paiements > {M.max['pl']}, mouvements > {M.max['sm']}, événements > {M.max['de']}),
  avec la même proportion d'identifiants sautés (documents supprimés) que dans l'export.
- **Numéros** : `VC{M.number['6'] + 1}/24`, `BL{M.number['5'] + 1}/24`, `FV{M.number['1'] + 1:04d}/24`… continuent la série
  (le logiciel n'a pas remis le compteur à zéro en janvier 2025) ; les factures fournisseur continuent la
  numérotation propre à chaque fournisseur.
- **Stock** : chaque produit repart de son solde réel au 30/04/2025 ; le prix d'achat et le CUMP aussi.
- **Soldes clients / fournisseurs** (`Extra.cosld`) et **soldes des caisses** : repris de la fin de l'export.
- **Références** : produits, clients, fournisseurs, caissiers, caisses et comptes bancaires existent tous
  dans l'export réel.

## Ce qui est appris sur l'export réel

Les 24 factures client qui refacturent des bons de livraison (RelatedDocuments) sont exclues de l'apprentissage :
leur chiffre d'affaires est déjà compté sur les bons de livraison et elles sont exclues des ventes du Data Warehouse.

Volume de ventes par jour de semaine et par mois · heures d'activité de chaque type de document · nombre
de lignes, quantités et remises (par produit) · popularité de chaque produit sur chaque canal · clients de
chaque canal · liste de prix · caissier selon le jour et l'heure · taux de brouillons, de documents corrigés,
d'impayés · nombre et délai des paiements · mode de paiement · fournisseur de chaque produit, fréquence de
commande, remises et timbre de chaque fournisseur · écarts de caisse à la fermeture · modifications manuelles
de stock. Les calculs des montants reproduisent ceux du logiciel (remise ligne, remise document dans les
colonnes `Sum…`, TVA, taxe de 1 % sur certaines factures fournisseur, timbre de 1 sur `FinalPrice`).

## Hypothèses ajoutées (à citer comme telles, pas comme des découvertes)

| Hypothèse | Valeur |
|---|---|
| Calendrier | {cal_txt} |
| Fuseau horaire | Paris (heure d'été), comme le serveur de l'export : `CreatedDate` en UTC, paiements et mouvements en heure locale |
| Croissance de la fréquentation | +{GROWTH_PER_YEAR:.0%} par an |
| Mois absents de l'export (mai → sept.) | indices {ASSUMED_MONTH_INDEX[args.calendar]} (août plus calme) |
| Mars | l'export montre une baisse en mars 2025 (Ramadan) : remplacée par la moyenne février / avril |
| Saisonnalité produits | {sp['solaires']} produits solaires et {sp['anti_moustiques']} anti-moustiques repérés par mot-clé : pic en juillet |
| Épidémies | {sp['orl_immunite']} produits ORL / immunité : ventes × (1 + {EPIDEMIC_AMPLITUDE} × écart de l'incidence grippe Sentinelles à sa moyenne) {'' if M.epi_used else '(fichier absent : effet désactivé)'} |
| Cycle de vie | tendance propre à chaque produit ; {params['produits_lances']} produits du catalogue lancés, {params['produits_arretes']} arrêtés en cours de période |
| Prix | hausses le 01/09/2025 (15 % des produits, +2 à 5 %), le 01/01/2026 (60 %, +2 à 7 %), le 01/07/2026 (15 %, +1 à 4 %) |
| Achats | une facture fournisseur est créée quand des produits du fournisseur passent sous {REORDER_DAYS} jours de demande ; quantité = {TARGET_DAYS} jours de demande (un stock négatif n'est pas rattrapé) |

⚠️ Les relations météo / épidémies / saison que vos modèles trouveront sur la période générée viennent en partie
de ces hypothèses. Pour évaluer honnêtement un modèle, entraînez-le et testez-le aussi **sur la seule période réelle**.

## Utilisation avec le pipeline

- `python clean_data.py --synthetique` nettoie ces 10 fichiers avec les fichiers de référence réels (produits,
  clients, utilisateurs, noms des caisses issus du `DomainEvents.csv` réel) et écrit `cleaned/synthetique/`, sans
  jamais mélanger réel et synthétique dans un même dossier.
- `build_dataset.py` empile ensuite les deux périodes dans le Data Warehouse ; la délimitation se fait par la date.
- Contrôles passés sur les fichiers générés : clés étrangères (lignes → documents → transactions → paiements →
  trésorerie → caisse ; produits, sociétés et utilisateurs existants), `TotalTtc` = somme des lignes,
  `FinalPrice` = `TotalTtc` + timbre, montant payé = somme des paiements, identifiants et numéros uniques et
  jamais utilisés dans l'export, soldes de stock continus depuis le dernier solde réel jusqu'à `ProductStocks.csv`.

## Limites

- Pas de nouveaux produits, clients ou fournisseurs créés (le catalogue reste celui de l'export).
- Les types de documents rares (avoirs, retours, proformas, commandes) ne sont pas générés : les retours clients
  n'apparaissent que comme lignes négatives des ventes (à la fréquence réelle, surtout des échanges sur un ticket
  de plusieurs lignes), et il n'y a pas d'avoir fournisseur après le 30/04/2025.
- Un ticket ou une facture de total nul ou négatif ne crée pas de paiement, comme dans l'export (aucun paiement
  négatif) : l'argent rendu à un client n'est pas enregistré comme paiement.
- Moyen de paiement : reproduit tel qu'il est saisi dans l'export depuis novembre 2024, c'est-à-dire presque jamais
  (< 1 % des paiements clients) ; seules les premières semaines de l'export (septembre-octobre 2024) le renseignent.
- Pas de dépôts / retraits bancaires ni d'ajustements de solde bancaire (rares dans l'export).
- Les paiements saisis puis supprimés (≈ {M.p_removed:.1%}, statut 2 en caisse) sont reproduits ; les mises à jour
  de paiement (`PaymentUpdated`, 11 cas réels) ne le sont pas.
- {params['stock_negatif_fin']} produits finissent avec un stock négatif (vente sans réception : 132 dans l'export au
  30/04/2025) — c'est un défaut de qualité réel du logiciel, conservé.
- Les mois de mai à septembre n'ont jamais été observés : leur niveau repose sur les indices supposés.

## Comparaison mensuelle (réel puis généré)

{table(comp)}
"""
    (OUT / "README.md").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
