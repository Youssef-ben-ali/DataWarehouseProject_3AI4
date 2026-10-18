#!/usr/bin/env python3
"""
Présentation de la 1re validation (PowerPoint, français) – Health Retailers.
Les chiffres sont recalculés à partir de dataset/ pour rester exacts.
    python build_presentation.py   ->  ../Presentation_Validation1_HealthRetailers.pptx
"""
import csv
from collections import defaultdict
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

HERE = Path(__file__).resolve().parent
DS = HERE / "dataset"
OUT = HERE / "presentation" / "Presentation_Validation1_HealthRetailers.pptx"

NAVY, TEAL, VIOLET, AMBER = "1E3A8A", "0F766E", "6D28D9", "B45309"
INK, MUTED, LIGHT, LINE, WHITE = "0F172A", "475569", "F1F5F9", "CBD5E1", "FFFFFF"
FONT = "Calibri"


# --------------------------------------------------------------------------- #
# chiffres
# --------------------------------------------------------------------------- #
def R(rel):
    with (DS / rel).open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fr(x, d=0):
    return f"{x:,.{d}f}".replace(",", " ").replace(".", ",")


REAL_END = "20250430"          # délimitation réel / synthétique (DateKey) : version B, données sur 2 ans


def corr(a, b):
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    den = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / den if den else 0.0


def stats():
    S = {}
    sales = R("dwh/fait_ventes.csv")
    real = [s for s in sales if s["DateKey"] <= REAL_END]
    S["ca_ht"] = sum(float(s["CA_HT"]) for s in sales)
    S["ca_reel"] = sum(float(s["CA_HT"]) for s in real)
    S["docs_reel"] = len({s["Document_Id"] for s in real})
    S["panier_reel"] = S["ca_reel"] / S["docs_reel"]
    S["marge"] = sum(float(s["CA_HT"]) - float(s["Cout_HT"]) for s in sales if s["Cout_HT"])
    m = defaultdict(float)
    for s in sales:
        m[f"{s['DateKey'][:4]}-{s['DateKey'][4:6]}"] += float(s["CA_HT"])
    S["mois"] = {k: v for k, v in sorted(m.items()) if k >= "2024-10"}
    S["mois_reel"] = {k: v for k, v in S["mois"].items() if k <= REAL_END[:4] + "-" + REAL_END[4:6]}
    S["moy_mois"] = sum(S["mois_reel"].values()) / len(S["mois_reel"])
    # canal et client anonyme : informations de la zone ETL (période réelle)
    comptoir = {d["Id"] for d in R("../cleaned/documents.csv") if d["DocumentType_Id"] == "6"}
    S["comptoir_pct"] = 100 * sum(float(s["CA_HT"]) for s in real if s["Document_Id"] in comptoir) / S["ca_reel"]
    txn = R("../cleaned/transactions.csv")
    S["anonyme_pct"] = 100 * sum(t["IsWalkInCustomer"] == "true" for t in txn) / len(txn)
    stock = R("dwh/fait_stock_actuel.csv")
    sold = {s["Product_Id"] for s in sales}
    act = [a for a in stock if a["Product_Id"] in sold]
    S["rupture_actifs"] = 100 * sum(float(a["Quantity"]) == 0 for a in act) / len(act)
    prods = R("dwh/dim_produit.csv")
    S["produits"] = len(prods)
    S["sans_famille_pct"] = 100 * sum(p["Famille"] in ("NON RENSEIGNE", "NON CLASSE") for p in prods) / len(prods)
    S["fournisseurs"] = len(R("../cleaned/suppliers.csv"))
    seg = R("ml/ml_11_4_segmentation_clients.csv")
    S["clients_id"] = len(seg)
    S["clients_ca_pct"] = 100 * sum(float(c["X_CA_HT_Total"]) for c in seg) / S["ca_ht"]
    pays = [p for p in R("dwh/fait_paiements.csv") if p["EstPaiementFournisseur"] == "false" and p["DateKey"] <= REAL_END]
    S["sans_mode_pct"] = 100 * sum(p["PaymentMode_Id"] == "-1" for p in pays) / len(pays)
    S["rows"] = {p.stem: sum(1 for _ in p.open(encoding="utf-8")) - 1 for p in (DS / "dwh").glob("*.csv")}
    S["ml_rows"] = {p.stem: sum(1 for _ in p.open(encoding="utf-8")) - 1 for p in (DS / "ml").glob("*.csv")}
    ops = R("ml/ml_11_3_operations_caisse.csv")
    S["annulations"] = sum(o["Y_IsCancelled"] == "true" for o in ops)
    # premier signal ML, mesuré sur la PÉRIODE RÉELLE uniquement (§8 du cahier)
    fam = [r for r in R("ml/ml_11_1_prevision_demande_famille_hebdo.csv")
           if r["FamilyGroup"] == "COMPLEMENTS ALIMENTAIRES" and r["SemaineComplete"] == "true"
           and r["SemaineDebut"] <= "2025-04-21" and r["X_Meteo_TempMoyenne"] and r["X_Grippe_Inc100"]]   # semaines 100 % réelles
    y = [float(r["Y_Quantite"]) for r in fam]
    S["sig_n"] = len(fam)
    S["sig_temp"] = corr(y, [float(r["X_Meteo_TempMoyenne"]) for r in fam])
    S["sig_grippe"] = corr(y, [float(r["X_Grippe_Inc100"]) for r in fam])
    # volume des sources brutes
    n = 0
    for p in (HERE / "fichiers").glob("*.csv"):
        raw = p.read_bytes()
        try:
            t = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            t = raw.decode("cp1252", errors="replace")
        first = t.split("\n", 1)[0]
        n += sum(1 for _ in csv.reader(t.splitlines()[1:], delimiter=";" if first.count(";") > first.count(",") else ","))
    S["records"] = n
    return S


# --------------------------------------------------------------------------- #
# helpers de mise en page
# --------------------------------------------------------------------------- #
def rgb(h):
    return RGBColor.from_string(h)


def nb(s):
    """Typographie française : espace insécable avant ? ! ; : % et après «, avant »."""
    for a, b in ((" ?", " ?"), (" !", " !"), (" ;", " ;"), (" :", " :"), (" %", " %"),
                 ("« ", "« "), (" »", " »")):
        s = s.replace(a, b)
    return s


