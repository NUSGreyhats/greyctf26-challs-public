# Organizer Notes

This challenge is generated and tested locally. From a clean checkout, create a
Python environment with the pinned runtime dependencies:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

Regenerate public artifacts and the private reference image:

```sh
python chall/generate.py
```

Check that public files do not contain private strings:

```sh
python chall/verify_public_no_leaks.py
```

Run the reference solver:

```sh
python solve/solution.py --seed 0
```

Before release, run seeds `0` through `10`; each reconstruction should visibly reveal the flag.
