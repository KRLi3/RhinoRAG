import os
import sys
import zipfile

VERSION = "v1.0"

BASE = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE, "db")
DIST_DIR = os.path.join(BASE, "dist")
DATA_ZIP = os.path.join(DIST_DIR, "rhino-rag-data.zip")
APP_ZIP = os.path.join(DIST_DIR, f"RhinoRAG-{VERSION}.zip")

MODEL_REPO = "models--BAAI--bge-small-en-v1.5"

# The user-facing app package: code + installer + readme. No db / model / venv —
# install.bat downloads the data package (rhino-rag-data.zip) at install time.
APP_FILES = [
    "install.bat",
    "mcp_server.py",
    "rag_core.py",
    "ingest.py",
    "requirements.txt",
    "README.md",
]


def find_model_cache():
    """Locate the bge-small snapshot in the HuggingFace hub cache."""
    candidates = []
    hf_home = os.environ.get("HF_HOME")
    if hf_home:
        candidates.append(os.path.join(hf_home, "hub"))
    candidates.append(os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub"))
    candidates.append(os.path.join(BASE, "models", "hub"))

    for hub in candidates:
        repo = os.path.join(hub, MODEL_REPO)
        if os.path.isdir(repo):
            return hub, repo
    return None, None


def add_tree(zf, src_root, arc_prefix):
    count = 0
    for root, _, files in os.walk(src_root):
        for f in files:
            full = os.path.join(root, f)
            rel = os.path.relpath(full, src_root)
            zf.write(full, os.path.join(arc_prefix, rel))
            count += 1
    return count


def build_data_zip():
    """db/ + bge-small model -> rhino-rag-data.zip (downloaded by install.bat)."""
    if not os.path.isdir(DB_DIR) or not os.listdir(DB_DIR):
        print("ERROR: db/ is empty. Run `python ingest.py` first.")
        sys.exit(1)

    hub, repo = find_model_cache()
    if not repo:
        print(f"ERROR: could not find {MODEL_REPO} in any HuggingFace cache.")
        print("Run `python ingest.py` once to download the model, then retry.")
        sys.exit(1)

    if os.path.exists(DATA_ZIP):
        os.remove(DATA_ZIP)

    with zipfile.ZipFile(DATA_ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        n_db = add_tree(zf, DB_DIR, "db")
        # Recreate a minimal HF cache layout under models/ so HF_HOME=./models works.
        n_model = add_tree(zf, os.path.join(hub, MODEL_REPO),
                           os.path.join("models", "hub", MODEL_REPO))

    size_mb = os.path.getsize(DATA_ZIP) / (1024 * 1024)
    print(f"[data] {n_db} db files + {n_model} model files -> "
          f"{os.path.basename(DATA_ZIP)} ({size_mb:.1f} MB)")


def build_app_zip():
    """install.bat + code + readme -> RhinoRAG-<ver>.zip (what users download)."""
    missing = [f for f in APP_FILES if not os.path.exists(os.path.join(BASE, f))]
    if missing:
        print(f"ERROR: missing app files: {missing}")
        sys.exit(1)

    if os.path.exists(APP_ZIP):
        os.remove(APP_ZIP)

    with zipfile.ZipFile(APP_ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for f in APP_FILES:
            zf.write(os.path.join(BASE, f), f)

    size_kb = os.path.getsize(APP_ZIP) / 1024
    print(f"[app]  {len(APP_FILES)} files -> "
          f"{os.path.basename(APP_ZIP)} ({size_kb:.0f} KB)")


def main():
    os.makedirs(DIST_DIR, exist_ok=True)
    build_app_zip()
    build_data_zip()
    print()
    print("[done] Upload BOTH to the GitHub Release:")
    print(f"  - {APP_ZIP}     (users download this)")
    print(f"  - {DATA_ZIP}    (install.bat fetches this automatically)")


if __name__ == "__main__":
    main()
