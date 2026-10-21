"""
Nettoyage de `DocumentsReports.csv` -> `cleaned/document_reports.csv`.

Code repris de clean_data.py (branche main) : mêmes règles, mêmes résultats.
Le détail de chaque étape est affiché à l'exécution et repris dans cleaned/CLEANING_REPORT.md.

Lancer depuis le dossier qui contient fichiers/ (ou depuis ce dossier monté à côté) :
    python script_cleaning_DocumentsReports.py
"""
from cleaning_commun import *  # noqa: F401,F403


def clean_document_reports():
    log = Log("document_reports.csv", ["DocumentsReports.csv"],
              "Technical per-line flags from the software report cache (low analytical value).")
    cols, recs, _ = read("DocumentsReports.csv", log)
    out, bad = [], 0
    for r in recs:
        try:
            d = json.loads(r["Benef"])
        except ValueError:
            bad += 1
            continue
        for it in d.get("di", []):
            out.append({"Id": r["Id"].strip(), "Benef_diid": str(it.get("diid", "")),
                        "Benef_pid": str(it.get("pid", "")),
                        "Benef_bcdde": str(it.get("bcdde", "")), "Benef_bcdve": str(it.get("bcdve", ""))})
    log(f"Unpacked the `Benef` JSON (one JSON list per document) into one row per document line: "
        f"{len(recs):,} documents → {len(out):,} rows. {bad} unreadable JSON value(s) skipped.")
    log("Despite its name, `Benef` holds no profit amount – only two unexplained 0/1 flags (`bcdde`, `bcdve`), kept "
        "as `Benef_bcdde`, `Benef_bcdve`. `Id` = document id, `Benef_diid` = document line id, `Benef_pid` = product "
        "stock id (new columns named <JsonColumn>_<jsonKey>). Recommendation: not needed for the warehouse.")
    write(["Id", "Benef_diid", "Benef_pid", "Benef_bcdde", "Benef_bcdve"], out, log)


if __name__ == "__main__":
    run(clean_document_reports)
