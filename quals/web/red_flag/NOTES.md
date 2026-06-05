# Red Flag Notes

## Layout

- `service/`: deployed Docker context and source, including the real flag.
- `dist/`: player bundle with a fake flag image.
- `solve/solve.py`: reference solver.
- `build_image.py`: rebuilds the fake-flag dist image and verifies build-only obfuscation helpers are not present in the final image.

The service Dockerfile performs the obfuscated build: Go source uses
`utils.RevealString` for encoded string defaults, then `add_anti_analysis.py`
injects overlapping STT_FUNC symbols with randomized names into the stripped
binary. The packaged dist image should contain the resulting binary evidence,
not the build scripts.

## Local Run

```bash
cd service
docker compose up --build
```

The service listens on `http://localhost:34367` (container port `8080`).

## Solve

```bash
python3 solve/solve.py http://localhost:34367
```

## Package Dist

```bash
python3 build_image.py
```
