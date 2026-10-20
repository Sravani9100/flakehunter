# Evals

Each directory in `cases/` is a tiny project with one planted flaky test. Its `case.toml`
records the root-cause category (plus any other accepted categories), the cause, and the
expected fix.

`run_evals.py` runs the production pipeline on each case:

1. Copy the case into a throwaway checkout and measure its baseline flake rate.
2. **Diagnose.** Score: is the category one the case accepts?
3. **Fix.** The agent edits the copy; the harness reruns the test `FLAKEHUNTER_VERIFY_RUNS`
   times (default 100) in fresh processes and runs the integrity checks. Score: `verified`.

```powershell
python evals/measure_flake_rate.py -n 40          # no API key needed
python evals/run_evals.py                          # all cases
python evals/run_evals.py timing_race hash_order   # a subset
python evals/run_evals.py --verify-runs 30         # cheaper, less certain
```

Results go to `results/latest.json` (shown on the dashboard's Evals page) and a timestamped
copy. Each case's `expected_fix` explains what a good fix looks like, including where
seeding or sorting would only hide the problem. Read the diffs, not just the scores.

## Adding a case

Create `cases/<name>/` with the code, a test, and `case.toml`:

```toml
category = "concurrency"
also_accept = ["ordering"]          # optional
flaky_test = "test_module::test_name"
root_cause = "..."
expected_fix = "..."
```

Check it really flakes with `python evals/measure_flake_rate.py <name> -n 40`. Aim for
10-60%: rarer flakes make verification noisy, and more frequent ones are just failures.
