#!/usr/bin/env python
# coding: utf-8

from pathlib import Path
from datetime import datetime
from shutil import copy2
import sys

import numpy as np
from osgeo import gdal


# ============================================================
# GDAL MEMORY SETTINGS
# ============================================================

# Keep GDAL cache small so it cannot consume several GB.
gdal.SetConfigOption("GDAL_CACHEMAX", "512")

# Avoid extra memory from multithreaded GTiff operations.
gdal.SetConfigOption("GDAL_NUM_THREADS", "1")


# ============================================================
# BLOCK SIZE
# ============================================================

# 1024 x 1024 = about 1 MB per uint8 raster.
# Even with many MODIS bands this remains small.
BLOCK_X = 1024
BLOCK_Y = 1024


# ============================================================
# INPUT
# ============================================================

if len(sys.argv) != 2:
    raise SystemExit(
        "Usage:\n"
        "python find_mode_landclass.py "
        "/path/to/control_DOMAIN.txt"
    )

CONTROL_FILE = Path(sys.argv[1]).expanduser().resolve()

if not CONTROL_FILE.exists():
    raise FileNotFoundError(
        f"Control file not found:\n{CONTROL_FILE}"
    )


# ============================================================
# CONTROL FILE
# ============================================================

def read_from_control(file, setting):

    with open(file) as contents:

        for line in contents:

            stripped = line.strip()

            if (
                not stripped
                or stripped.startswith("#")
                or "|" not in stripped
            ):
                continue

            left, right = stripped.split("|", 1)

            if left.strip() != setting:
                continue

            value = (
                right
                .split("#", 1)[0]
                .strip()
            )

            if value == "":
                raise ValueError(
                    f"Setting is empty: {setting}"
                )

            return value

    raise ValueError(
        f"Setting not found: {setting}"
    )


def make_default_path(suffix):

    root_path = Path(
        read_from_control(
            CONTROL_FILE,
            "root_path"
        )
    )

    domain_name = read_from_control(
        CONTROL_FILE,
        "domain_name"
    )

    return (
        root_path
        / f"domain_{domain_name}"
        / suffix
    )


def resolve_path(setting, default_suffix):

    value = read_from_control(
        CONTROL_FILE,
        setting
    )

    if value == "default":
        return make_default_path(
            default_suffix
        )

    return (
        Path(value)
        .expanduser()
        .resolve()
    )


# ============================================================
# PATHS
# ============================================================

domain_name = read_from_control(
    CONTROL_FILE,
    "domain_name"
)

land_class_path = resolve_path(
    "parameter_land_tif_path",
    "parameters/landclass/6_tif_multiband"
)

mode_land_class_path = resolve_path(
    "parameter_land_mode_path",
    "parameters/landclass/7_mode_land_class"
)

mode_land_class_path.mkdir(
    parents=True,
    exist_ok=True
)

dest_file_name = read_from_control(
    CONTROL_FILE,
    "parameter_land_tif_name"
)

dest_file = (
    mode_land_class_path
    / dest_file_name
)


# ============================================================
# FIND SOURCE
# ============================================================

source_files = sorted(
    land_class_path.glob("*.tif")
)

if len(source_files) == 0:
    raise RuntimeError(
        "No MODIS TIFF found in:\n"
        f"{land_class_path}"
    )

if len(source_files) != 1:
    raise RuntimeError(
        "Expected exactly one MODIS TIFF, "
        f"but found {len(source_files)}."
    )

source_file = source_files[0]


# ============================================================
# OPEN SOURCE
# ============================================================

src_ds = gdal.Open(
    str(source_file),
    gdal.GA_ReadOnly
)

if src_ds is None:
    raise RuntimeError(
        f"Could not open source TIFF:\n{source_file}"
    )

num_bands = src_ds.RasterCount
ncols = src_ds.RasterXSize
nrows = src_ds.RasterYSize

geo_transform = src_ds.GetGeoTransform()
projection = src_ds.GetProjection()

if not projection:
    raise RuntimeError(
        "Source raster has no projection."
    )


# ============================================================
# NODATA
# ============================================================

nodata_values = []

for band_number in range(1, num_bands + 1):

    band = src_ds.GetRasterBand(
        band_number
    )

    nodata_values.append(
        band.GetNoDataValue()
    )

defined_nodata = [
    value
    for value in nodata_values
    if value is not None
]

