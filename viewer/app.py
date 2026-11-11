#!/usr/bin/env python3
"""Interface web pour dicom2stl : convertit un scanner en maillage 3D et l'affiche.

Lancement (depuis la racine du projet) :

    pip install -r viewer/requirements.txt
    python viewer/app.py

puis ouvrir http://127.0.0.1:5000
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
import uuid

from flask import Flask, abort, jsonify, request, send_file, send_from_directory
from werkzeug.utils import secure_filename

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
SAMPLE = os.path.join(REPO_ROOT, "examples", "Data", "ct_head.nii.gz")

# Formats d'entrée acceptés quand un seul fichier est envoyé.
SINGLE_FILE_EXTS = (".zip", ".nii", ".nii.gz", ".nrrd", ".mha", ".mhd", ".vtk")
TISSUES = ("skin", "bone", "soft", "fat")
CONVERT_TIMEOUT = 900  # secondes

app = Flask(__name__, static_folder=os.path.join(HERE, "static"), static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024 * 1024  # 2 Go

# Keep conversion files inside the project: some Windows environments deny
# subprocess access to system temp folders or newly created private folders.
JOBS_ROOT = os.path.join(REPO_ROOT, ".viewer_jobs")
os.makedirs(JOBS_ROOT, exist_ok=True)
JOBS_DIR = os.path.join(JOBS_ROOT, uuid.uuid4().hex)
os.mkdir(JOBS_DIR)


def _number(name, cast, lo, hi, default):
    """Lit un paramètre numérique du formulaire et le borne."""
    raw = request.form.get(name, "")
    if raw == "":
        return default
    try:
        value = cast(raw)
    except ValueError:
        abort(400, f"Paramètre invalide : {name}")
    return max(lo, min(hi, value))


def _save_uploads(files, input_dir):
    """Enregistre les fichiers envoyés ; renvoie le chemin à passer à dicom2stl."""
    saved = []
    for i, f in enumerate(files):
        name = secure_filename(os.path.basename(f.filename or "")) or f"file_{i}"
        path = os.path.join(input_dir, f"{i:05d}_{name}")
        f.save(path)
        saved.append((name, path))

    if len(saved) == 1:
        name, path = saved[0]
        lower = name.lower()
        if lower.endswith(SINGLE_FILE_EXTS):
            # dicom2stl se base sur l'extension : on la remet proprement.
            ext = next(e for e in sorted(SINGLE_FILE_EXTS, key=len, reverse=True) if lower.endswith(e))
            final = os.path.join(input_dir, "volume" + ext)
            os.replace(path, final)
            return final
    # Plusieurs fichiers (dossier DICOM) : on passe le dossier entier.
    return input_dir


@app.get("/")
def index():
    return send_from_directory(os.path.join(HERE, "static"), "index.html")


@app.get("/api/info")
def info():
    return jsonify(sample_available=os.path.exists(SAMPLE), tissues=TISSUES)


@app.post("/api/convert")
def convert():
    use_sample = request.form.get("sample") == "1"
    files = request.files.getlist("files")

    tissue = request.form.get("tissue", "bone")
    if tissue not in TISSUES:
        abort(400, "Type de tissu invalide")
    smooth = _number("smooth", int, 0, 200, 25)
    reduce_ = _number("reduce", float, 0.0, 0.99, 0.9)
    largest = request.form.get("largest") == "1"

    job_id = uuid.uuid4().hex
    job_dir = os.path.join(JOBS_DIR, job_id)
    input_dir = os.path.join(job_dir, "input")
    os.makedirs(input_dir)
    out_stl = os.path.join(job_dir, "mesh.stl")

    if use_sample:
        if not os.path.exists(SAMPLE):
            shutil.rmtree(job_dir, ignore_errors=True)
            abort(404, "Échantillon introuvable")
        source = SAMPLE
    elif files:
        source = _save_uploads(files, input_dir)
    else:
        shutil.rmtree(job_dir, ignore_errors=True)
        abort(400, "Aucun fichier envoyé")

    cmd = [
        sys.executable, "-m", "dicom2stl.Dicom2STL",
        "--type", tissue,
        "--smooth", str(smooth),
        "--reduce", str(reduce_),
        "--output", out_stl,
    ]
    if largest:
        cmd += ["--enable", "largest"]
    cmd.append(source)

    started = time.perf_counter()
    try:
        proc = subprocess.run(
            cmd, cwd=REPO_ROOT, capture_output=True, text=True, timeout=CONVERT_TIMEOUT
        )
    except subprocess.TimeoutExpired:
        shutil.rmtree(job_dir, ignore_errors=True)
        return jsonify(error="La conversion a dépassé le temps limite."), 504
    elapsed = time.perf_counter() - started

    log = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0 or not os.path.exists(out_stl):
        shutil.rmtree(job_dir, ignore_errors=True)
        if "No module named 'vtk'" in log:
            error = "VTK est manquant. Liberez de l'espace disque, puis relancez viewer/run.bat."
        elif "No module named 'SimpleITK'" in log or "No module named 'SimpleITKUtilities'" in log:
            error = "Dependances d'imagerie manquantes. Relancez viewer/run.bat."
        else:
            error = "Conversion impossible. Consultez le detail ci-dessous."
        return jsonify(error=error, log=log[-3000:]), 422

    match = re.findall(r"Writing (\d+) polygons", log)
    triangles = int(match[-1]) if match else None
    # Les fichiers envoyés ne servent plus : on ne garde que le maillage.
    shutil.rmtree(input_dir, ignore_errors=True)

    return jsonify(
        id=job_id,
        stl_url=f"/api/stl/{job_id}.stl",
        triangles=triangles,
        size_bytes=os.path.getsize(out_stl),
        seconds=round(elapsed, 1),
        log=log[-3000:],
    )


@app.get("/api/stl/<job_id>.stl")
def get_stl(job_id):
    if not re.fullmatch(r"[0-9a-f]{32}", job_id):
        abort(404)
    path = os.path.join(JOBS_DIR, job_id, "mesh.stl")
    if not os.path.exists(path):
        abort(404)
    return send_file(path, mimetype="model/stl", download_name="mesh.stl")


def main():
    parser = argparse.ArgumentParser(description="Interface web de dicom2stl")
    parser.add_argument("--host", default="127.0.0.1", help="Adresse d'écoute (défaut : 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()
    print(f"Interface disponible sur http://{args.host}:{args.port}")
    try:
        app.run(host=args.host, port=args.port, debug=False, threaded=True)
    finally:
        shutil.rmtree(JOBS_DIR, ignore_errors=True)
        try:
            os.rmdir(JOBS_ROOT)
        except OSError:
            pass


if __name__ == "__main__":
    main()
