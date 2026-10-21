"""
Nettoyage de `RelatedDocuments.csv` -> `cleaned/related_documents.csv`.

Code repris de clean_data.py (branche main) : mêmes règles, mêmes résultats.
Le détail de chaque étape est affiché à l'exécution et repris dans cleaned/CLEANING_REPORT.md.

Lancer depuis le dossier qui contient fichiers/ (ou depuis ce dossier monté à côté) :
    python script_cleaning_RelatedDocuments.py
"""
from cleaning_commun import *  # noqa: F401,F403


def clean_related_documents():
    log = Log("related_documents.csv", ["RelatedDocuments.csv"],
              "Links between documents (e.g. delivery notes grouped into one invoice).")
    cols, recs, _ = read("RelatedDocuments.csv", log)
    rel = Counter(r["Relation"].strip() for r in recs)
    cols, recs = standardize(cols, recs, log, "DMY")
    log(f"`Relation` always has the same value {dict(rel)} → dropped.")
    cols, recs = select(recs, [("Id", "relation_id"), ("Document1_Id", "document_id"),
                               ("Document2_Id", "related_document_id")], log)
    write(cols, recs, log)


if __name__ == "__main__":
    run(clean_related_documents)