if defined_nodata:

    nodata = int(
        defined_nodata[0]
    )

    for value in defined_nodata:

        if int(value) != nodata:

            raise RuntimeError(
                "MODIS bands have "
                "inconsistent NoData values."
            )

else:

    # Standard MODIS fill value.
    nodata = 255


if not 0 <= nodata <= 255:
    raise RuntimeError(
        f"Invalid NoData value: {nodata}"
    )


print()
print("=" * 70)
print("CREATE REPRESENTATIVE MODIS LAND-CLASS RASTER")
print("=" * 70)
print()
print(f"Domain       : {domain_name}")
print(f"Source TIFF  : {source_file}")
print(f"Output TIFF  : {dest_file}")
print(f"Raster size  : {ncols} x {nrows}")
print(f"Bands        : {num_bands}")
print(f"NoData       : {nodata}")
print(
    f"Block size   : {BLOCK_X} x {BLOCK_Y}"
)
print()


# ============================================================
# CREATE OUTPUT
# ============================================================

if dest_file.exists():
    dest_file.unlink()

driver = gdal.GetDriverByName("GTiff")

if driver is None:
    raise RuntimeError(
        "GTiff driver is unavailable."
    )

dst_ds = driver.Create(
    str(dest_file),
    ncols,
    nrows,
    1,
    gdal.GDT_Byte,
    options=[
        "COMPRESS=DEFLATE",
        "TILED=YES",
        "BIGTIFF=IF_SAFER",
        "NUM_THREADS=1",
    ],
)

if dst_ds is None:
    raise RuntimeError(
        f"Could not create:\n{dest_file}"
    )

dst_ds.SetGeoTransform(
    geo_transform
)

dst_ds.SetProjection(
    projection
)

dst_band = dst_ds.GetRasterBand(1)

dst_band.SetNoDataValue(
    float(nodata)
)


# ============================================================
# SINGLE-BAND FAST PATH
# ============================================================

if num_bands == 1:

    print(
        "Only one MODIS band is present."
    )

    print(
        "Using streaming GDAL translation "
        "instead of loading the raster into NumPy."
    )

    dst_ds = None

    translate_options = gdal.TranslateOptions(
        format="GTiff",
        bandList=[1],
        outputType=gdal.GDT_Byte,
        creationOptions=[
            "COMPRESS=DEFLATE",
            "TILED=YES",
            "BIGTIFF=IF_SAFER",
            "NUM_THREADS=1",
        ],
    )

    result = gdal.Translate(
        str(dest_file),
        str(source_file),
        options=translate_options,
    )

    if result is None:
        raise RuntimeError(
            "gdal.Translate failed."
        )

    result = None
    src_ds = None

else:

    # ========================================================
    # MULTI-BAND BLOCKWISE MODE
    # ========================================================

    print(
        f"Calculating modal class across "
        f"{num_bands} bands block-by-block."
    )

    for yoff in range(
        0,
        nrows,
        BLOCK_Y
    ):

        ysize = min(
            BLOCK_Y,
            nrows - yoff
        )

        for xoff in range(
            0,
            ncols,
            BLOCK_X
        ):

            xsize = min(
                BLOCK_X,
                ncols - xoff
            )

            # --------------------------------------------
            # Read one block from all bands
            # --------------------------------------------

            block_stack = np.empty(
                (
                    num_bands,
                    ysize,
                    xsize
                ),
                dtype=np.uint8
            )

            for band_number in range(
                1,
                num_bands + 1
            ):

                band = src_ds.GetRasterBand(
                    band_number
                )

                data = band.ReadAsArray(
                    xoff,
                    yoff,
                    xsize,
                    ysize
                )

                if data is None:
                    raise RuntimeError(
                        f"Could not read band "
                        f"{band_number}."
                    )

                block_stack[
                    band_number - 1
                ] = data

            # --------------------------------------------
            # Calculate block mode
            # --------------------------------------------

            mode_block = np.full(
                (ysize, xsize),
                nodata,
                dtype=np.uint8
            )

            best_count = np.zeros(
                (ysize, xsize),
                dtype=np.uint16
            )

            # np.unique() operates only on this block,
            # not the entire North American raster.
            classes = np.unique(
                block_stack
            )

            # np.unique returns sorted values.
            # Therefore using ">" preserves the lower
            # class number in an exact tie.

            for land_class in classes:

                land_class = int(
                    land_class
                )

                if land_class == nodata:
                    continue

                counts = np.sum(
                    block_stack == land_class,
                    axis=0,
                    dtype=np.uint16
                )

                replace = (
                    counts > best_count
                )

                mode_block[
                    replace
                ] = np.uint8(
                    land_class
                )

                best_count[
                    replace
                ] = counts[
                    replace
                ]

            # --------------------------------------------
            # Write block
            # --------------------------------------------

            dst_band.WriteArray(
                mode_block,
                xoff=xoff,
                yoff=yoff
            )

    dst_band.FlushCache()
    dst_ds.FlushCache()

    dst_ds = None
    src_ds = None


