"""OPTIONAL. GPU side for the benchmark step (only if benchmark: true in config.yaml).

Run on the GPU machine, in a separate clone of the project repo, inside tmux:
    python pipeline/gpu_watcher.py

It picks up a bench job, lets the bench-runner agent set up bench/ (and smoke-test it),
runs bench/run_all.sh itself (no time limit), then lets the agent summarize the results.
"""
import argparse
import subprocess
import time

from common import (HANDOFF, ROOT, STATE, git_pull, git_push, guard_not_template, load_config, now,
                    read_json, rel, run_agent, write_json)

CFG = load_config()


def report(job, status, **extra):
    write_json(HANDOFF / "from_gpu.json", {"job_id": job["job_id"], "kind": job["kind"], "status": status,
                                           "updated_at": now(), **extra})
    git_push(["state", "bench"], f"gpu: job {job['job_id']} {status}")


def handle(job):
    out = STATE / "bench"
    out.mkdir(parents=True, exist_ok=True)
    report(job, "running", started_at=now())
    try:
        run_agent("bench-runner", f"Mode: setup. Plan: {job['plan']}. Build bench/ and write {rel(out)}/setup.md.", CFG)
        log = out / "run_all.log"
        print(f"[{now()}] Running bench/run_all.sh (log: {rel(log)})", flush=True)
        with open(log, "w") as f:
            subprocess.run(["bash", "bench/run_all.sh"], cwd=ROOT, stdout=f, stderr=subprocess.STDOUT)
        run_agent("bench-runner", f"Mode: summary. Plan: {job['plan']}. Log: {rel(log)}. "
                  f"Write {rel(out)}/results.json and {rel(out)}/summary.md.", CFG)
        report(job, "done", finished_at=now())
    except Exception as e:
        (out / "error.md").write_text(f"# Benchmark failed\n\n```\n{e}\n```\n")
        report(job, "failed", error=str(e)[:2000], finished_at=now())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()
    guard_not_template(CFG)
    print(f"[{now()}] GPU watcher started. Polling every {CFG['poll_seconds']}s.")
    while True:
        git_pull()
        job = read_json(HANDOFF / "to_gpu.json")
        doneinfo = read_json(HANDOFF / "from_gpu.json", {})
        if job and job.get("job_id") != doneinfo.get("job_id"):
            print(f"[{now()}] New job {job['job_id']}")
            handle(job)
        if a.once:
            break
        time.sleep(CFG["poll_seconds"])


if __name__ == "__main__":
    main()
