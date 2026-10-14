#!/bin/bash

#SBATCH --job-name=mizuMeanShp
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=16G
#SBATCH --time=04:00:00
#SBATCH --output=mizuMeanShp_%j.out
#SBATCH --error=mizuMeanShp_%j.err

# ============================================================
# Average KWTroutedRunoff (over time) from every
#   ${EXPERIMENT_ID}.h.*.nc
# in the mizuRoute OUTPUT_PATH and attach each average as an
# attribute of a copy of the river network shapefile,
# matching  reachID (nc)  ==  COMID (shp).
#
# Usage:
#   sh 10_add_mizuroute_mean_to_shp.sh [CONTROL_FILE]
#   for example:
#   sh 10_add_mizuroute_mean_to_shp.sh control_MERIT_73.txt
#
#   CONTROL_FILE is the file name inside 0_control_files/
#   (default: control_active.txt)
# ============================================================

set -euo pipefail


# ============================================================
# PATHS / CONTROL
# ============================================================

CONTROL_FILE="${1:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CWARHM="$(cd "${SCRIPT_DIR}/.." && pwd)"
CONTROL="${CWARHM}/0_control_files/${CONTROL_FILE}"

if [ ! -f "$CONTROL" ]; then

    echo
    echo "ERROR: control file not found:"
    echo "$CONTROL"

    exit 1
fi


# ============================================================
# CONTROL READER
# ============================================================

read_control() {

    local key="$1"

    awk -F'|' -v key="$key" '

        /^[[:space:]]*#/ {
            next
        }

        NF >= 2 {

            left=$1
            gsub(/^[ \t]+|[ \t]+$/, "", left)

            if (left == key) {

                right=$2
                sub(/#.*/, "", right)
                gsub(/^[ \t]+|[ \t]+$/, "", right)

                print right
                exit
            }
        }

    ' "$CONTROL"
}


# ============================================================
# SETTINGS
# ============================================================

ROOT_PATH="$(read_control root_path)"
DOMAIN_NAME="$(read_control domain_name)"
EXPERIMENT_ID="$(read_control experiment_id)"
DOMAIN_METHOD="$(read_control domain_definition_method)"

OUTPUT_PATH="$(read_control experiment_output_mizuRoute)"

RIVER_SHP_PATH="$(read_control river_network_shp_path)"
RIVER_SHP_NAME="$(read_control river_network_shp_name)"


# ============================================================
# DEFAULT PATHS
# ============================================================

if [ -z "$OUTPUT_PATH" ] || [ "$OUTPUT_PATH" = "default" ]; then

    OUTPUT_PATH="${ROOT_PATH}/domain_${DOMAIN_NAME}/simulations/${EXPERIMENT_ID}/mizuRoute"

fi


if [ -z "$RIVER_SHP_PATH" ] || [ "$RIVER_SHP_PATH" = "default" ]; then

    RIVER_SHP_PATH="${ROOT_PATH}/domain_${DOMAIN_NAME}/shapefiles/river_network"

fi


if [ -z "$RIVER_SHP_NAME" ] || [ "$RIVER_SHP_NAME" = "default" ]; then

    RIVER_SHP_NAME="${DOMAIN_NAME}_riverNetwork_${DOMAIN_METHOD}.shp"

fi


RIVER_SHP="${RIVER_SHP_PATH}/${RIVER_SHP_NAME}"


# ============================================================
# REQUIRED INPUT CHECKS
# ============================================================

if [ ! -d "$OUTPUT_PATH" ]; then

    echo
    echo "ERROR: mizuRoute output directory not found:"
    echo "$OUTPUT_PATH"

    exit 1
fi


if [ ! -f "$RIVER_SHP" ]; then

    echo
    echo "ERROR: river network shapefile not found:"
    echo "$RIVER_SHP"

    exit 1
fi


HISTORY_COUNT="$(
    find "$OUTPUT_PATH" \
        -maxdepth 1 \
        -type f \
        -name "${EXPERIMENT_ID}.h.*.nc" \
        | wc -l
)"


if [ "$HISTORY_COUNT" -eq 0 ]; then

    echo
    echo "ERROR: no ${EXPERIMENT_ID}.h.*.nc files found in:"
    echo "$OUTPUT_PATH"

    exit 1
fi


# ============================================================
# COPY RIVER NETWORK SHAPEFILE (all sidecar files) TO OUTPUT
# ============================================================

SHP_STEM="${RIVER_SHP_NAME%.*}"

# Output name makes clear the attributes are mean streamflow:
#   <original_name>_meanStreamflow.shp
OUT_STEM="${SHP_STEM}_meanStreamflow"

OUT_SHP="${OUTPUT_PATH}/${OUT_STEM}.shp"


rm -f "${OUTPUT_PATH}/${OUT_STEM}".{shp,shx,dbf,prj,cpg,sbn,sbx,qix,fix}


