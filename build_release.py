import os
import sys
import zipfile

BASE = os.path.dirname(os.path.abspath(__file__))
DB_DIR = os.path.join(BASE, "db")
DIST_DIR = os.path.join(BASE, "dist")
OUT_ZIP = os.path.join(DIST_DIR, "rhino-rag-data.zip")

MODEL_REPO = "models--BAAI--bge-small-en-v1.5"


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


def main():
    if not os.path.isdir(DB_DIR) or not os.listdir(DB_DIR):
        print("ERROR: db/ is empty. Run `python ingest.py` first.")
        sys.exit(1)

    hub, repo = find_model_cache()
    if not repo:
        print(f"ERROR: could not find {MODEL_REPO} in any HuggingFace cache.")
        print("Run `python ingest.py` once to download the model, then retry.")
        sys.exit(1)

    os.makedirs(DIST_DIR, exist_ok=True)
    if os.path.exists(OUT_ZIP):
        os.remove(OUT_ZIP)

    print(f"[build] db:    {DB_DIR}")
    print(f"[build] model: {repo}")
    print(f"[build] -> {OUT_ZIP}")

    with zipfile.ZipFile(OUT_ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        n_db = add_tree(zf, DB_DIR, "db")
        # Recreate a minimal HF cache layout under models/ so HF_HOME=./models works.
        n_model = add_tree(zf, os.path.join(hub, MODEL_REPO),
                           os.path.join("models", "hub", MODEL_REPO))

    size_mb = os.path.getsize(OUT_ZIP) / (1024 * 1024)
    print(f"[done] {n_db} db files + {n_model} model files, {size_mb:.1f} MB")
    print(f"[done] Upload {OUT_ZIP} to the GitHub Release.")


if __name__ == "__main__":
    main()
