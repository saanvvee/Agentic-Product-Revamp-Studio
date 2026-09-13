#!/usr/bin/env bash
# Fetch the dataset subset described in DATA.md / PRD S7.3.
#
# Downloads into data/ and datasets/, both gitignored. Never commit the output.
# Licences: MIMII CC BY-SA 4.0, MVTec AD CC BY-NC-SA 4.0, AI4I CC BY 4.0.
# Academic, non-commercial use only.
#
# Safe to re-run: every step skips work that is already done.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATA_DIR="${REPO_ROOT}/data"
PY="${REPO_ROOT}/.venv/Scripts/python.exe"
[ -x "${PY}" ] || PY="${REPO_ROOT}/.venv/bin/python"

mkdir -p "${DATA_DIR}"

echo "==> AI4I 2020 (telemetry, ~500 KB, CC BY 4.0)"
if [ -f "${DATA_DIR}/ai4i2020.csv" ]; then
  echo "    already present, skipping"
else
  "${PY}" - <<'PYEOF'
from pathlib import Path
from ucimlrepo import fetch_ucirepo

root = Path(__file__).resolve().parent if "__file__" in dir() else Path.cwd()
out = Path("data/ai4i2020.csv")
ds = fetch_ucirepo(id=601)
df = ds.data.original if hasattr(ds.data, "original") else ds.data.features
df.to_csv(out, index=False)
print(f"    wrote {out} rows={len(df)}")
PYEOF
fi

echo
echo "==> MVTec AD (vision, ~1 GB for two categories, CC BY-NC-SA 4.0)"
echo "    Categories: metal_nut, screw (PRD S7.3 v1.1)"
if [ -d "${REPO_ROOT}/datasets/MVTecAD/metal_nut" ]; then
  echo "    already present, skipping"
else
  echo "    anomalib downloads to ./datasets/ on first use:"
  echo "      from anomalib.data import MVTecAD"
  echo "      MVTecAD(category='metal_nut').prepare_data()"
  echo
  echo "    If the official mvtec.com URL stalls, use the mirror that keeps the"
  echo "    ORIGINAL directory layout (see DATA.md -- the Voxel51 mirror is in"
  echo "    FiftyOne format and anomalib cannot read it directly):"
  echo "      hf download MSherbinii/mvtec-ad-metal-nut --repo-type dataset \\"
  echo "        --local-dir datasets/MVTecAD"
fi

echo
echo "==> MIMII (audio, ~2.5 GB, CC BY-SA 4.0)"
echo "    +6 dB SNR, fan only, model IDs 00/02/04/06 (PRD S7.3 v1.1)"
if [ -d "${DATA_DIR}/mimii/fan" ]; then
  echo "    already present, skipping"
else
  echo "    Manual step: download the +6 dB fan archive from"
  echo "      https://zenodo.org/records/3384388"
  echo "    and extract to ${DATA_DIR}/mimii/fan/"
  echo
  echo "    We take ONE SNR level and ONE machine type deliberately. All three"
  echo "    SNR levels would be tens of GB and gain us nothing (PRD S7.3)."
fi

echo
echo "Done. Verify nothing is staged for commit:"
echo "    git status --short"
