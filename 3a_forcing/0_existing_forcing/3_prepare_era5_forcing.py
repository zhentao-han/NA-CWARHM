#!/usr/bin/env python3
# coding: utf-8

# Prepare "ERA5-type" forcing for the NWAM-SUMMA workflow.
#
# MULTIBASIN VERSION
# ------------------
# This script does NOT use control_active.txt.
#
# Each of the five variables is read from its OWN folder, with its OWN
# variable name, both set in the control file. Files are named YYYYMM.nc
# in every folder. Grids are NOT regridded: the output keeps the native
# grid of the input files. All five inputs must share the same grid and
# time axis (otherwise the script stops with an error).
#
# Control-file settings (in addition to the usual domain/time/space ones):
#
#   forcing_airpres_path   | <folder>
#   forcing_airpres_var    | <variable name inside the files>
#   forcing_LWRadAtm_path  | <folder>
#   forcing_LWRadAtm_var   | <variable name inside the files>
#   forcing_SWRadAtm_path  | <folder>
#   forcing_SWRadAtm_var   | <variable name inside the files>
#   forcing_spechum_path   | <folder>
#   forcing_spechum_var    | <variable name inside the files>
#   forcing_windspd_path   | <folder>
#   forcing_windspd_var    | <variable name inside the files>
#
# Optional:
#   forcing_buffer         | 0.25     # degrees added around forcing_raw_space
#
# Output variables are always named airpres, LWRadAtm, SWRadAtm, spechum
# and windspd. Units are not converted (same as the original script).
#
# Usage:
#
#   python 3_prepare_era5_forcing.py CONTROL_FILE
#
#       -> process all months in forcing_raw_time
#
#   python 3_prepare_era5_forcing.py CONTROL_FILE YEAR MONTH
#
#       -> process one month only
#
# Example:
#
#   python 3_prepare_era5_forcing.py \
#       ../../0_control_files/control_MERIT_717.txt \
#       1950 1

from pathlib import Path
from datetime import datetime
from shutil import copyfile
import sys

import xarray as xr


# =====================================================================
# COMMAND-LINE ARGUMENTS
# =====================================================================

if len(sys.argv) not in (2, 4):

    raise SystemExit(
        "Usage:\n"
        "  python 3_prepare_era5_forcing.py CONTROL_FILE\n"
        "or\n"
        "  python 3_prepare_era5_forcing.py CONTROL_FILE YEAR MONTH"
    )


controlPath = Path(
    sys.argv[1]
).expanduser().resolve()


if not controlPath.exists():

    raise FileNotFoundError(
        f"Control file not found:\n"
        f"{controlPath}"
    )


# =====================================================================
# CONTROL FILE FUNCTIONS
# =====================================================================

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

            left, right = stripped.split(
                "|",
                1
            )

            if left.strip() != setting:
                continue

            return (
                right
                .split("#", 1)[0]
                .strip()
            )

    raise ValueError(
        f"Setting '{setting}' not found in:\n"
        f"{file}"
    )


def make_default_path(suffix):

    rootPath = Path(
        read_from_control(
            controlPath,
            "root_path"
        )
    )

    domainName = read_from_control(
        controlPath,
        "domain_name"
    )

    return (
        rootPath
        / f"domain_{domainName}"
        / suffix
    )


# =====================================================================
# DOMAIN
# =====================================================================

domainName = read_from_control(
    controlPath,
    "domain_name"
)


# =====================================================================
# VARIABLES: OUTPUT NAME -> (SOURCE FOLDER, SOURCE VARIABLE NAME)
# =====================================================================

keep_variables = [
    "airpres",
    "LWRadAtm",
    "SWRadAtm",
    "spechum",
    "windspd",
]


sources = {}

for variable in keep_variables:

    sources[variable] = {

        "path": Path(
            read_from_control(
                controlPath,
                f"forcing_{variable}_path"
            )
        ),

        "var": read_from_control(
            controlPath,
            f"forcing_{variable}_var"
        ),
    }


for variable, source in sources.items():

    if not source["path"].exists():

        raise FileNotFoundError(
            f"Directory for {variable} not found:\n"
            f"{source['path']}"
        )


# =====================================================================
# PATHS
# =====================================================================

forcingRawPath = read_from_control(
    controlPath,
    "forcing_raw_path"
)


if forcingRawPath == "default":

    forcingRawPath = make_default_path(
        "forcing/1_raw_data"
    )

else:

    forcingRawPath = Path(
        forcingRawPath
    )


outputPath = (
    forcingRawPath
    / "ERA5_prepared"
)


outputPath.mkdir(
    parents=True,
    exist_ok=True
)


