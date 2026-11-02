#!/usr/bin/env python
# coding: utf-8

# Prepare MSWEP precipitation + temperature forcing for the NWAM-SUMMA workflow.
# (Adapted from the EM-Earth version of this script.)
#
# MULTI-BASIN SAFE
# ----------------
# This script does NOT read control_active.txt.
# A domain-specific control file must be supplied explicitly.
#
# Usage:
#
#   Process all months in forcing_raw_time:
#       python 1_prepare_emearth_forcing.py CONTROL_FILE
#
#   Process one month:
#       python 1_prepare_emearth_forcing.py CONTROL_FILE YEAR MONTH
#
#   Example:
#       python 1_prepare_emearth_forcing.py \
#           ../../0_control_files/control_MERIT_717.txt 1950 1
#
# Control-file settings used by this script
# -----------------------------------------
#   domain_name           | <name>
#   root_path             | <path>
#   forcing_raw_path      | default   (or an explicit path)
#   forcing_raw_time      | START_YEAR,END_YEAR
#   forcing_raw_space     | LAT_MAX/LON_MIN/LAT_MIN/LON_MAX
#
#   forcing_prcp_path     | /home/zhentao/scratch/data/temp/MSWEP/Past/Daily
#   forcing_tmean_path    | <folder containing the temperature files>
#
# Optional (defaults shown):
#   forcing_prcp_var      | precipitation   # variable name in precip files
#   forcing_prcp_units    | mm/hour         # mm/hour or mm/day
#   forcing_tmean_var     | tmean           # variable name in temperature files
#   forcing_tmean_units   | degC            # degC or K
#
# Input files are expected as:
#   <forcing_prcp_path>/YYYYMM.nc
#   <forcing_tmean_path>/YYYYMM.nc

from pathlib import Path
from datetime import datetime
from shutil import copyfile
import sys

import numpy as np
import xarray as xr


# ---------------------------------------------------------------------
# COMMAND-LINE ARGUMENTS
# ---------------------------------------------------------------------

if len(sys.argv) not in [2, 4]:
    raise SystemExit(
        "Usage:\n"
        "python 1_prepare_emearth_forcing.py CONTROL_FILE\n"
        "or\n"
        "python 1_prepare_emearth_forcing.py CONTROL_FILE YEAR MONTH"
    )

controlPath = Path(sys.argv[1]).expanduser().resolve()

if not controlPath.exists():
    raise FileNotFoundError(f"Control file not found:\n{controlPath}")

if not controlPath.is_file():
    raise RuntimeError(f"Control-file path is not a file:\n{controlPath}")


# ---------------------------------------------------------------------
# CONTROL FILE
# ---------------------------------------------------------------------

def read_from_control(file, setting):
    """
    Read one setting using exact control-key matching.
    """
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

            return right.split("#", 1)[0].strip()

    raise ValueError(f"Setting '{setting}' not found in:\n{file}")


def read_from_control_default(file, setting, default):
    """
    Read one optional setting; return default if it is absent.
    """
    try:
        return read_from_control(file, setting)
    except ValueError:
        return default


def make_default_path(suffix):
    """
    Construct a standard path inside the active domain.
    """
    rootPath = Path(read_from_control(controlPath, "root_path"))
    domainName = read_from_control(controlPath, "domain_name")
    return rootPath / f"domain_{domainName}" / suffix


# ---------------------------------------------------------------------
# DOMAIN
# ---------------------------------------------------------------------

domainName = read_from_control(controlPath, "domain_name")


# ---------------------------------------------------------------------
# INPUT SOURCES (read from the control file)
# ---------------------------------------------------------------------

prcpPath = Path(read_from_control(controlPath, "forcing_prcp_path"))
tmeanPath = Path(read_from_control(controlPath, "forcing_tmean_path"))

prcpVar = read_from_control_default(
    controlPath, "forcing_prcp_var", "precipitation"
)
tmeanVar = read_from_control_default(
    controlPath, "forcing_tmean_var", "tmean"
)

prcpUnits = read_from_control_default(
    controlPath, "forcing_prcp_units", "mm/hour"
)
tmeanUnits = read_from_control_default(
    controlPath, "forcing_tmean_units", "degC"
)

# Conversion of precipitation to kg m-2 s-1 (1 mm water = 1 kg m-2).
precip_divisor = {
    "mm/day": 86400.0,
    "mm/hour": 3600.0,
}

if prcpUnits not in precip_divisor:
    raise ValueError(
        "Invalid forcing_prcp_units setting:\n"
        f"  {prcpUnits}\n\n"
        "Allowed values are:\n"
        "  mm/day\n"
        "  mm/hour"
    )

