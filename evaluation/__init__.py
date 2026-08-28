"""
Offline evaluation harness for the biometric pipeline.

Nothing in this package is on a live authentication path. Every module here
reads the enrolled dataset and writes reports; none of them can grant or deny
anything, because nothing in the running system imports them.

Run the entry points as modules, so no CLI wiring in main.py is needed:

    venv/Scripts/python.exe -m evaluation.extract      # slow, run once
    venv/Scripts/python.exe -m evaluation.face_eval    # fast, iterate freely

Layout:
    extract.py    dataset images -> cached per-sample metrics + embeddings
    pairs.py      genuine / impostor masks over the sample set
    metrics.py    ROC, AUC, EER, FAR/FRR sweeps, d'
    protocols.py  Protocol A (pairwise) and Protocol B (the deployed rule)
    plots.py      figures for the paper
    face_eval.py  step 1 entry point — runs A + B and writes the report

Outputs land in evaluation/output/ (gitignored, regenerable). Collected
measurements that cannot be regenerated live in evaluation/data/ instead.
"""