# =====================================================================
# TIME PERIOD
# =====================================================================

years = read_from_control(
    controlPath,
    "forcing_raw_time"
)


def parse_year_month(text, default_month):
    """
    Accept "YYYY" (month = default_month) or "YYYY-MM".
    """
    text = text.strip()

    if "-" in text:
        year_text, month_text = text.split("-", 1)
        return int(year_text), int(month_text)

    return int(text), default_month


try:

    startText, endText = [
        x.strip()
        for x in years.split(",")
    ]

    startYear, startMonth = parse_year_month(startText, 1)
    endYear, endMonth = parse_year_month(endText, 12)

except Exception as exc:

    raise ValueError(
        "forcing_raw_time must have format:\n"
        "START,END where each is YYYY or YYYY-MM.\n"
        "For example:\n"
        "1950,2019  (January 1950 - December 2019)\n"
        "1950-03,2019-11  (March 1950 - November 2019)"
    ) from exc


if not (
    1 <= startMonth <= 12
    and 1 <= endMonth <= 12
):

    raise ValueError(
        f"Invalid month in forcing_raw_time: {years}"
    )


if (startYear, startMonth) > (endYear, endMonth):

    raise ValueError(
        f"Invalid forcing_raw_time: {years}"
    )


periodText = (
    f"{startYear}-{startMonth:02d} to "
    f"{endYear}-{endMonth:02d}"
)


# =====================================================================
# SPATIAL EXTENT
# =====================================================================

space = read_from_control(
    controlPath,
    "forcing_raw_space"
)


try:

    latMax, lonMin, latMin, lonMax = [
        float(x.strip())
        for x in space.split("/")
    ]

except Exception as exc:

    raise ValueError(
        "forcing_raw_space must have format:\n"
        "LAT_MAX/LON_MIN/LAT_MIN/LON_MAX"
    ) from exc


if latMin >= latMax:

    raise ValueError(
        "Invalid forcing_raw_space: "
        "latMin must be smaller than latMax."
    )


if lonMin >= lonMax:

    raise ValueError(
        "Invalid forcing_raw_space: "
        "lonMin must be smaller than lonMax."
    )


# Buffer around the basin box (degrees). Default is the original
# one-ERA5-grid-cell value (0.25); override with forcing_buffer.

try:

    buffer = float(
        read_from_control(
            controlPath,
            "forcing_buffer"
        )
    )

except ValueError as exc:

    if "not found" in str(exc):

        buffer = 0.25

    else:

        raise


subset_lat_max = (
    latMax + buffer
)

subset_lat_min = (
    latMin - buffer
)

subset_lon_min = (
    lonMin - buffer
)

subset_lon_max = (
    lonMax + buffer
)


# =====================================================================
# HELPER: OPEN ONE VARIABLE, STANDARDISE AND SUBSET
# =====================================================================

def load_variable(outName, ym):
    """
    Open <path>/YYYYMM.nc for one variable, rename the source variable
    to its output name, standardise coordinate names, subset to the
    basin box and return it as a float32 DataArray (native grid).
    """

    source = sources[outName]

    inputFile = (
        source["path"]
        / f"{ym}.nc"
    )

    if not inputFile.exists():

        return None, inputFile

    with xr.open_dataset(
        inputFile
    ) as ds:

        # Accept lat/lon as well as latitude/longitude.

        rename = {}

        if (
            "lat" in ds.variables
            and "latitude" not in ds.variables
        ):
            rename["lat"] = "latitude"

        if (
            "lon" in ds.variables
            and "longitude" not in ds.variables
        ):
            rename["lon"] = "longitude"

        if rename:
            ds = ds.rename(rename)

        # Check coordinates.

        missing_coordinates = [
            coordinate
            for coordinate in (
                "time",
                "latitude",
                "longitude",
            )
            if coordinate not in ds.variables
        ]

        if missing_coordinates:

            raise ValueError(
                f"Missing required coordinates "
                f"{missing_coordinates} in {inputFile}"
            )

        # Check variable.

        if source["var"] not in ds.variables:

            raise ValueError(
                f"Variable '{source['var']}' (for {outName}) "
                f"not found in {inputFile}\n"
                f"Available variables: "
                f"{list(ds.variables)}"
            )

        # Spatial subset; handle either latitude ordering.

        latitude = ds["latitude"].values

        if latitude[0] > latitude[-1]:

            lat_slice = slice(
                subset_lat_max,
                subset_lat_min
            )

        else:

            lat_slice = slice(
                subset_lat_min,
                subset_lat_max
            )

        ds_sub = ds.sel(
            latitude=lat_slice,
            longitude=slice(
                subset_lon_min,
                subset_lon_max
            )
        )

        if ds_sub.sizes.get("latitude", 0) == 0:

            raise ValueError(
                f"Latitude subset is empty for "
                f"{outName} {ym}. "
                f"Check forcing_raw_space."
            )

        if ds_sub.sizes.get("longitude", 0) == 0:

            raise ValueError(
                f"Longitude subset is empty for "
                f"{outName} {ym}. "
                f"Check forcing_raw_space."
            )

        if ds_sub.sizes.get("time", 0) == 0:

            raise ValueError(
                f"Time dimension is empty for "
                f"{outName} {ym}."
            )

        da = (
            ds_sub[source["var"]]
            .astype("float32")
            .rename(outName)
            .load()
        )

    return da, inputFile