if tmeanUnits not in {"degC", "K"}:
    raise ValueError(
        "Invalid forcing_tmean_units setting:\n"
        f"  {tmeanUnits}\n\n"
        "Allowed values are:\n"
        "  degC\n"
        "  K"
    )

forcingRawPath = read_from_control(controlPath, "forcing_raw_path")

if forcingRawPath == "default":
    forcingRawPath = make_default_path("forcing/1_raw_data")
else:
    forcingRawPath = Path(forcingRawPath)

outputPath = forcingRawPath / "EM_Earth_prepared"
outputPath.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------
# TIME PERIOD
# ---------------------------------------------------------------------

years = read_from_control(controlPath, "forcing_raw_time")

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
    startText, endText = [x.strip() for x in years.split(",")]
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

if not (1 <= startMonth <= 12 and 1 <= endMonth <= 12):
    raise ValueError(
        f"Invalid month in forcing_raw_time: {years}"
    )

if (startYear, startMonth) > (endYear, endMonth):
    raise ValueError(f"Invalid forcing_raw_time: {years}")

periodText = (
    f"{startYear}-{startMonth:02d} to {endYear}-{endMonth:02d}"
)


# ---------------------------------------------------------------------
# SPATIAL EXTENT
# ---------------------------------------------------------------------

space = read_from_control(controlPath, "forcing_raw_space")

try:
    latMax, lonMin, latMin, lonMax = [
        float(x.strip()) for x in space.split("/")
    ]
except Exception as exc:
    raise ValueError(
        "forcing_raw_space must have format:\n"
        "LAT_MAX/LON_MIN/LAT_MIN/LON_MAX"
    ) from exc

if latMin >= latMax:
    raise ValueError("forcing_raw_space has invalid latitude bounds.")

if lonMin >= lonMax:
    raise ValueError("forcing_raw_space has invalid longitude bounds.")

# Add one grid-cell buffer (MSWEP is 0.1 degree).
buffer = 0.1

subset_lat_max = latMax + buffer
subset_lat_min = latMin - buffer
subset_lon_min = lonMin - buffer
subset_lon_max = lonMax + buffer


def subset_box(ds):
    """
    Spatially subset a dataset to the basin box, handling either
    latitude ordering (north->south or south->north).
    """
    lat = ds["lat"].values

    if lat[0] > lat[-1]:
        lat_slice = slice(subset_lat_max, subset_lat_min)
    else:
        lat_slice = slice(subset_lat_min, subset_lat_max)

    return ds.sel(
        lat=lat_slice,
        lon=slice(subset_lon_min, subset_lon_max),
    )


# ---------------------------------------------------------------------
# INPUT DIRECTORY CHECKS
# ---------------------------------------------------------------------

if not prcpPath.exists():
    raise FileNotFoundError(
        f"Precipitation directory not found:\n{prcpPath}"
    )

if not tmeanPath.exists():
    raise FileNotFoundError(
        f"Temperature directory not found:\n{tmeanPath}"
    )


# ---------------------------------------------------------------------
# SELECT MONTHS TO PROCESS
# ---------------------------------------------------------------------

# CONTROL_FILE only: process every month in forcing_raw_time.
if len(sys.argv) == 2:
    months_to_process = [
        (year, month)
        for year in range(startYear, endYear + 1)
        for month in range(1, 13)
        if (startYear, startMonth) <= (year, month) <= (endYear, endMonth)
    ]

# CONTROL_FILE YEAR MONTH: process one specific month.
elif len(sys.argv) == 4:
    try:
        runYear = int(sys.argv[2])
        runMonth = int(sys.argv[3])
    except ValueError as exc:
        raise ValueError("YEAR and MONTH must be integers.") from exc

    if runMonth < 1 or runMonth > 12:
        raise ValueError("Month must be between 1 and 12.")

    if not (
        (startYear, startMonth)
        <= (runYear, runMonth)
        <= (endYear, endMonth)
    ):
        raise ValueError(
            f"{runYear}-{runMonth:02d} is outside "
            f"forcing_raw_time {periodText}"
        )

    months_to_process = [(runYear, runMonth)]


# ---------------------------------------------------------------------
# REPORT
# ---------------------------------------------------------------------

