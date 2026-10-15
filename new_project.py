"""Create a NEW survey project from this template, with its own GitHub repo.

    python new_project.py moe-survey
    python new_project.py moe-survey --dest ~/projects --owner farhoudjk
    python new_project.py moe-survey --no-github      # local folder only

The template folder is never changed. The new project gets:
  - a clean copy of all agents, skills and scripts (empty state/, paper/, inputs/papers/)
  - config.yaml with project_name and is_template: false
  - its own private GitHub repo <owner>/<name>
Works on Windows, macOS and Linux.
"""
import argparse
import datetime
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent
SKIP = {".git", "work", "logs", "__pycache__", ".venv", "new_project.py"}
EMPTY = {"state", "paper", "inputs/papers"}  # copied as empty folders


def run(cmd, cwd):
    print("  $", " ".join(cmd))
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout + r.stderr)
        sys.exit(f"Command failed: {' '.join(cmd)}")
    return r.stdout.strip()


def ignore(dirpath, names):
    rel = pathlib.Path(dirpath).resolve().relative_to(ROOT).as_posix()
    out = [n for n in names if n in SKIP or n.endswith(".zip")]
    if rel in EMPTY:
        out += [n for n in names if n != ".gitkeep"]
    return out


def set_config(dest, name, owner, private):
    p = dest / "pipeline" / "config.yaml"
    s = p.read_text(encoding="utf-8")
    for key, val in [("is_template", "false"), ("project_name", name),
                     ("private_repos", "true" if private else "false")] + \
                    ([("github_owner", owner)] if owner else []):
        s, n = re.subn(rf"^{key}:.*$", f"{key}: {val}", s, flags=re.M)
        if n != 1:
            sys.exit(f"Could not set {key} in config.yaml")
    p.write_text(s, encoding="utf-8")
    m = re.search(r"^github_owner:\s*(\S+)", s, flags=re.M)
    return m.group(1) if m else None


def template_version():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True).stdout.strip() or "unknown"
    except FileNotFoundError:
        return "unknown"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name", help="project name, letters, numbers, - and _ only")
    ap.add_argument("--dest", default=str(ROOT.parent), help="parent folder for the new project")
    ap.add_argument("--owner", help="GitHub user or org (default: github_owner in config.yaml)")
    ap.add_argument("--public", action="store_true", help="make the GitHub repos public")
    ap.add_argument("--no-github", action="store_true", help="only create the local folder")
    a = ap.parse_args()

    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", a.name):
        sys.exit("Use only letters, numbers, '.', '-' and '_' in the name.")
    dest = pathlib.Path(a.dest).resolve() / a.name
    if dest.exists():
        sys.exit(f"{dest} already exists. Pick another name or delete it.")

    print(f"Creating project in {dest}")
    shutil.copytree(ROOT, dest, ignore=ignore)
    for d in EMPTY:
        (dest / d).mkdir(parents=True, exist_ok=True)
        (dest / d / ".gitkeep").touch()
    owner = set_config(dest, a.name, a.owner, not a.public)
    (dest / "PROJECT.md").write_text(
        f"# {a.name}\n\nCreated {datetime.date.today()} from survey-pipeline template "
        f"(version {template_version()}).\n\nWrite the topic in `inputs/topic.md`, then see README.md "
        "Part B.\n", encoding="utf-8")

    run(["git", "init", "-b", "main"], dest)
    run(["git", "add", "-A"], dest)
    run(["git", "commit", "-m", f"New project {a.name} from survey-pipeline template"], dest)

    if a.no_github:
        print(f"\nDone (local only). Folder: {dest}")
        return
    if shutil.which("gh") is None:
        sys.exit("GitHub CLI 'gh' not found. Install it, run 'gh auth login', then inside the "
                 f"project folder run: gh repo create {owner}/{a.name} --private --source . --push")
    run(["gh", "repo", "create", f"{owner}/{a.name}", "--public" if a.public else "--private",
         "--source", ".", "--push"], dest)

    print(f"""
Done. New project: https://github.com/{owner}/{a.name}
Local folder:     {dest}

Next:
  1. cd "{dest}"
  2. write your topic in inputs/topic.md (optional: seed papers in inputs/seeds.md, PDFs in inputs/papers/)
  3. python pipeline/orchestrator.py
""")


if __name__ == "__main__":
    main()