# =====================================================================
# SELECT MONTHS TO PROCESS
# =====================================================================

if len(sys.argv) == 2:

    months_to_process = [
        (year, month)
        for year in range(
            startYear,
            endYear + 1
        )
        for month in range(
            1,
            13
        )
        if (startYear, startMonth)
        <= (year, month)
        <= (endYear, endMonth)
    ]


else:

    try:

        runYear = int(
            sys.argv[2]
        )

        runMonth = int(
            sys.argv[3]
        )

    except ValueError as exc:

        raise ValueError(
            "YEAR and MONTH must be integers."
        ) from exc


    if (
        runMonth < 1
        or runMonth > 12
    ):

        raise ValueError(
            "Month must be between 1 and 12."
        )


    if not (
        (startYear, startMonth)
        <= (runYear, runMonth)
        <= (endYear, endMonth)
    ):

        raise ValueError(
            f"{runYear}-{runMonth:02d} is outside "
            f"forcing_raw_time {periodText}"
        )


    months_to_process = [
        (
            runYear,
            runMonth
        )
    ]


# =====================================================================
# REPORT CONFIGURATION
# =====================================================================

print()

print("=" * 70)
print("PREPARE ERA5-TYPE FORCING")
print("=" * 70)

print(
    f"Domain       : {domainName}"
)

print(
    f"Control file : {controlPath}"
)

for variable in keep_variables:

    print(
        f"{variable:<13}: "
        f"{sources[variable]['path']} "
        f"[{sources[variable]['var']}]"
    )

print(
    f"Output       : {outputPath}"
)

print(
    f"Forcing years: "
    f"{periodText}"
)

print(
    f"Months this run: "
    f"{len(months_to_process)}"
)

print(
    "Subset bounds:"
)

print(
    f"  latitude : "
    f"{subset_lat_min} to "
    f"{subset_lat_max}"
)

print(
    f"  longitude: "
    f"{subset_lon_min} to "
    f"{subset_lon_max}"
)

print()


# =====================================================================
# PROCESS MONTHS
# =====================================================================

processed_months = []
skipped_months = []
missing_months = []


for year, month in months_to_process:

    ym = (
        f"{year}"
        f"{month:02d}"
    )


    outputFile = (
        outputPath
        / f"ERA5_SUMMA_{ym}.nc"
    )


    print(
        f"Processing {ym}"
    )


    # -----------------------------------------------------------------
    # CHECK INPUTS / EXISTING OUTPUT
    # -----------------------------------------------------------------

    missing_files = [
        sources[variable]["path"] / f"{ym}.nc"
        for variable in keep_variables
        if not (
            sources[variable]["path"] / f"{ym}.nc"
        ).exists()
    ]


    if missing_files:

        for missing_file in missing_files:

            print(
                f"  Missing: "
                f"{missing_file}"
            )

        missing_months.append(
            ym
        )

        continue


    if outputFile.exists():

        print(
            f"  Output already exists: "
            f"{outputFile}"
        )

        skipped_months.append(
            ym
        )

        continue


    # -----------------------------------------------------------------
    # LOAD EACH VARIABLE FROM ITS OWN FILE
    # -----------------------------------------------------------------

    arrays = {}

    for variable in keep_variables:

        da, _ = load_variable(
            variable,
            ym
        )

        arrays[variable] = da


    # -----------------------------------------------------------------
    # VERIFY COMMON TIME / GRID (no regridding is done)
    # -----------------------------------------------------------------

    reference = arrays[
        keep_variables[0]
    ]

    for variable in keep_variables[1:]:

        for coordinate in (
            "time",
            "latitude",
            "longitude",
        ):

            if not reference[
                coordinate
            ].equals(
                arrays[variable][coordinate]
            ):

                raise ValueError(
                    f"{coordinate} mismatch between "
                    f"{keep_variables[0]} and {variable} "
                    f"for {ym}. All variables must share "
                    f"the same grid and time axis "
                    f"(no regridding is performed)."
                )


    # -----------------------------------------------------------------
    # OUTPUT DATASET
    # -----------------------------------------------------------------

    ds_out = xr.Dataset(
        {
            variable: arrays[variable]
            for variable in keep_variables
        }
    )


    # -----------------------------------------------------------------
    # GLOBAL METADATA
    # -----------------------------------------------------------------

    ds_out.attrs[
        "History"
    ] = (
        "Prepared forcing "
        "for NWAM-SUMMA"
    )


    ds_out.attrs[
        "Reason"
    ] = (
        "Domain subset of airpres, LWRadAtm, SWRadAtm, "
        "spechum and windspd, each read from its own "
        "source. Precipitation and temperature are "
        "prepared separately."
    )


    ds_out.attrs[
        "Domain"
    ] = (
        domainName
    )


    ds_out.attrs[
        "Control file"
    ] = (
        str(
            controlPath
        )
    )


    for variable in keep_variables:

        ds_out.attrs[
            f"Source {variable}"
        ] = (
            f"{sources[variable]['path']} "
            f"variable {sources[variable]['var']}"
        )


    # -----------------------------------------------------------------
    # COMPRESSION
    # -----------------------------------------------------------------

    encoding = {}


    for variable in keep_variables:

        encoding[
            variable
        ] = {
            "dtype": "float32",
            "zlib": True,
            "complevel": 4,
        }


    # -----------------------------------------------------------------
    # WRITE OUTPUT
    # -----------------------------------------------------------------

    ds_out.to_netcdf(
        outputFile,
        encoding=encoding
    )


    ds_out.close()


    processed_months.append(
        ym
    )


    print(
        f"  Created: "
        f"{outputFile}"
    )