# ============================================================
# VERIFY OUTPUT
# ============================================================

check_ds = gdal.Open(
    str(dest_file),
    gdal.GA_ReadOnly
)

if check_ds is None:
    raise RuntimeError(
        "Output raster cannot be opened."
    )

if check_ds.RasterXSize != ncols:
    raise RuntimeError(
        "Output width changed."
    )

if check_ds.RasterYSize != nrows:
    raise RuntimeError(
        "Output height changed."
    )

if check_ds.RasterCount != 1:
    raise RuntimeError(
        "Output does not have exactly one band."
    )

check_band = check_ds.GetRasterBand(1)

if check_band.GetNoDataValue() != float(nodata):
    raise RuntimeError(
        "Output NoData value changed."
    )


# ============================================================
# BLOCKWISE QA
# ============================================================

class_set = set()
nodata_count = 0

for yoff in range(
    0,
    nrows,
    BLOCK_Y
):

    ysize = min(
        BLOCK_Y,
        nrows - yoff
    )

    for xoff in range(
        0,
        ncols,
        BLOCK_X
    ):

        xsize = min(
            BLOCK_X,
            ncols - xoff
        )

        array = check_band.ReadAsArray(
            xoff,
            yoff,
            xsize,
            ysize
        )

        if array is None:
            raise RuntimeError(
                "Could not read output block."
            )

        values = np.unique(array)

        class_set.update(
            int(value)
            for value in values
            if int(value) != nodata
        )

        nodata_count += int(
            np.count_nonzero(
                array == nodata
            )
        )


if not class_set:
    raise RuntimeError(
        "Output contains no valid land classes."
    )

print()
print("=" * 70)
print("OUTPUT QA")
print("=" * 70)
print()
print(
    f"Classes      : {sorted(class_set)}"
)
print(
    f"NoData cells : {nodata_count}"
)


# ============================================================
# CLOSE
# ============================================================

check_ds = None


# ============================================================
# WORKFLOW LOG
# ============================================================

log_folder = (
    mode_land_class_path
    / "_workflow_log"
)

log_folder.mkdir(
    parents=True,
    exist_ok=True
)

now = datetime.now()

log_file = (
    log_folder
    / (
        f"{now:%Y%m%d_%H%M%S}_"
        "create_mode_landclass.txt"
    )
)

with open(log_file, "w") as file:

    file.write(
        f"Log generated on "
        f"{now:%Y/%m/%d %H:%M:%S}\n"
    )

    file.write(
        f"Domain: {domain_name}\n"
    )

    file.write(
        f"Source raster: {source_file}\n"
    )

    file.write(
        f"Output raster: {dest_file}\n"
    )

    file.write(
        f"Raster dimensions: "
        f"{ncols} x {nrows}\n"
    )

    file.write(
        f"MODIS bands: {num_bands}\n"
    )

    file.write(
        f"NoData value: {nodata}\n"
    )

    file.write(
        f"Block size: "
        f"{BLOCK_X} x {BLOCK_Y}\n"
    )

    file.write(
        f"Valid output classes: "
        f"{sorted(class_set)}\n"
    )

    file.write(
        f"NoData cells: "
        f"{nodata_count}\n"
    )

copy2(
    Path(__file__).resolve(),
    log_folder / Path(__file__).name
)

copy2(
    CONTROL_FILE,
    log_folder / CONTROL_FILE.name
)


print()
print("=" * 70)
print("MODIS REPRESENTATIVE LAND CLASS COMPLETED")
print("=" * 70)
print()
print(f"Output: {dest_file}")
print(f"Log   : {log_file}")