print()
print("=" * 70)
print("PREPARE FORCING (MSWEP precipitation + temperature)")
print("=" * 70)
print(f"Domain         : {domainName}")
print(f"Control file   : {controlPath}")
print(f"Precip path    : {prcpPath}")
print(f"Precip variable: {prcpVar} ({prcpUnits})")
print(f"Tmean path     : {tmeanPath}")
print(f"Tmean variable : {tmeanVar} ({tmeanUnits})")
print(f"Output         : {outputPath}")
print(f"Forcing years  : {periodText}")
print(f"Months this run: {len(months_to_process)}")
print("Subset bounds:")
print(f"  latitude : {subset_lat_min} to {subset_lat_max}")
print(f"  longitude: {subset_lon_min} to {subset_lon_max}")
print()


# ---------------------------------------------------------------------
# PROCESS MONTHS
# ---------------------------------------------------------------------

processed_months = []
skipped_months = []
missing_months = []

for year, month in months_to_process:

    ym = f"{year}{month:02d}"

    prcpFile = prcpPath / f"{ym}.nc"
    tmeanFile = tmeanPath / f"{ym}.nc"
    outputFile = outputPath / f"EM_Earth_SUMMA_{ym}.nc"

    print(f"Processing {ym}")

    # -------------------------------------------------------------
    # CHECK INPUTS
    # -------------------------------------------------------------

    if not prcpFile.exists():
        print(f"  Missing precipitation file: {prcpFile}")
        missing_months.append(ym)
        continue

    if not tmeanFile.exists():
        print(f"  Missing temperature file: {tmeanFile}")
        missing_months.append(ym)
        continue

    if outputFile.exists():
        print(f"  Output already exists: {outputFile}")
        skipped_months.append(ym)
        continue

    # -------------------------------------------------------------
    # OPEN INPUT DATASETS
    # -------------------------------------------------------------

    with (
        xr.open_dataset(prcpFile) as ds_prcp,
        xr.open_dataset(tmeanFile) as ds_tmean,
    ):

        # ---------------------------------------------------------
        # SPATIAL SUBSET
        # ---------------------------------------------------------

        ds_prcp = subset_box(ds_prcp)
        ds_tmean = subset_box(ds_tmean)

        # ---------------------------------------------------------
        # CHECK SUBSET
        # ---------------------------------------------------------

        if (
            ds_prcp.sizes.get("lat", 0) == 0
            or ds_prcp.sizes.get("lon", 0) == 0
        ):
            raise ValueError(
                f"Precipitation subset is empty for {ym}. "
                "Check forcing_raw_space."
            )

        if (
            ds_tmean.sizes.get("lat", 0) == 0
            or ds_tmean.sizes.get("lon", 0) == 0
        ):
            raise ValueError(
                f"Temperature subset is empty for {ym}. "
                "Check forcing_raw_space."
            )

        # ---------------------------------------------------------
        # VERIFY TIME / GRID MATCH
        # ---------------------------------------------------------

        if not ds_prcp["time"].identical(ds_tmean["time"]):
            raise ValueError(
                "Time mismatch between precipitation and temperature "
                f"for {ym}. (Check that both inputs have the same time "
                "step, e.g. both daily.)"
            )

        if not ds_prcp["lat"].identical(ds_tmean["lat"]):
            raise ValueError(f"Latitude mismatch for {ym}")

        if not ds_prcp["lon"].identical(ds_tmean["lon"]):
            raise ValueError(f"Longitude mismatch for {ym}")

        # ---------------------------------------------------------
        # PRECIPITATION
        #
        # SUMMA receives pptrate in kg m-2 s-1.
        # 1 mm water = 1 kg m-2, so:
        #   mm/hour -> divide by 3600  (default, same as original script)
        #   mm/day  -> divide by 86400
        # ---------------------------------------------------------

        if prcpVar not in ds_prcp.variables:
            raise RuntimeError(
                "Selected precipitation variable is missing from the "
                "source file.\n"
                f"Selected variable: {prcpVar}\n"
                f"File: {prcpFile}\n"
                f"Available variables: {list(ds_prcp.variables)}"
            )

        pptrate = (
            ds_prcp[prcpVar] / precip_divisor[prcpUnits]
        ).astype("float32")

        pptrate.attrs = {
            "units": "kg m-2 s-1",
            "long_name": f"precipitation rate from {prcpVar}",
            "standard_name": "precipitation_flux",
        }

        # ---------------------------------------------------------
        # TEMPERATURE
        #
        # SUMMA: airtemp = K
        # ---------------------------------------------------------

        if tmeanVar not in ds_tmean.variables:
            raise RuntimeError(
                "Selected temperature variable is missing from the "
                "source file.\n"
                f"Selected variable: {tmeanVar}\n"
                f"File: {tmeanFile}\n"
                f"Available variables: {list(ds_tmean.variables)}"
            )

        if tmeanUnits == "degC":
            airtemp = (ds_tmean[tmeanVar] + 273.15).astype("float32")
        else:
            airtemp = ds_tmean[tmeanVar].astype("float32")

        airtemp.attrs = {
            "units": "K",
            "long_name": f"air temperature from {tmeanVar}",
            "standard_name": "air_temperature",
        }

        # ---------------------------------------------------------
        # OUTPUT DATASET
        # ---------------------------------------------------------

        ds_out = xr.Dataset(
            data_vars={
                "pptrate": pptrate,
                "airtemp": airtemp,
            },
            coords={
                "time": ds_prcp["time"],
                "lat": ds_prcp["lat"],
                "lon": ds_prcp["lon"],
            },
        )

        ds_out = ds_out.rename(
            {
                "lat": "latitude",
                "lon": "longitude",
            }
        )

        # ---------------------------------------------------------
        # GLOBAL METADATA
        # ---------------------------------------------------------

        ds_out.attrs["History"] = (
            "Created from MSWEP precipitation and temperature forcing"
        )
        ds_out.attrs["Reason"] = (
            "Prepare precipitation and air temperature for NWAM-SUMMA"
        )
        ds_out.attrs["Source precipitation"] = (
            f"{prcpPath} variable {prcpVar} ({prcpUnits})"
        )
        ds_out.attrs["Source temperature"] = (
            f"{tmeanPath} variable {tmeanVar} ({tmeanUnits})"
        )
        ds_out.attrs["CWARHM domain"] = domainName
        ds_out.attrs["CWARHM control file"] = controlPath.name

        # ---------------------------------------------------------
        # WRITE OUTPUT
        # ---------------------------------------------------------

        encoding = {
            "pptrate": {
                "dtype": "float32",
                "zlib": True,
                "complevel": 4,
            },
            "airtemp": {
                "dtype": "float32",
                "zlib": True,
                "complevel": 4,
            },
        }

        ds_out.to_netcdf(outputFile, encoding=encoding)
        ds_out.close()

    processed_months.append(ym)
    print(f"  Created: {outputFile}")


