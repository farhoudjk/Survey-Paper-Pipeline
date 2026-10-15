"""Get a paper's full text. Run from the project root.

python .claude/skills/extraction-schema/fetch_paper.py <paper-id>
"""
import json
import pathlib
import shutil
import subprocess
import sys
import urllib.request

ROOT = pathlib.Path.cwd()
OUT = ROOT / "work" / "papers"


def download(url, dest):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "survey-pipeline/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        if data[:4] != b"%PDF":
            return False
        dest.write_bytes(data)
        return True
    except Exception:
        return False


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: fetch_paper.py <paper-id>")
    pid = sys.argv[1]
    corpus = json.loads((ROOT / "state" / "corpus.json").read_text(encoding="utf-8"))
    p = corpus["papers"].get(pid)
    if not p:
        sys.exit(f"{pid} is not in state/corpus.json")
    OUT.mkdir(parents=True, exist_ok=True)
    pdf, txt = OUT / f"{pid}.pdf", OUT / f"{pid}.txt"
    if txt.exists() and txt.stat().st_size > 2000:
        print(f"FULL TEXT {txt}")
        return
    ok = False
    keys = [k for k in (pid, p.get("arxiv")) if k]
    for f in (ROOT / "inputs" / "papers").glob("*.pdf"):
        if any(k.lower() in f.name.lower() for k in keys):
            shutil.copy(f, pdf)
            ok = True
            break
    if not ok and p.get("arxiv"):
        ok = download(f"https://arxiv.org/pdf/{p['arxiv']}", pdf)
    if not ok and p.get("pdf_url"):
        ok = download(p["pdf_url"], pdf)
    if not ok:
        print(f"ABSTRACT ONLY. No PDF found for {pid}. Abstract:\n{p.get('abstract') or '(none)'}")
        return
    if shutil.which("pdftotext") is None:
        sys.exit("pdftotext not found. Install it: sudo apt install poppler-utils")
    subprocess.run(["pdftotext", "-layout", str(pdf), str(txt)], check=False)
    if txt.exists() and txt.stat().st_size > 2000:
        print(f"FULL TEXT {txt}")
    else:
        print(f"ABSTRACT ONLY. PDF text could not be extracted for {pid}. Abstract:\n{p.get('abstract') or '(none)'}")


if __name__ == "__main__":
    main()