def text(slide, x, y, w, h, paras, size=16, color=INK, bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP,
         space=6):
    """paras : liste de str ou de (str, dict(options)) ; une str commençant par '• ' devient une puce."""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.05)
    for i, p in enumerate(paras if isinstance(paras, list) else [paras]):
        opt = {}
        if isinstance(p, tuple):
            p, opt = p
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.alignment = opt.get("align", align)
        para.space_after = Pt(opt.get("space", space))
        bullet = p.startswith("• ")
        if bullet:
            r0 = para.add_run()
            r0.text = "▪  "
            r0.font.size = Pt(opt.get("size", size) - 2)
            r0.font.color.rgb = rgb(opt.get("bcolor", NAVY))
            r0.font.name = FONT
            p = p[2:]
        # **gras** inline
        parts = p.split("**")
        for j, part in enumerate(parts):
            if not part:
                continue
            r = para.add_run()
            r.text = nb(part)
            r.font.name = FONT
            r.font.size = Pt(opt.get("size", size))
            r.font.bold = opt.get("bold", bold) or (j % 2 == 1)
            r.font.color.rgb = rgb(opt.get("color", color))
    return tb


def box(slide, x, y, w, h, fill=LIGHT, line=None, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08, dash=False):
    s = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    if fill:
        s.fill.solid()
        s.fill.fore_color.rgb = rgb(fill)
    else:
        s.fill.background()
    if line:
        s.line.color.rgb = rgb(line)
        s.line.width = Pt(1.25)
        if dash:
            from pptx.enum.dml import MSO_LINE_DASH_STYLE
            s.line.dash_style = MSO_LINE_DASH_STYLE.DASH
    else:
        s.line.fill.background()
    s.shadow.inherit = False
    s.text_frame.text = ""
    return s


def boxtext(slide, x, y, w, h, paras, fill=LIGHT, line=None, size=14, color=INK, align=PP_ALIGN.LEFT,
            anchor=MSO_ANCHOR.MIDDLE, pad=0.12, dash=False, bold=False, shape=MSO_SHAPE.ROUNDED_RECTANGLE):
    box(slide, x, y, w, h, fill, line, dash=dash, shape=shape)
    return text(slide, x + pad, y + 0.04, w - 2 * pad, h - 0.08, paras, size=size, color=color, align=align,
                anchor=anchor, bold=bold, space=3)


def line(slide, x1, y1, x2, y2, color=LINE, width=1.5):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = rgb(color)
    c.line.width = Pt(width)
    return c


def table(slide, x, y, w, rows, widths, size=11, head_fill=NAVY, row_h=0.36, first_bold=True):
    shp = slide.shapes.add_table(len(rows), len(rows[0]), Inches(x), Inches(y), Inches(w), Inches(row_h * len(rows)))
    t = shp.table
    for i, wd in enumerate(widths):
        t.columns[i].width = Inches(wd)
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            cell = t.cell(r, c)
            cell.margin_left = cell.margin_right = Inches(0.07)
            cell.margin_top = cell.margin_bottom = Inches(0.04)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.fill.solid()
            cell.fill.fore_color.rgb = rgb(head_fill if r == 0 else (WHITE if r % 2 else "F8FAFC"))
            tf = cell.text_frame
            tf.word_wrap = True
            lines_ = str(val).split("\n")
            for k, ln in enumerate(lines_):
                p = tf.paragraphs[0] if k == 0 else tf.add_paragraph()
                parts = ln.split("**")
                for j, part in enumerate(parts):
                    if not part:
                        continue
                    run = p.add_run()
                    run.text = nb(part)
                    run.font.name = FONT
                    run.font.size = Pt(size)
                    run.font.bold = r == 0 or (first_bold and c == 0) or j % 2 == 1
                    run.font.color.rgb = rgb(WHITE if r == 0 else INK)
    return t


class Deck:
    def __init__(self):
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = Inches(13.333), Inches(7.5)
        self.n = 0

    def slide(self, title=None, section=None, notes=""):
        s = self.prs.slides.add_slide(self.prs.slide_layouts[6])
        self.n += 1
        if title:
            box(s, 0, 0, 13.333, 0.12, NAVY, shape=MSO_SHAPE.RECTANGLE)
            if section:
                text(s, 0.55, 0.3, 9, 0.35, section.upper(), size=12, color=TEAL, bold=True)
            text(s, 0.55, 0.58, 12.2, 0.75, title, size=27, color=NAVY, bold=True)
            text(s, 0.55, 7.0, 8, 0.3, "Health Retailers · Projet Data Engineering · Validation 1", size=10, color=MUTED)
            text(s, 11.8, 7.0, 1.0, 0.3, str(self.n), size=10, color=MUTED, align=PP_ALIGN.RIGHT)
        if notes:
            s.notes_slide.notes_text_frame.text = notes
        return s


