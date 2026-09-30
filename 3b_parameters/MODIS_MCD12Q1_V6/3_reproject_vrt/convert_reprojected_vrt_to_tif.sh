
#!/bin/bash

set -euo pipefail

# Usage:
# bash convert_reprojected_vrt_to_tif.sh /path/to/control_DOMAIN.txt

if [ "$#" -ne 1 ]; then
    echo "Usage: bash $0 /path/to/control_DOMAIN.txt"
    exit 1
fi

CONTROL_FILE=$(realpath "$1")

if [ ! -f "$CONTROL_FILE" ]; then
    echo "ERROR: Control file not found: $CONTROL_FILE"
    exit 1
fi

# Read a setting from the pipe-delimited control file.
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
        echo "ERROR: Missing or empty setting: $setting" >&2
        exit 1
    fi

    echo "$value"
}

# Domain paths
root_path=$(read_control "root_path")
domain_name=$(read_control "domain_name")
domain_path="${root_path}/domain_${domain_name}"

# Reprojected VRT directory (output of reproject_vrt.sh)
source_path=$(read_control "parameter_land_vrt2_path")

if [ "$source_path" = "default" ]; then
    source_path="${domain_path}/parameters/landclass/3_vrt_epsg_4326"
fi

if [ ! -d "$source_path" ]; then
    echo "ERROR: Reprojected VRT directory not found:"
    echo "$source_path"
    exit 1
fi

# Diagnostic GeoTIFF output directory
dest_path="${domain_path}/parameters/landclass/3_vrt_epsg_4326_tif"
mkdir -p "$dest_path"

# Required GDAL commands
command -v gdal_translate >/dev/null 2>&1 || {
    echo "ERROR: gdal_translate not found."
    exit 1
}

command -v gdalinfo >/dev/null 2>&1 || {
    echo "ERROR: gdalinfo not found."
    exit 1
}

# Find all reprojected annual VRTs
mapfile -t vrt_files < <(
    find "$source_path" -maxdepth 1 -type f \
        -name "MCD12Q1_*.vrt" | sort
)

if [ "${#vrt_files[@]}" -eq 0 ]; then
    echo "ERROR: No MCD12Q1_*.vrt files found in $source_path"
    exit 1
fi

echo "============================================================"
echo "CONVERT REPROJECTED MODIS VRT FILES TO GEOTIFF"
echo "============================================================"
echo "Domain: $domain_name"
echo "Source: $source_path"
echo "Output: $dest_path"
echo "VRT files found: ${#vrt_files[@]}"
echo "GDAL version: $(gdal_translate --version)"
echo

for vrt_file in "${vrt_files[@]}"; do

    base_name=$(basename "$vrt_file" .vrt)
    tif_file="${dest_path}/${base_name}.tif"

    echo "------------------------------------------------------------"
    echo "Input : $vrt_file"
    echo "Output: $tif_file"

    # Remove an old output so that the result is regenerated.
    rm -f "$tif_file"

    gdal_translate \
        -co COMPRESS=DEFLATE \
        -co TILED=YES \
        -co BIGTIFF=IF_SAFER \
        "$vrt_file" \
        "$tif_file"

    # Verify that the output is readable.
    if [ ! -s "$tif_file" ] || ! gdalinfo "$tif_file" >/dev/null 2>&1; then
        echo "ERROR: GeoTIFF creation or validation failed:"
        echo "$tif_file"
        exit 1
    fi

    # Compare raster dimensions and band count.
    input_size=$(gdalinfo "$vrt_file" | grep '^Size is ' | head -1)
    output_size=$(gdalinfo "$tif_file" | grep '^Size is ' | head -1)

    input_bands=$(gdalinfo "$vrt_file" | grep -c '^Band ')
    output_bands=$(gdalinfo "$tif_file" | grep -c '^Band ')

    echo "Input size : $input_size"
    echo "Output size: $output_size"
    echo "Input bands: $input_bands"
    echo "Output bands: $output_bands"

    if [ "$input_size" != "$output_size" ] ||
       [ "$input_bands" -ne "$output_bands" ]; then
        echo "ERROR: Raster dimensions or band count changed."
        exit 1
    fi

    echo "Conversion successful."
    echo
done

echo "============================================================"
echo "ALL REPROJECTED VRT FILES CONVERTED SUCCESSFULLY"
echo "Output directory: $dest_path"
echo "============================================================"
