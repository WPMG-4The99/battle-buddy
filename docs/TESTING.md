# Testing Battle Buddy

Stdlib `unittest`. No extra Python packages. No accounts. No cloud keys.

## Windows

From the repo root:

```text
python -m unittest discover -s tests
```

Tk ships with the official Windows Python installer. A display is already there.

## Linux

Need Python 3.12 + `python3-tk` + `xvfb`. Then one process per module so Tk teardown cannot take the rest of the suite with it:

```text
sudo apt-get install -y python3-tk xvfb
bash scripts/run-tests.sh
```

`scripts/run-tests.sh` loops `tests/test_*.py`, gives each module a throwaway `HOME` and `BATTLEBUDDY_HOME`, wraps it in `xvfb-run -a`, and kills a module after 120 seconds. It prints a pass/fail table and exits non-zero if any module failed.

Single module:

```text
xvfb-run -a python -m unittest tests.test_ask
```

Do not run the whole suite in one process on Linux. That path can abort with `Tcl_AsyncDelete: async handler deleted by the wrong thread`.

## CI

The `Tests` workflow (`.github/workflows/tests.yml`) runs on every pull request and every push to `main`. Ubuntu, Python 3.12, xvfb, then `bash scripts/run-tests.sh`. It is not a required check yet. The `Windows exe` workflow is unchanged and still only builds.

## Known skipped tests

None right now. If a test cannot be made deterministic without changing product code under `battlebuddy/`, mark that one test:

```text
@unittest.skip("flaky: needs product change, see #<n>")
```

and list it here.

Oorah.