# ---------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------

logFolder = outputPath / "_workflow_log"
logFolder.mkdir(parents=True, exist_ok=True)

thisFile = Path(__file__).name

try:
    copyfile(Path(__file__).resolve(), logFolder / thisFile)
except Exception as exc:
    print(f"Warning: could not copy script to log folder: {exc}")

# Also preserve the exact domain control file used for this run.
try:
    copyfile(controlPath, logFolder / controlPath.name)
except Exception as exc:
    print(f"Warning: could not copy control file to log folder: {exc}")

now = datetime.now()

if len(months_to_process) == 1:
    run_label = months_to_process[0][0] * 100 + months_to_process[0][1]
    logFile = logFolder / (
        f"{now:%Y%m%d_%H%M%S}_prepare_emearth_{run_label}.txt"
    )
else:
    logFile = logFolder / (
        f"{now:%Y%m%d_%H%M%S}_prepare_emearth_forcing_log.txt"
    )

with open(logFile, "w") as file:
    file.write(f"Run time          : {now:%Y-%m-%d %H:%M:%S}\n")
    file.write(f"Domain            : {domainName}\n")
    file.write(f"Control file      : {controlPath}\n")
    file.write(f"Precip path       : {prcpPath}\n")
    file.write(f"Precip variable   : {prcpVar} ({prcpUnits})\n")
    file.write(f"Tmean path        : {tmeanPath}\n")
    file.write(f"Tmean variable    : {tmeanVar} ({tmeanUnits})\n")
    file.write(f"Output path       : {outputPath}\n")
    file.write(f"Forcing years     : {periodText}\n")
    file.write(
        "Subset bounds     : "
        f"lat {subset_lat_min} to {subset_lat_max}, "
        f"lon {subset_lon_min} to {subset_lon_max}\n"
    )
    file.write(f"Months requested  : {len(months_to_process)}\n")
    file.write(f"Months processed  : {len(processed_months)}\n")
    file.write(f"Months skipped    : {len(skipped_months)}\n")
    file.write(f"Months missing    : {len(missing_months)}\n")

    if skipped_months:
        file.write("\nSkipped (output already existed):\n")
        for ym in skipped_months:
            file.write(f"  {ym}\n")

    if missing_months:
        file.write("\nMissing input files:\n")
        for ym in missing_months:
            file.write(f"  {ym}\n")

print()
print("=" * 70)
print("DONE")
print("=" * 70)
print(f"Processed: {len(processed_months)}")
print(f"Skipped  : {len(skipped_months)}")
print(f"Missing  : {len(missing_months)}")
print(f"Log      : {logFile}")