# --------------------------------------------------------------------------- #
# diapositives
# --------------------------------------------------------------------------- #
def build(S):
    d = Deck()
    mois_fr = {"01": "janv.", "02": "févr.", "03": "mars", "04": "avr.", "05": "mai", "06": "juin", "07": "juil.",
               "08": "août", "09": "sept.", "10": "oct.", "11": "nov.", "12": "déc."}

    # 1. Titre ------------------------------------------------------------------
    s = d.slide(notes="Présenter l'équipe et le sujet : le projet Health Retailers consiste à construire une plateforme "
                      "décisionnelle (Data Warehouse, BI et Machine Learning) à partir des données transactionnelles "
                      "réelles d'un drugstore. Annoncer le plan en 4 points demandés pour cette validation.")
    box(s, 0, 0, 13.333, 7.5, NAVY, shape=MSO_SHAPE.RECTANGLE)
    box(s, 0, 5.15, 13.333, 0.06, TEAL, shape=MSO_SHAPE.RECTANGLE)
    text(s, 0.9, 1.5, 11.5, 0.5, "PROJET DATA ENGINEERING · CLASSE 3IA", size=16, color="99F6E4", bold=True)
    text(s, 0.9, 2.05, 11.5, 1.2, "Health Retailers", size=60, color=WHITE, bold=True)
    text(s, 0.9, 3.3, 11.5, 1.0, "Plateforme décisionnelle BI & Machine Learning pour un drugstore", size=26, color="E0E7FF")
    text(s, 0.9, 5.5, 11.5, 0.5, "Première validation du projet — modèle révisé (version B)", size=18, color=WHITE, bold=True)
    text(s, 0.9, 6.0, 11.5, 0.5, "Équipe : [Nom du groupe] — [Membre 1], [Membre 2], [Membre 3], [Membre 4]",
         size=16, color="CBD5E1")

    # 2. Sommaire ---------------------------------------------------------------
    s = d.slide("Plan de la présentation", notes="Suivre exactement les 4 points demandés, puis conclure sur les "
                "limites identifiées et les prochaines étapes. Durée visée : 15 à 18 minutes.")
    items = [("1", "Business Understanding", "Contexte métier, données disponibles et problématique"),
             ("2", "Objectifs du projet", "Objectif global → sous-objectifs métier → objectifs techniques BI / ML"),
             ("3", "Méthodologie de travail", "Démarche adoptée pour la préparation des données, la BI et le ML"),
             ("4", "Modèle du Data Warehouse", "Tables de faits, dimensions et mesures"),
             ("5", "Limites et prochaines étapes", "Ce qui reste à valider et à réaliser")]
    for i, (n, t, sub) in enumerate(items):
        y = 1.65 + i * 1.02
        boxtext(s, 0.9, y, 0.8, 0.8, [(n, {"align": PP_ALIGN.CENTER})], fill=NAVY if i < 4 else MUTED, size=26,
                color=WHITE, bold=True)
        text(s, 1.95, y + 0.02, 10, 0.45, t, size=22, color=INK, bold=True)
        text(s, 1.95, y + 0.45, 10, 0.4, sub, size=15, color=MUTED)

    # 3. Contexte ---------------------------------------------------------------
    s = d.slide("Un drugstore qui produit beaucoup de données… peu exploitées", "1 · Business Understanding",
                notes="Contexte : transformation digitale du secteur santé & bien-être. Le drugstore enregistre chaque "
                      "jour ses ventes, achats, stocks et paiements dans un logiciel de gestion. Nous disposons d'un export "
                      f"de 29 fichiers CSV (~{fr(S['records'])} enregistrements) couvrant 7 mois, que nous avons prolongé à 2 ans par "
                      "des données synthétiques documentées. Ces données ne sont aujourd'hui pas exploitées pour piloter l'activité.")
    text(s, 0.55, 1.55, 6.6, 4.9, [
        "• **Activité :** drugstore / parapharmacie situé en France – hygiène, beauté, compléments alimentaires, accessoires.",
        "• **Système opérationnel :** un logiciel de caisse et de gestion enregistre ventes comptoir, factures clients, "
        "achats fournisseurs, paiements, caisses et mouvements de stock.",
        "• **Enjeu du secteur :** avec la transformation digitale, la donnée transactionnelle devient un levier pour "
        "améliorer la performance commerciale et opérationnelle.",
        "• **Source fournie :** un export brut de la base du logiciel – 29 fichiers CSV, du 30/09/2024 au 30/04/2025.",
        "• **Prolongation :** données synthétiques générées jusqu'au 29/09/2026 (2 ans au total), rangées à part comme "
        "donnée externe ; délimitation par la date.",
    ], size=16, space=10)
    tiles = [(fr(S["records"]), "enregistrements bruts\ndans 29 fichiers CSV"),
             (fr(S["ca_reel"] / 1e6, 2) + " M", "de chiffre d'affaires HT\nsur les 7 mois réels"),
             (fr(S["docs_reel"]), "ventes réelles (documents)\npanier moyen " + fr(S["panier_reel"], 0) + " HT"),
             (fr(S["produits"]), "produits référencés\n" + fr(S["fournisseurs"]) + " fournisseurs")]
    for i, (v, lab) in enumerate(tiles):
        x, y = 7.55 + (i % 2) * 2.75, 1.6 + (i // 2) * 2.45
        box(s, x, y, 2.55, 2.2, LIGHT)
        text(s, x + 0.15, y + 0.25, 2.25, 0.8, v, size=30, color=NAVY, bold=True)
        text(s, x + 0.15, y + 1.1, 2.3, 1.0, lab.split("\n"), size=13, color=MUTED, space=1)
    text(s, 7.55, 6.5, 5.3, 0.35, "Montants exprimés dans la devise du logiciel source.", size=11, color=MUTED)

    # 4. Activité (graphique) ---------------------------------------------------
    s = d.slide(f"Un CA HT d'environ {fr(S['moy_mois'] / 1000)} k par mois, porté par le comptoir",
                "1 · Business Understanding",
                notes="Premier regard sur l'activité, calculé à partir de notre Data Warehouse. En bleu foncé les 7 mois "
                      "réels, en clair la prolongation synthétique. Le CA mensuel réel est assez "
                      "stable avec un creux en mars. La vente comptoir domine et la grande majorité des transactions "
                      "concernent un client anonyme : cela limite l'analyse client, ce qui a guidé nos choix d'objectifs.")
    cd = CategoryChartData()
    keys = list(S["mois"].keys())
    cd.categories = [f"{mois_fr[k[5:]]} {k[2:4]}" for k in keys]
    cd.add_series("CA HT", [round(v) for v in S["mois"].values()])
    gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.55), Inches(1.5), Inches(7.6), Inches(5.0), cd)
    ch = gf.chart
    ch.has_legend = False
    ch.has_title = True
    ch.chart_title.text_frame.text = "CA HT mensuel — réel (oct. 2024 – avr. 2025) puis synthétique (mai 2025 – sept. 2026)"
    tr = ch.chart_title.text_frame.paragraphs[0].runs[0]
    tr.font.size, tr.font.bold, tr.font.name = Pt(14), True, FONT
    tr.font.color.rgb = rgb(INK)
    plot = ch.plots[0]
    plot.gap_width = 70
    ser = plot.series[0]
    ser.format.fill.solid()
    ser.format.fill.fore_color.rgb = rgb(NAVY)
    for idx, k in enumerate(keys):                       # période synthétique en couleur claire
        if k not in S["mois_reel"]:
            pt = ser.points[idx]
            pt.format.fill.solid()
            pt.format.fill.fore_color.rgb = rgb("A5B4FC")
    va = ch.value_axis
    va.has_major_gridlines = True
    va.major_gridlines.format.line.color.rgb = rgb("E2E8F0")
    va.format.line.fill.background()
    va.tick_labels.font.size = Pt(11)
    va.tick_labels.font.color.rgb = rgb(MUTED)
    va.tick_labels.number_format = '#,##0'
    va.tick_labels.number_format_is_linked = False
    ca = ch.category_axis
    ca.tick_labels.font.size = Pt(12)
    ca.tick_labels.font.color.rgb = rgb(INK)
    ca.format.line.color.rgb = rgb(LINE)
    vals = list(S["mois"].values())
    rvals = list(S["mois_reel"].values())
    for idx in (rvals.index(max(rvals)), rvals.index(min(rvals))):
        dl = ser.points[idx].data_label
        dl.position = XL_LABEL_POSITION.OUTSIDE_END
        dl.text_frame.text = f"{fr(vals[idx] / 1000)} k"
        r = dl.text_frame.paragraphs[0].runs[0]
        r.font.size, r.font.bold, r.font.name = Pt(12), True, FONT
        r.font.color.rgb = rgb(INK)
    low = keys[rvals.index(min(rvals))]
    text(s, 0.55, 6.55, 7.6, 0.35, "Bleu foncé : réel · bleu clair : synthétique. Septembre 2024 exclu (un seul jour d'activité).",
         size=11, color=MUTED)
    ins = [(f"{fr(S['comptoir_pct'])} %", "du CA HT est réalisé en vente comptoir ; le reste via bons de livraison et factures."),
           (f"{fr(S['anonyme_pct'])} %", "des transactions sont rattachées à un client comptoir anonyme : peu de clients identifiés."),
           (f"{mois_fr[low[5:]].capitalize()} {low[:4]}", "est le mois le plus faible : la saisonnalité reste à expliquer.")]
    for i, (v, t) in enumerate(ins):
        y = 1.6 + i * 1.65
        box(s, 8.55, y, 4.25, 1.45, LIGHT)
        text(s, 8.75, y + 0.12, 3.9, 0.55, v, size=24, color=TEAL, bold=True)
        text(s, 8.75, y + 0.68, 3.9, 0.75, t, size=13, color=INK)

    # 5. Problématique ----------------------------------------------------------
    s = d.slide("Problématique : des données riches mais non exploitables en l'état", "1 · Business Understanding",
                notes="Le profilage des 29 fichiers a révélé quatre familles de problèmes. Insister sur le double comptage "
                      "factures / bons de livraison : sans traitement, le CA serait surestimé. Conclure par la question "
                      "à laquelle le projet répond.")
    cards = [("Données dispersées", ["29 fichiers, 2 séparateurs, 3 encodages", "Dates au format US et FR mélangées",
                                     "JSON et HTML stockés dans des colonnes"]),
             ("Qualité inégale", ["91 codes produits détruits par Excel", "Noms anonymisés incohérents entre fichiers",
                                  "Inventaire physique jamais finalisé"]),
             ("Pièges métier", ["24 factures refacturent 864 bons de livraison → CA compté deux fois",
                                f"{fr(S['anonyme_pct'])} % de transactions anonymes"]),
             ("Aucune vision consolidée", ["Pas d'indicateurs de pilotage",
                                           f"{fr(S['rupture_actifs'])} % des produits actifs en rupture",
                                           "Aucune anticipation de la demande"])]
    for i, (t, items_) in enumerate(cards):
        x = 0.55 + i * 3.1
        box(s, x, 1.55, 2.9, 3.05, LIGHT, shape=MSO_SHAPE.RECTANGLE)
        box(s, x, 1.55, 2.9, 0.09, AMBER, shape=MSO_SHAPE.RECTANGLE)
        text(s, x + 0.18, 1.75, 2.6, 0.45, t, size=17, color=INK, bold=True)
        text(s, x + 0.18, 2.3, 2.6, 2.3, ["• " + it for it in items_], size=13, space=6)
    boxtext(s, 0.55, 4.9, 12.25, 1.7, [
        ("PROBLÉMATIQUE", {"size": 12, "color": "99F6E4", "bold": True}),
        ("Comment transformer les données transactionnelles brutes du drugstore en une plateforme décisionnelle "
         "fiable, qui permette aux responsables de piloter les ventes, les stocks, les clients et la caisse, "
         "et d'anticiper la demande ?", {"size": 19, "color": WHITE}),
    ], fill=NAVY, pad=0.35)

    # 6. Décideurs ----------------------------------------------------------------
    s = d.slide("Cinq décideurs, des questions concrètes", "1 · Business Understanding",
                notes="Démarche du cahier de spécification : partir des décideurs et de leurs questions, pas des tables. "
                      "Chaque question sera reliée à un KPI, une formule et une source de données.")
    table(s, 0.55, 1.55, 12.25, [
        ["Décideur", "Objectif métier", "Questions analytiques principales"],
        ["Direction générale", "Suivre la performance globale", "Quel est le CA ? Comment évolue-t-il ? Quelle période génère le plus de CA ?"],
        ["Responsable commercial", "Analyser les ventes", "Quels produits et marques se vendent le plus et sont les plus rentables ? Quel panier moyen ?"],
        ["Responsable relation client", "Analyser les clients", "Quels clients sont actifs ? Quelle est leur fréquence d'achat et leur valeur ?"],
        ["Resp. approvisionnement / stock", "Piloter les stocks", "Quels produits sont en rupture ou en stock faible ? Quelle demande anticiper ?"],
        ["Responsable financier / caisse", "Suivre les flux de paiement", "Quel montant est encaissé ? Par quel moyen ? Comment évoluent les encaissements ?"],
    ], [3.0, 2.9, 6.35], size=14, row_h=0.72)

    # 7. Objectifs : arbre -------------------------------------------------------
    s = d.slide("Objectifs : de l'objectif global aux objectifs techniques", "2 · Objectifs du projet",
                notes="Lecture de haut en bas : un objectif global, décliné en cinq sous-objectifs métier, chacun relié à "
                      "un objectif technique de visualisation (BI, en vert) et, quand c'est pertinent, de Machine Learning "
                      "(en violet). La performance commerciale est entièrement couverte par la BI.")
    boxtext(s, 1.9, 1.45, 9.5, 0.82, [("OBJECTIF GLOBAL", {"size": 11, "color": "BFDBFE", "bold": True}),
                                      ("Doter le drugstore d'une plateforme décisionnelle (DWH + BI + ML) pour piloter "
                                       "et anticiper son activité commerciale et opérationnelle", {"size": 15, "color": WHITE, "bold": True})],
            fill=NAVY, align=PP_ALIGN.CENTER)
    subs = [("Piloter la performance commerciale", "Dashboards Synthèse & Commercial", None),
            ("Optimiser les stocks et l'approvisionnement", "Dashboard Stock : stock disponible, ruptures, stock faible", "Prévision de la demande hebdomadaire"),
            ("Connaître et fidéliser les clients", "Dashboard Clients : actifs, fréquence, panier", "Segmentation des clients"),
            ("Protéger la marge", "Marge HT par produit, famille et marque (dashboard Commercial)", "Détection d'anomalies sur les ventes"),
            ("Sécuriser la caisse et les paiements", "Dashboard Paiements & caisse", "Détection d'anomalies de caisse")]
    cw, gap, x0 = 2.35, 0.125, 0.55
    line(s, 6.65, 2.27, 6.65, 2.5, color=MUTED)
    line(s, x0 + cw / 2, 2.5, x0 + 4 * (cw + gap) + cw / 2, 2.5, color=MUTED)
    for i, (so, bi, ml) in enumerate(subs):
        x = x0 + i * (cw + gap)
        line(s, x + cw / 2, 2.5, x + cw / 2, 2.7, color=MUTED)
        boxtext(s, x, 2.7, cw, 1.0, [(f"SO{i + 1}", {"size": 11, "color": NAVY, "bold": True}), (so, {"size": 13, "bold": True})],
                fill="DBEAFE", align=PP_ALIGN.CENTER)
        line(s, x + cw / 2, 3.7, x + cw / 2, 3.95, color=MUTED)
        boxtext(s, x, 3.95, cw, 1.2, [("BI · VISUALISATION", {"size": 10, "color": "CCFBF1", "bold": True}),
                                      (bi, {"size": 12.5, "color": WHITE})], fill=TEAL, align=PP_ALIGN.CENTER)
        line(s, x + cw / 2, 5.15, x + cw / 2, 5.35, color=MUTED)
        if ml:
            boxtext(s, x, 5.35, cw, 1.2, [("ML · MACHINE LEARNING", {"size": 10, "color": "EDE9FE", "bold": True}),
                                          (ml, {"size": 12.5, "color": WHITE})], fill=VIOLET, align=PP_ALIGN.CENTER)
        else:
            boxtext(s, x, 5.35, cw, 1.2, [("ML", {"size": 10, "color": MUTED, "bold": True}),
                                          ("Besoin couvert par la BI", {"size": 12.5, "color": MUTED})],
                    fill=WHITE, line=LINE, dash=True, align=PP_ALIGN.CENTER)

    # 8. Objectifs : détail ------------------------------------------------------
    s = d.slide("Objectifs techniques détaillés : KPI et cas de Machine Learning", "2 · Objectifs du projet",
                notes="Pour chaque sous-objectif : les KPI du tableau de bord et le cas ML avec son type de problème et "
                      "sa cible. Les formules des KPI viennent du cahier de spécification (§6 et §12).")
    table(s, 0.55, 1.5, 12.25, [
        ["Sous-objectif métier", "Objectif technique BI (KPI / reporting)", "Objectif technique ML (type · cible)"],
        ["SO1 · Performance commerciale", "CA HT, croissance %, nb de ventes, panier moyen,\ntop produits et marques par période", "—"],
        ["SO2 · Stocks et approvisionnement", "Stock disponible, produits en rupture,\nproduits en stock faible", "**Prévision de la demande** · régression / séries temporelles\nY = quantité vendue la semaine suivante, par famille / marque"],
        ["SO3 · Clients", "Clients actifs, fréquence d'achat, panier client,\nCA par client et par type (B2B / particulier)", "**Segmentation** · clustering non supervisé\npas de cible : groupes de clients homogènes"],
        ["SO4 · Marge", "Marge HT = CA HT − coût HT, calculée comme mesure\npar produit, famille, marque et période", "**Détection d'anomalies sur les ventes** · non supervisé\nliste des lignes de vente à contrôler"],
        ["SO5 · Caisse et paiements", "Montant encaissé, nombre de paiements,\npar moyen de paiement et par période", "**Détection d'anomalies de caisse** · anomalies / classification\nY = opération annulée (oui / non)"],
    ], [3.0, 4.35, 4.9], size=13, row_h=0.86)

    # 9. Méthodologie globale ---------------------------------------------------
    s = d.slide("Une démarche itérative, inspirée de CRISP-DM", "3 · Méthodologie de travail",
                notes="Le cahier de spécification a fixé les besoins. Nous avons profilé chaque fichier, puis nettoyé les "
                      "données avec un script Python reproductible, construit le Data Warehouse et les jeux de données ML. "
                      "Principe directeur : une donnée n'est intégrée que si elle répond à une question métier.")
    steps = [("1", "Compréhension\nmétier", "Cahier de spécification"), ("2", "Profilage\ndes 29 CSV", "Clés, formats, qualité"),
             ("3", "Nettoyage", "clean_data.py"), ("4", "Modélisation\n& ETL DWH", "build_dataset.py"),
             ("5", "BI", "Dashboards Power BI"), ("6", "Machine\nLearning", "Python · scikit-learn"),
             ("7", "Restitution", "Validation métier")]
    w, step = 1.55, 1.77
    for i, (n, t, sub) in enumerate(steps):
        x = 0.55 + i * step
        fill = TEAL if t == "BI" else VIOLET if "Machine" in t else NAVY
        boxtext(s, x, 1.6, w, 1.2, [(n, {"size": 12, "color": "C7D2FE", "bold": True}),
                                    (t.replace("\n", " "), {"size": 14, "color": WHITE, "bold": True})],
                fill=fill, align=PP_ALIGN.CENTER, pad=0.08)
        if i < len(steps) - 1:
            a = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x + w + 0.03), Inches(2.08), Inches(0.16), Inches(0.24))
            a.fill.solid()
            a.fill.fore_color.rgb = rgb(MUTED)
            a.line.fill.background()
        text(s, x - 0.05, 2.9, w + 0.1, 0.6, sub, size=12, color=MUTED, align=PP_ALIGN.CENTER)
    layers = [("Sources", "29 CSV réels + données synthétiques", LIGHT, INK),
              ("Données nettoyées", "formats unifiés · réel et synthétique", LIGHT, INK),
              ("Data Warehouse", "4 dimensions · 3 tables de faits", "DBEAFE", NAVY),
              ("Jeux de données ML", "6 fichiers · variables X_ / cible Y_", "EDE9FE", VIOLET),
              ("Restitution", "Dashboards · modèles · alertes", "CCFBF1", TEAL)]
    text(s, 0.55, 3.75, 12, 0.4, "Flux des données", size=15, color=INK, bold=True)
    for i, (t, sub, fill, col) in enumerate(layers):
        x = 0.55 + i * 2.5
        boxtext(s, x, 4.25, 2.2, 1.35, [(t, {"size": 15, "bold": True, "color": col}), (sub, {"size": 12, "color": MUTED})],
                fill=fill, align=PP_ALIGN.CENTER)
        if i < 4:
            a = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Inches(x + 2.22), Inches(4.78), Inches(0.26), Inches(0.3))
            a.fill.solid()
            a.fill.fore_color.rgb = rgb(LINE)
            a.line.fill.background()
    text(s, 0.55, 5.9, 12.2, 0.8, ["• Scripts Python reproductibles : chaque étape se relance en une commande ; les fichiers "
                                   "originaux ne sont jamais modifiés.",
                                   "• Données externes : météo (Open-Meteo) et épidémies (réseau Sentinelles), réservées à la "
                                   "prévision ML ; calendrier français calculé ; prolongation synthétique à 2 ans."], size=13, space=3)

    # 10. Préparation des données -----------------------------------------------
    s = d.slide("Préparation des données : fiabiliser avant d'analyser", "3 · Méthodologie de travail",
                notes="Exemples concrets du nettoyage. Le point clé pour la BI : les 24 factures qui refacturent des bons "
                      "de livraison sont exclues, sinon le CA est compté deux fois. Toutes les règles sont documentées "
                      "dans un rapport de nettoyage et un fichier de contrôles qualité.")
    cols = [("Standardiser", NAVY, ["Encodages réparés (UTF-8, Windows-1252, DOS 850)", "Dates US et FR détectées colonne par colonne → ISO",
                                    "Décimales, booléens VRAI/FAUX, séparateurs unifiés", "Noms de colonnes d'origine conservés"]),
            ("Réparer et relier", TEAL, ["Fichier DomainEvents mal formé reconstruit", "91 codes produits corrompus par Excel identifiés",
                                         "4 475 produits reliés à leur identifiant via le journal d'événements",
                                         "HTML et JSON extraits en colonnes exploitables"]),
            ("Appliquer les règles métier", AMBER, ["24 factures refacturant 864 BL exclues (double comptage)",
                                                    "Documents brouillons et lignes de commentaire exclus",
                                                    "Retours et avoirs comptés en négatif",
                                                    "Mots de passe et e-mails supprimés (RGPD)"])]
    for i, (t, col, items_) in enumerate(cols):
        x = 0.55 + i * 4.15
        box(s, x, 1.55, 3.95, 4.15, LIGHT, shape=MSO_SHAPE.RECTANGLE)
        box(s, x, 1.55, 0.09, 4.15, col, shape=MSO_SHAPE.RECTANGLE)
        text(s, x + 0.3, 1.7, 3.5, 0.5, t, size=18, color=col, bold=True)
        text(s, x + 0.3, 2.3, 3.5, 3.3, ["• " + it for it in items_], size=14, space=9)
    text(s, 0.55, 5.95, 12.2, 0.7, "Contrôles qualité du cahier (§7.1) : unicité des clés, intégrité référentielle "
         "documents → lignes → produits, valeurs aberrantes, dates exploitables – résultats tracés dans controles_qualite.csv.",
         size=13, color=MUTED)

    # 11. Méthodologie BI ---------------------------------------------------------
    s = d.slide("Partie BI : une démarche Kimball, du besoin au tableau de bord", "3 · Méthodologie de travail",
                notes="Démarche Kimball : on part du besoin du décideur, on définit le KPI et sa formule, puis la "
                      "granularité, les dimensions et les faits. L'ETL est en Python, le chargement dans PostgreSQL "
                      "(script SQL généré), la restitution dans Power BI avec cinq tableaux de bord.")
    steps = ["Besoin du\ndécideur", "KPI et\nformule", "Granularité", "Dimensions\net faits", "ETL Python", "PostgreSQL", "Power BI"]
    for i, t in enumerate(steps):
        x = 0.55 + i * 1.77
        boxtext(s, x, 1.55, 1.6, 0.95, [(t.replace("\n", " "), {"size": 13, "bold": True, "color": TEAL if i >= 6 else NAVY})],
                fill="CCFBF1" if i >= 6 else "DBEAFE", align=PP_ALIGN.CENTER)
        if i < 6:
            line(s, x + 1.6, 2.02, x + 1.77, 2.02, color=MUTED, width=2)
    table(s, 0.55, 2.85, 7.3, [
        ["Dashboard", "Contenu principal"],
        ["Synthèse", "CA, nombre de ventes, panier moyen, évolution"],
        ["Commercial", "CA, quantités et marge HT par produit, marque, famille, période"],
        ["Stock", "Stock disponible, produits en rupture, produits en stock faible"],
        ["Clients", "Clients actifs, fréquence, valeur, type de client"],
        ["Paiements", "Montant encaissé, nombre de paiements, par moyen et période"],
    ], [2.2, 5.1], size=13, row_h=0.52)
    boxtext(s, 8.2, 2.85, 4.6, 3.12, [
        ("Formules clés (cahier §6 et §12)", {"size": 14, "bold": True, "color": NAVY}),
        ("CA HT = SUM(CA_HT) · Marge HT = CA HT − Coût HT", {"size": 13}),
        ("Croissance = (CA N − CA N-1) / CA N-1 × 100", {"size": 13}),
        ("Panier moyen = CA / Nb de documents", {"size": 13}),
        ("Rupture : Quantity = 0 · stock faible : 0 < Quantity ≤ seuil", {"size": 13}),
        ("Filtres minimum : période, produit, marque", {"size": 13, "color": MUTED}),
    ], fill=LIGHT, anchor=MSO_ANCHOR.TOP, pad=0.25)

    # 12. Méthodologie ML ---------------------------------------------------------
    s = d.slide("Partie ML : quatre cas d'usage, une démarche commune", "3 · Méthodologie de travail",
                notes="Démarche commune : préparation d'un jeu de données dédié (variables X_ séparées de la cible Y_), "
                      "modèle de référence simple, puis modèles plus avancés, évaluation adaptée au type de problème. "
                      "Premier signal, mesuré sur la seule période réelle comme l'exige le cahier : les ventes de "
                      "compléments alimentaires sont corrélées à la température et à la grippe. À confirmer par la "
                      "comparaison du modèle avec et sans ces variables.")
    ml = [("Prévision de la demande", "Régression · séries temporelles",
           f"{fr(S['ml_rows']['ml_11_1_prevision_demande_famille_hebdo'])} semaines × famille",
           "X : historique (lags), prix, remise, canal, fériés, météo, épidémies",
           "Référence naïve → SARIMA / Prophet → XGBoost", "Validation temporelle · MAE / RMSE"),
          ("Anomalies sur les ventes", "Non supervisé",
           f"{fr(S['ml_rows']['ml_11_2_anomalies_ventes'])} lignes de vente",
           "X : remise, écart prix / coût moyen, quantité atypique, vendeur, heure",
           "Isolation Forest · LOF", "Contrôle par règles métier et revue manuelle"),
          ("Anomalies de caisse", "Anomalies · classification",
           f"{fr(S['ml_rows']['ml_11_3_operations_caisse'])} opérations · {fr(S['ml_rows']['ml_11_3_ecarts_caisse'])} écarts",
           f"X : montant, utilisateur, heure, taux d'annulation ; Y : annulation ({fr(S['annulations'])} cas)",
           "Isolation Forest · Random Forest pondéré", "Précision / rappel (classes déséquilibrées)"),
          ("Segmentation des clients", "Clustering",
           f"{S['clients_id']} clients identifiés ({fr(S['clients_ca_pct'])} % du CA)",
           "X : CA, fréquence, panier, ancienneté, récence, B2B / particulier",
           "Log + standardisation → K-Means / CAH", "Silhouette, méthode du coude, profils métier")]
    for i, (t, typ, data, x_, model, ev) in enumerate(ml):
        x = 0.55 + i * 3.1
        box(s, x, 1.5, 2.95, 4.5, LIGHT, shape=MSO_SHAPE.RECTANGLE)
        box(s, x, 1.5, 2.95, 0.09, VIOLET, shape=MSO_SHAPE.RECTANGLE)
        text(s, x + 0.18, 1.68, 2.65, 0.5, t, size=16, color=VIOLET, bold=True)
        text(s, x + 0.18, 2.18, 2.65, 0.35, typ, size=12, color=MUTED, bold=True)
        text(s, x + 0.18, 2.6, 2.65, 3.9, [("Données", {"size": 11, "color": MUTED, "bold": True}), (data, {"size": 13}),
                                          ("Variables", {"size": 11, "color": MUTED, "bold": True}), (x_, {"size": 13}),
                                          ("Modèles", {"size": 11, "color": MUTED, "bold": True}), (model, {"size": 13}),
                                          ("Évaluation", {"size": 11, "color": MUTED, "bold": True}), (ev, {"size": 13})],
             space=2)
    boxtext(s, 0.55, 6.15, 12.25, 0.6, [(f"Premier signal (période réelle, {S['sig_n']} semaines) : ventes de compléments "
                                         f"alimentaires corrélées à la température ({fr(S['sig_temp'], 2)}) et à la grippe "
                                         f"({'+' if S['sig_grippe'] >= 0 else ''}{fr(S['sig_grippe'], 2)}) — candidates, à valider.",
                                         {"size": 13, "color": VIOLET, "bold": True})],
            fill="EDE9FE", pad=0.2)

    # 13. DWH : schéma ------------------------------------------------------------
    s = d.slide("Modèle du Data Warehouse : une constellation de faits", "4 · Modèle du Data Warehouse",
                notes="Trois tables de faits (ventes, stock actuel, paiements) partagent quatre dimensions conformes "
                      "(temps, produit, client, paiement) : une constellation réduite au strict besoin du cahier. "
                      "Chaque trait relie une clé étrangère (N) à la clé primaire d'une dimension (1). Toutes les clés "
                      "étrangères ont été vérifiées : 100 % retrouvent leur dimension.")
    img = DS / "schema" / "schema_dwh_diagramme.png"
    s.shapes.add_picture(str(img), Inches(2.55), Inches(1.4), height=Inches(5.5))
    text(s, 0.4, 2.0, 1.9, 4.0, [("3", {"size": 34, "color": NAVY, "bold": True}), ("tables de faits", {"size": 13, "color": MUTED}),
                                 ("4", {"size": 34, "color": NAVY, "bold": True}), ("dimensions", {"size": 13, "color": MUTED}),
                                 ("100 %", {"size": 34, "color": TEAL, "bold": True}),
                                 ("des clés étrangères vérifiées", {"size": 13, "color": MUTED})], space=2)

    # 13 bis. Zoom sur l'étoile des ventes -------------------------------------------
    s = d.slide("Zoom : l'étoile des ventes, cœur du modèle", "4 · Modèle du Data Warehouse",
                notes="La table de faits des ventes et ses trois dimensions. Le grain est une ligne de produit vendue dans un "
                      "document à une date. Les mesures sont additives et signées. Les clés étrangères pointent chacune "
                      "vers la clé primaire d'une dimension (relation N vers 1).")

    def card(x, y, w, title, rows, head, h=None):
        h = h or 0.42 + 0.3 * len(rows) + 0.12
        box(s, x, y, w, h, WHITE, line=head, shape=MSO_SHAPE.RECTANGLE)
        box(s, x, y, w, 0.42, head, shape=MSO_SHAPE.RECTANGLE)
        text(s, x + 0.1, y + 0.03, w - 0.2, 0.36, title, size=14, color=WHITE, bold=True, anchor=MSO_ANCHOR.MIDDLE)
        for k, (col, tag) in enumerate(rows):
            yy = y + 0.47 + k * 0.3
            colr = "B91C1C" if tag.startswith("PK") else "1D4ED8" if tag.startswith("FK") else MUTED if tag == "Power BI" else INK
            text(s, x + 0.1, yy, w - 1.1, 0.3, col, size=12, color=colr, bold=bool(tag) and tag != "mesure")
            if tag:
                text(s, x + w - 1.15, yy, 1.05, 0.3, tag, size=10, color="059669" if tag == "mesure" else colr,
                     bold=True, align=PP_ALIGN.RIGHT)
        return h

    fx, fy, fw = 4.75, 1.45, 3.85
    # ordre des FK = ordre vertical des dimensions à gauche / à droite → aucun trait ne se croise
    fact_rows = [("Id", "PK"), ("DateKey", "FK"), ("Product_Id", "FK"), ("Company_Id", "FK"),
                 ("Document_Id", "dégénérée"), ("QuantiteVendue", "mesure"), ("Remise_HT", "mesure"), ("CA_HT", "mesure"),
                 ("Cout_HT", "mesure"), ("Marge HT = CA HT − Cout HT", "Power BI")]
    card(fx, fy, fw, "fait_ventes", fact_rows, "2563EB")
    fk_y = {name: fy + 0.47 + i * 0.3 + 0.15 for i, (name, _) in enumerate(fact_rows)}
    dims_l = [("dim_temps", [("DateKey", "PK"), ("Date, année, trimestre", ""), ("Mois, semaine ISO", ""), ("Jour férié", "")], "DateKey")]
    dims_r = [("dim_produit", [("Product_Id", "PK"), ("Libellé, famille", ""), ("Marque", ""), ("Seuil d'alerte", "")], "Product_Id"),
              ("dim_client", [("Company_Id", "PK"), ("Nom, type de client", ""), ("Client identifié (oui / non)", "")], "Company_Id")]
    for side, dims in (("L", dims_l), ("R", dims_r)):
        y = 1.45
        for name, rows, fk in dims:
            x = 0.55 if side == "L" else 9.5
            h = card(x, y, 3.3, name, rows, "334155")
            dy = y + 0.47 + 0.15
            if side == "L":
                line(s, x + 3.3, dy, fx, fk_y[fk], color=MUTED, width=1.5)
                text(s, x + 3.33, dy - 0.3, 0.3, 0.3, "1", size=11, color=MUTED, bold=True)
                text(s, fx - 0.3, fk_y[fk] - 0.3, 0.3, 0.3, "N", size=11, color=MUTED, bold=True)
            else:
                line(s, fx + fw, fk_y[fk], x, dy, color=MUTED, width=1.5)
                text(s, x - 0.3, dy - 0.3, 0.3, 0.3, "1", size=11, color=MUTED, bold=True)
                text(s, fx + fw + 0.03, fk_y[fk] - 0.3, 0.3, 0.3, "N", size=11, color=MUTED, bold=True)
            y += h + 0.3
    text(s, 4.75, 6.25, 3.9, 0.6, "Grain : 1 produit vendu dans 1 document à 1 date", size=12, color=MUTED,
         align=PP_ALIGN.CENTER)

    # 14. Faits et mesures ----------------------------------------------------------
    s = d.slide("Trois tables de faits et leurs mesures", "4 · Modèle du Data Warehouse",
                notes="La table centrale est fait_ventes, au grain d'une ligne de produit vendue dans un document à une "
                      "date (granularité recommandée par le cahier). Les mesures sont signées : les retours et avoirs "
                      "viennent en négatif, ce qui permet de simplement additionner. Les indicateurs dérivés (marge, "
                      "rupture, stock faible, montant encaissé) sont des mesures Power BI, pas des colonnes.")
    rw = S["rows"]
    table(s, 0.55, 1.45, 12.25, [
        ["Table de faits", "Granularité (1 ligne =)", "Lignes", "Mesures", "Dimensions reliées"],
        ["fait_ventes", "1 produit vendu dans 1 document à 1 date", fr(rw["fait_ventes"]),
         "QuantiteVendue, Remise_HT, CA_HT, Cout_HT\n(+ Document_Id pour compter les ventes)", "Temps, Produit, Client"],
        ["fait_stock_actuel", "1 produit à la date de snapshot (29/09/2026)", fr(rw["fait_stock_actuel"]),
         "Quantity", "Temps, Produit"],
        ["fait_paiements", "1 paiement", fr(rw["fait_paiements"]), "Amount\n(+ EstPaiementFournisseur pour filtrer)", "Temps, Paiement"],
        ["Mesures Power BI", "calculées, non stockées", "—",
         "Marge HT, panier moyen, croissance, clients actifs,\nruptures, stock faible, montant encaissé", "selon la mesure"],
    ], [2.35, 3.0, 1.05, 3.4, 2.45], size=12, row_h=0.95)

    # 15. Dimensions ----------------------------------------------------------------
    s = d.slide("Quatre dimensions conformes, partagées par les faits", "4 · Modèle du Data Warehouse",
                notes="Chaque dimension a une clé primaire simple et seulement les attributs exigés par le cahier. Le "
                      "calendrier français est calculé ; la météo et les épidémies restent hors du Data Warehouse (jeu ML "
                      "de prévision). Des membres -1 « non renseigné » garantissent que chaque clé étrangère retrouve sa dimension.")
    table(s, 0.55, 1.45, 12.25, [
        ["Dimension", "Clé primaire", "Attributs principaux", "Lignes"],
        ["dim_temps", "DateKey", "Date, année, trimestre, mois, semaine ISO, jour férié (30/09/2024 → 29/09/2026)", fr(rw["dim_temps"])],
        ["dim_produit", "Product_Id", "Libellé, famille, marque, seuil d'alerte de stock", fr(rw["dim_produit"])],
        ["dim_client", "Company_Id", "Nom, type (particulier / B2B / comptoir anonyme), client identifié", fr(rw["dim_client"])],
        ["dim_paiement", "PaymentMode_Id", "Espèces, carte bancaire, chèque, crédit, jetons, non renseigné", fr(rw["dim_paiement"])],
    ], [2.3, 2.0, 6.75, 1.2], size=13, row_h=0.75)

    # 16. Choix de modélisation -----------------------------------------------------
    s = d.slide("Choix de modélisation et garanties de qualité", "4 · Modèle du Data Warehouse",
                notes="Les décisions de modélisation à défendre devant le jury, et comment nous avons vérifié le modèle.")
    choix = [("Constellation réduite", "Trois processus (ventes, stock, paiements) partagent quatre dimensions : "
                                       "uniquement ce que le cahier demande."),
             ("Grain le plus fin", "Une ligne de produit vendue : on peut toujours agréger, jamais redescendre."),
             ("Mesures signées", "Retours et avoirs en négatif : un simple SUM donne le CA net."),
             ("Sans double comptage", "Les factures qui refacturent des bons de livraison sont exclues des ventes."),
             ("Intégrité garantie", "Membres -1 « non renseigné » ; 100 % des clés étrangères retrouvent leur dimension."),
             ("Stocké ou calculé", "Une colonne n'est stockée que si le cahier l'exige et qu'elle ne peut pas être "
                                   "recalculée ; marge, rupture, stock faible sont des mesures.")]
    for i, (t, d_) in enumerate(choix):
        x, y = 0.55 + (i % 2) * 6.2, 1.55 + (i // 2) * 1.75
        box(s, x, y, 6.0, 1.55, LIGHT, shape=MSO_SHAPE.RECTANGLE)
        box(s, x, y, 0.09, 1.55, NAVY, shape=MSO_SHAPE.RECTANGLE)
        text(s, x + 0.3, y + 0.15, 5.5, 0.45, t, size=17, color=NAVY, bold=True)
        text(s, x + 0.3, y + 0.62, 5.5, 0.9, d_, size=14)

    # 17. Limites et suite ----------------------------------------------------------
    s = d.slide("Limites identifiées et prochaines étapes", "5 · Conclusion",
                notes="Être transparents sur les limites : historique court, localisation du magasin à confirmer, "
                      "et deux chiffres du cahier que les données ne confirment pas. Puis présenter le plan pour la "
                      "suite du projet.")
    text(s, 0.55, 1.5, 6.0, 0.45, "Limites", size=20, color=AMBER, bold=True)
    text(s, 0.55, 2.05, 6.0, 4.6, [
        "• **Historique réel court :** 7 mois ; la prolongation à 2 ans est synthétique (hypothèses documentées) – "
        "l'apport météo / épidémies se mesure sur le réel.",
        "• **Localisation à confirmer :** le logiciel source est configuré pour la Tunisie, le cahier situe le magasin en France.",
        f"• **Référentiel incomplet :** {fr(S['sans_famille_pct'])} % des produits sans famille ; {fr(S['anonyme_pct'])} % de ventes anonymes.",
        f"• **Moyens de paiement :** {fr(S['sans_mode_pct'])} % des encaissements réels sans moyen renseigné dans la source.",
    ], size=15, space=10)
    text(s, 6.95, 1.5, 6.0, 0.45, "Prochaines étapes", size=20, color=TEAL, bold=True)
    nxt = ["Charger le Data Warehouse dans PostgreSQL", "Construire les 5 tableaux de bord Power BI",
           "Entraîner et évaluer les 4 modèles ML", "Mesurer l'apport météo / épidémies sur la période réelle",
           "Restitution finale et documentation"]
    for i, t in enumerate(nxt):
        y = 2.05 + i * 0.88
        boxtext(s, 6.95, y, 0.6, 0.6, [(str(i + 1), {"align": PP_ALIGN.CENTER})], fill=TEAL, size=17, color=WHITE, bold=True)
        text(s, 7.75, y + 0.08, 5.1, 0.5, t, size=16)

    # 18. Merci ------------------------------------------------------------------------
    s = d.slide(notes="Remercier le jury et ouvrir les questions.")
    box(s, 0, 0, 13.333, 7.5, NAVY, shape=MSO_SHAPE.RECTANGLE)
    text(s, 0.9, 2.6, 11.5, 1.1, "Merci de votre attention", size=48, color=WHITE, bold=True, align=PP_ALIGN.CENTER)
    text(s, 0.9, 3.75, 11.5, 0.6, "Questions et échanges", size=24, color="99F6E4", align=PP_ALIGN.CENTER)
    return d.prs


def main():
    S = stats()
    prs = build(S)
    prs.save(OUT)
    print(f"Présentation écrite : {OUT}")


if __name__ == "__main__":
    main()