# =====================================================================
# LOGGING
# =====================================================================

logFolder = (
    outputPath
    / "_workflow_log"
)


logFolder.mkdir(
    parents=True,
    exist_ok=True
)


thisFile = Path(
    __file__
).name


try:

    copyfile(
        Path(
            __file__
        ).resolve(),
        logFolder
        / thisFile
    )

except Exception as exc:

    print(
        "Warning: could not copy "
        f"script to log folder: {exc}"
    )


now = datetime.now()


if len(
    months_to_process
) == 1:

    run_label = (
        months_to_process[0][0]
        * 100
        + months_to_process[0][1]
    )


    logFile = (
        logFolder
        / (
            f"{now:%Y%m%d_%H%M%S}_"
            f"prepare_era5_{run_label}.txt"
        )
    )


else:

    logFile = (
        logFolder
        / (
            f"{now:%Y%m%d_%H%M%S}_"
            "prepare_era5_forcing_log.txt"
        )
    )


with open(
    logFile,
    "w"
) as file:

    file.write(
        f"Log generated by {thisFile} on "
        f"{now:%Y/%m/%d %H:%M:%S}\n"
    )

    file.write(
        f"Domain: "
        f"{domainName}\n"
    )

    file.write(
        f"Control file: "
        f"{controlPath}\n"
    )

    for variable in keep_variables:

        file.write(
            f"Source {variable}: "
            f"{sources[variable]['path']} "
            f"[{sources[variable]['var']}]\n"
        )

    file.write(
        f"Output directory: "
        f"{outputPath}\n"
    )

    file.write(
        f"Configured forcing period: "
        f"{periodText}\n"
    )

    file.write(
        f"Months requested: "
        f"{len(months_to_process)}\n"
    )

    file.write(
        f"Months created: "
        f"{len(processed_months)}\n"
    )

    file.write(
        "Months skipped because output "
        f"already existed: "
        f"{len(skipped_months)}\n"
    )

    file.write(
        f"Missing input months: "
        f"{len(missing_months)}\n"
    )

    file.write(
        "Retained airpres, LWRadAtm, "
        "SWRadAtm, spechum and windspd "
        "(native grid, no regridding).\n"
    )


# =====================================================================
# FINAL SUMMARY
# =====================================================================

print()

print("=" * 70)
print("FORCING PREPARATION COMPLETED")
print("=" * 70)

print(
    f"Domain          : "
    f"{domainName}"
)

print(
    f"Months requested: "
    f"{len(months_to_process)}"
)

print(
    f"Months created  : "
    f"{len(processed_months)}"
)

print(
    f"Months skipped  : "
    f"{len(skipped_months)}"
)

print(
    f"Missing inputs  : "
    f"{len(missing_months)}"
)

print(
    f"Output directory: "
    f"{outputPath}"
)

print(
    f"Workflow log    : "
    f"{logFile}"
)
