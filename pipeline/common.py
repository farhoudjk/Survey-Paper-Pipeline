"""Shared helpers: config, JSON files, git hand-off, running agents."""
import concurrent.futures as cf
import datetime
import json
import pathlib
import subprocess
import time

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATE = ROOT / "state"
HANDOFF = STATE / "handoff"
LOGS = ROOT / "logs"


def load_config():
    with open(ROOT / "pipeline" / "config.yaml") as f:
        return yaml.safe_load(f)


def guard_not_template(cfg):
    if cfg.get("is_template"):
        raise SystemExit(
            "This is the TEMPLATE repo. Do not run the pipeline here.\n"
            "Create a survey project first:  python new_project.py <project-name>\n"
            "Then run the pipeline inside the new project folder.")


def now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def rel(p):
    return str(pathlib.Path(p).resolve().relative_to(ROOT))


def read_json(p, default=None):
    p = pathlib.Path(p)
    if not p.exists():
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def write_json(p, data):
    p = pathlib.Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def sh(cmd, cwd=ROOT, check=True):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(map(str, cmd))}\n{r.stdout}\n{r.stderr}")
    return r


# ---------- git ----------

def git_pull():
    sh(["git", "pull", "--rebase", "--autostash"], check=False)


def git_push(paths, msg, retries=5):
    sh(["git", "add", "-A", *[str(p) for p in paths]], check=False)
    if sh(["git", "diff", "--cached", "--quiet"], check=False).returncode == 0:
        return
    sh(["git", "commit", "-m", msg])
    for _ in range(retries):
        if sh(["git", "push"], check=False).returncode == 0:
            return
        sh(["git", "pull", "--rebase"], check=False)
        time.sleep(3)
    print("WARNING: git push failed. Work is saved locally; push by hand later.")


# ---------- agents ----------

def run_agent(name, task, cfg, cwd=ROOT):
    """Run one Claude Code agent headless. Each call is a fresh session."""
    LOGS.mkdir(exist_ok=True)
    log = LOGS / f"{datetime.datetime.now():%Y%m%d_%H%M%S_%f}_{name}.log"
    cmd = ["claude", "-p", "--agent", name, "--permission-mode", "dontAsk",
           "--max-turns", str(cfg.get("agent_max_turns", 300)), "--output-format", "text"]
    if cfg.get("model"):
        cmd += ["--model", cfg["model"]]
    cmd.append(task)
    print(f"[{now()}] >>> {name}  (log: {rel(log)})", flush=True)
    with open(log, "w", encoding="utf-8") as f:
        f.write(f"TASK:\n{task}\n\nOUTPUT:\n")
        f.flush()
        r = subprocess.run(cmd, cwd=cwd, stdout=f, stderr=subprocess.STDOUT, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Agent {name} failed (exit {r.returncode}). See {log}")
    print(f"[{now()}] <<< {name} done", flush=True)
    return log


def run_agents_parallel(jobs, cfg):
    """jobs = [(agent_name, task), ...]. Runs up to cfg['parallel_agents'] at once.
    Returns the list of jobs that failed (so the caller can retry them)."""
    failed = []
    with cf.ThreadPoolExecutor(max_workers=max(1, cfg.get("parallel_agents", 1))) as ex:
        futs = {ex.submit(run_agent, n, t, cfg): (n, t) for n, t in jobs}
        for fu in cf.as_completed(futs):
            try:
                fu.result()
            except Exception as e:  # keep going, report at the end
                print(f"   failed: {e}")
                failed.append(futs[fu])
    return failed


def require(path, who):
    if not pathlib.Path(path).exists():
        raise RuntimeError(f"{who} did not write {rel(path)}. Check the latest log in logs/.")


def chunks(xs, n):
    return [xs[i:i + n] for i in range(0, len(xs), n)]