for ext in shp shx dbf prj cpg sbn sbx qix fix; do

    if [ -f "${RIVER_SHP_PATH}/${SHP_STEM}.${ext}" ]; then

        cp \
            "${RIVER_SHP_PATH}/${SHP_STEM}.${ext}" \
            "${OUTPUT_PATH}/${OUT_STEM}.${ext}"

    fi

done


# ============================================================
# REPORT
# ============================================================

echo
echo "============================================================"
echo "MEAN KWTroutedRunoff -> RIVER NETWORK SHAPEFILE"
echo "============================================================"

echo "Domain        : $DOMAIN_NAME"
echo "Experiment    : $EXPERIMENT_ID"
echo "Control       : $CONTROL"
echo "Input shp     : $RIVER_SHP"
echo "Output shp    : $OUT_SHP"
echo "History files : $HISTORY_COUNT"
echo "Start         : $(date)"

echo "============================================================"
echo


# ============================================================
# PYTHON: TIME-AVERAGE AND JOIN
# ============================================================

python3 - "$OUTPUT_PATH" "$EXPERIMENT_ID" "$OUT_SHP" <<'PYEOF'

import glob
import os
import re
import sys

import numpy as np
import pandas as pd
import xarray as xr
import geopandas as gpd

output_path, experiment_id, out_shp = sys.argv[1:4]

VAR = "KWTroutedRunoff"
ID_VAR = "reachID"
SHP_ID = "COMID"
CHUNK = 500  # time steps read at once (keeps memory low)


# ------------------------------------------------------------
# Find the history files
# ------------------------------------------------------------

files = sorted(
    glob.glob(os.path.join(output_path, f"{experiment_id}.h.*.nc"))
)

if not files:
    sys.exit("ERROR: no history files found")


def file_tag(path):
    """run1.h.2019.nc -> 2019"""
    base = os.path.basename(path)
    base = base[len(experiment_id) + len(".h."):]
    return re.sub(r"\.nc$", "", base)


# ------------------------------------------------------------
# Shapefile
# ------------------------------------------------------------

gdf = gpd.read_file(out_shp)

if SHP_ID not in gdf.columns:
    sys.exit(f"ERROR: {SHP_ID} not found in shapefile. "
             f"Columns: {list(gdf.columns)}")

comid = gdf[SHP_ID].astype("int64")

if comid.duplicated().any():
    print(f"WARNING: {int(comid.duplicated().sum())} duplicated "
          f"{SHP_ID} values in shapefile; all duplicates get the "
          f"same value.")


# ------------------------------------------------------------
# Shapefile attribute names are limited to 10 characters.
# Use Q_<tag> when it fits, otherwise Q<nnn> and keep a mapping.
# ------------------------------------------------------------

tags = [file_tag(f) for f in files]

names = []
for i, tag in enumerate(tags):
    clean = re.sub(r"[^0-9A-Za-z]", "", tag)
    cand = f"Q_{clean}"
    if len(cand) > 10 or cand in names or cand in gdf.columns:
        cand = f"Q{i + 1:03d}"
    names.append(cand)

mapping = pd.DataFrame({"attribute": names,
                        "file": [os.path.basename(f) for f in files]})


# ------------------------------------------------------------
# Time mean per file (chunked, NaN-aware), joined by reach ID
# ------------------------------------------------------------

for f, name in zip(files, names):

    with xr.open_dataset(f, decode_times=False) as ds:

        reach = ds[ID_VAR].values.astype("int64")
        da = ds[VAR]
        ntime = da.sizes["time"]

        total = np.zeros(da.sizes["seg"], dtype="float64")
        count = np.zeros(da.sizes["seg"], dtype="float64")

        for start in range(0, ntime, CHUNK):
            block = da.isel(time=slice(start, start + CHUNK)).values
            total += np.nansum(block, axis=0, dtype="float64")
            count += np.sum(np.isfinite(block), axis=0)

        with np.errstate(invalid="ignore", divide="ignore"):
            mean = np.where(count > 0, total / count, np.nan)

    series = pd.Series(mean, index=reach)
    series = series[~series.index.duplicated(keep="first")]

    gdf[name] = comid.map(series).astype("float64").values

    matched = int(gdf[name].notna().sum())
    print(f"{os.path.basename(f)}: {ntime} steps -> {name}  "
          f"({matched}/{len(gdf)} reaches matched)")


# ------------------------------------------------------------
# Write
# ------------------------------------------------------------

gdf.to_file(out_shp)

if any(n.startswith("Q") and re.fullmatch(r"Q\d{3}", n) for n in names):
    map_path = os.path.splitext(out_shp)[0] + "_attribute_map.csv"
    mapping.to_csv(map_path, index=False)
    print(f"Attribute-to-file map written: {map_path}")

print(f"\nWrote {out_shp} with attributes: {', '.join(names)}")

PYEOF


# ============================================================
# SUCCESS
# ============================================================

echo
echo "============================================================"
echo "DONE"
echo "============================================================"

echo "Shapefile : $OUT_SHP"
echo "End       : $(date)"

echo "============================================================"
