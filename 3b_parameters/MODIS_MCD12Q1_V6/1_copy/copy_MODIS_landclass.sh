#!/bin/bash
set -euo pipefail

# Copy MODIS yearly data from downloaded/existing directory to the workflow


# ============================================================
# INPUT CONTROL FILE
# ============================================================

if [ "$#" -ne 1 ]; then

    echo "Usage:"
    echo
    echo "bash make_vrt_per_year.sh /path/to/control_DOMAIN.txt"
    echo
    exit 1

fi


CONTROL_FILE=$(realpath "$1")


if [ ! -f "$CONTROL_FILE" ]; then

    echo "ERROR: Control file not found:"
    echo "$CONTROL_FILE"

    exit 1

fi



# ============================================================
# CONTROL-FILE READER
# ============================================================

read_control() {

    local setting="$1"
    local value

    value=$(
        grep -m 1 "^${setting}[[:space:]]*|" "$CONTROL_FILE" \
        | cut -d'|' -f2- \
        | cut -d'#' -f1 \
        | xargs
    )

    if [ -z "$value" ]; then

        echo "ERROR: Setting not found or empty: $setting" >&2

        exit 1

    fi

    echo "$value"
}


# ============================================================
# DOMAIN SETTINGS
# ============================================================

root_path=$(read_control "root_path")

domain_name=$(read_control "domain_name")


domain_path="${root_path}/domain_${domain_name}"


# ============================================================
# SOURCE MODIS DATA
# ============================================================

source_path=$(read_control "parameter_land_database_path")


if [ ! -d "$source_path" ]; then

    echo "ERROR: MODIS existing database directory not found:"
    echo "$source_path"

    exit 1

fi


# ============================================================
# OUTPUT VRT DIRECTORY
# ============================================================

dest_path=$(read_control "parameter_land_raw_path")


if [ "$dest_path" = "default" ]; then

    dest_path="${domain_path}/parameters/landclass/1_MODIS_raw_data"

fi


mkdir -p "${dest_path}"



#SRC="/home/zhentao/projects/rrg-h294liu/data/geospatial-data/MODIS/MCD12Q1.061"
#DST="/home/zhentao/projects/rrg-h294liu/zhentao/CAUSHydroModel/data_prepare/parameters/landclass/1_MODIS_raw_data"


find "$source_path" -type f -name "*.hdf" -print0 | xargs -0 cp -t "$dest_path"


src_count=$(find "$source_path" -type f -name "*.hdf" | wc -l)
dst_count=$(find "$dest_path" -type f -name "*.hdf" | wc -l)

echo "Number of HDF files in source:      $src_count"
echo "Number of HDF files in destination: $dst_count"
