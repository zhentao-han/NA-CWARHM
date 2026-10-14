#!/usr/bin/env python3
# coding: utf-8

# Create trialParams.nc for an NWAM-SUMMA domain.
#
# Purpose
# -------
# Create the SUMMA trial-parameter NetCDF using the HRU ordering
# from the first forcing file listed in forcingFileList.txt.
#
# This guarantees that:
#
#   trialParams.nc hruId
#
# exactly follows:
#
#   NWAM_SUMMA_forcing_YYYYMM.nc hruId
#
# Trial parameters are defined in the supplied control file:
#
#   settings_summa_trialParam_n
#   settings_summa_trialParam_1
#   settings_summa_trialParam_2
#   ...
#
# A parameter setting may contain:
#
#   parameter,value
#
# which assigns the same value to every HRU, or:
#
#   parameter,value1,value2,...,valueN
#
# where N must equal the number of HRUs.
#
# >>> CHANGED (1): header documentation for the new GRU content
# Dimensions and ID variables written to trialParams.nc
# (same layout as attributes.nc):
#
#   dimensions : hru, gru
#   hruId(hru) : HRU IDs, in the forcing-file HRU order
#   gruId(gru) : unique GRU IDs, in order of first appearance
#                after the catchment is reordered to the forcing
#                HRU order (identical to attributes.nc gruId)
#
# GRU IDs come from the Stage-00 prepared catchment shapefile
# (catchment_shp_hruid / catchment_shp_gruid), exactly as in
# 1_initialize_attributes_nc.py. Trial parameters themselves
# remain HRU-based, i.e. they are dimensioned (hru,).
# <<< END CHANGED (1)
#
# IMPORTANT
# ---------
# This script reads the domain-specific control file supplied on
# the command line.
#
# It does NOT read or modify control_active.txt.
#
# Usage
# -----
#
# python 1_create_trialParams.py \
#     /path/to/control_DOMAIN.txt

import sys
from pathlib import Path
from datetime import datetime
from shutil import copy2

# >>> CHANGED (2): geopandas and pandas are needed to read the
# >>> prepared catchment shapefile and build the GRU list
import geopandas as gpd
import pandas as pd
# <<< END CHANGED (2)
import netCDF4 as nc4
import numpy as np
import xarray as xr


# ============================================================
# CONTROL FILE
# ============================================================

if len(sys.argv) != 2:

    raise SystemExit(
        "Usage:\n"
        "python 1_create_trialParams.py "
        "/path/to/control_DOMAIN.txt"
    )


CONTROL_FILE = Path(
    sys.argv[1]
).resolve()


if not CONTROL_FILE.exists():

    raise FileNotFoundError(
        f"Control file not found:\n"
        f"{CONTROL_FILE}"
    )


# ============================================================
# CONTROL FUNCTIONS
# ============================================================

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

            left, right = stripped.split(
                "|",
                1
            )

            if left.strip() != setting:
                continue

            value = (
                right
                .split("#", 1)[0]
                .strip()
            )

            if value == "":
                raise ValueError(
                    f"Setting '{setting}' is empty in:\n"
                    f"{file}"
                )

            return value

    raise ValueError(
        f"Setting '{setting}' not found in:\n"
        f"{file}"
    )


def make_default_path(suffix):
    """
    Construct:
        <root_path>/domain_<domain_name>/<suffix>
    """

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
    """
    Resolve a control-file path that may be set to 'default'.
    """

    value = read_from_control(
        CONTROL_FILE,
        setting
    )

    if value == "default":

        return make_default_path(
            default_suffix
        )

    return Path(
        value
    )


# >>> CHANGED (3): helper functions copied unchanged from
# >>> 1_initialize_attributes_nc.py so GRU handling is identical
def convert_integer_ids(values, name):
    """
    Validate numeric IDs and return int64 values.
    """

    values = (
        np.asarray(
            values
        )
        .reshape(-1)
    )

    if values.ndim != 1:

        raise RuntimeError(
            f"{name} must be one-dimensional.\n"
            f"Shape found: {values.shape}"
        )

    if values.size == 0:

        raise RuntimeError(
            f"No values found for {name}."
        )

    try:

        values_float = values.astype(
            np.float64
        )

    except Exception as exc:

        raise RuntimeError(
            f"{name} could not be converted "
            "to numeric values."
        ) from exc

    if not np.all(
        np.isfinite(
            values_float
        )
    ):

        raise RuntimeError(
            f"{name} contains non-finite values."
        )

    if not np.allclose(
        values_float,
        np.round(
            values_float
        )
    ):

        raise RuntimeError(
            f"{name} contains non-integer values."
        )

    return (
        np.round(
            values_float
        )
        .astype(np.int64)
    )


def validate_int32(values, name):
    """
    Ensure IDs fit the int32 representation used for gruId
    (same as attributes.nc).
    """

    values = np.asarray(
        values,
        dtype=np.int64
    )

    info = np.iinfo(
        np.int32
    )

    if (
        np.any(values < info.min)
        or np.any(values > info.max)
    ):

        raise RuntimeError(
            f"{name} contains values outside the "
            "32-bit integer range."
        )


def validate_gru_contiguity(gru_values):
    """
    Verify that each GRU occurs in one continuous HRU block.
    """

    seen = set()
    previous = None

    for raw_value in gru_values:

        value = int(
            raw_value
        )

        if value != previous:

            if value in seen:

                raise RuntimeError(
                    f"GRU {value} appears in multiple "
                    "non-contiguous HRU blocks.\n\n"
                    "SUMMA requires all HRUs belonging "
                    "to a GRU to be consecutive in the "
                    "HRU dimension."
                )

            seen.add(
                value
            )

            previous = value
# <<< END CHANGED (3)


# ============================================================
# DOMAIN
# ============================================================

domain_name = read_from_control(
    CONTROL_FILE,
    "domain_name"
)


# ============================================================
# PATHS
# ============================================================

forcing_path = resolve_path(
    "forcing_summa_path",
    "forcing/4_SUMMA_input"
)


settings_path = resolve_path(
    "settings_summa_path",
    "settings/SUMMA"
)


settings_path.mkdir(
    parents=True,
    exist_ok=True
)


trialparams_name = read_from_control(
    CONTROL_FILE,
    "settings_summa_trialParams"
)


forcing_list_name = read_from_control(
    CONTROL_FILE,
    "settings_summa_forcing_list"
)


trialparams_file = (
    settings_path
    / trialparams_name
)


forcing_list_file = (
    settings_path
    / forcing_list_name
)


# ============================================================
# VALIDATE FORCING INPUTS
# ============================================================

if not forcing_path.exists():

    raise FileNotFoundError(
        "SUMMA forcing directory not found:\n"
        f"{forcing_path}"
    )


if not forcing_list_file.exists():

    raise FileNotFoundError(
        "SUMMA forcing-file list not found:\n"
        f"{forcing_list_file}\n\n"
        "Run 1_create_forcing_file_list.py after the complete "
        "forcing archive has been generated."
    )


with open(
    forcing_list_file
) as file:

    forcing_names = [
        line.strip()
        for line in file
        if line.strip()
        and not line.lstrip().startswith("#")
    ]


if not forcing_names:

    raise RuntimeError(
        "SUMMA forcing-file list is empty:\n"
        f"{forcing_list_file}"
    )


if len(forcing_names) != len(
    set(forcing_names)
):

    raise RuntimeError(
        "Duplicate filenames were found in:\n"
        f"{forcing_list_file}"
    )


forcing_file = (
    forcing_path
    / forcing_names[0]
)


if not forcing_file.exists():

    raise FileNotFoundError(
        "First forcing file listed in forcingFileList.txt "
        "does not exist:\n"
        f"{forcing_file}"
    )


# ============================================================
# READ HRU ORDER FROM FIRST SUMMA FORCING FILE
# ============================================================

with xr.open_dataset(
    forcing_file
) as forcing:

    if "hru" not in forcing.dims:

        raise RuntimeError(
            "Forcing file does not contain an 'hru' dimension:\n"
            f"{forcing_file}"
        )


    if "hruId" not in forcing:

        raise RuntimeError(
            "hruId not found in forcing file:\n"
            f"{forcing_file}"
        )

    forcing_hru_ids = (
        np.asarray(
            forcing["hruId"].values
        )
        .reshape(-1)
    )

# ============================================================
# VALIDATE HRU IDS
# ============================================================

if forcing_hru_ids.ndim != 1:

    raise RuntimeError(
        "Forcing hruId must be one-dimensional.\n"
        f"Shape found: {forcing_hru_ids.shape}"
    )


if forcing_hru_ids.size == 0:

    raise RuntimeError(
        "No HRU IDs found in forcing file."
    )


try:

    forcing_hru_ids_float = (
        forcing_hru_ids
        .astype(np.float64)
    )

except Exception as exc:

    raise RuntimeError(
        "Forcing hruId values could not be converted "
        "to numeric values."
    ) from exc


if not np.all(
    np.isfinite(
        forcing_hru_ids_float
    )
):

    raise RuntimeError(
        "Non-finite HRU IDs found in forcing."
    )


if not np.allclose(
    forcing_hru_ids_float,
    np.round(
        forcing_hru_ids_float
    )
):

    raise RuntimeError(
        "Forcing hruId contains non-integer values."
    )


forcing_hru_ids = (
    np.round(
        forcing_hru_ids_float
    )
    .astype(np.int64)
)


if len(
    np.unique(
        forcing_hru_ids
    )
) != len(
    forcing_hru_ids
):

    raise RuntimeError(
        "Duplicate hruId values found in forcing."
    )


num_hru = len(
    forcing_hru_ids
)


# >>> CHANGED (4): NEW SECTION - read the HRU -> GRU mapping from
# >>> the Stage-00 prepared catchment and derive gruId, following
# >>> the same logic as 1_initialize_attributes_nc.py
# ============================================================
# READ GRU MAPPING FROM PREPARED CATCHMENT
# ============================================================

catchment_name = read_from_control(
    CONTROL_FILE,
    "catchment_shp_name"
)

# Always use the Stage-00 prepared CWARHM catchment.
catchment_file = (
    make_default_path(
        "shapefiles/catchment"
    )
    / catchment_name
)

hru_field = read_from_control(
    CONTROL_FILE,
    "catchment_shp_hruid"
)

gru_field = read_from_control(
    CONTROL_FILE,
    "catchment_shp_gruid"
)


if not catchment_file.exists():

    raise FileNotFoundError(
        "Prepared CWARHM catchment shapefile "
        "not found:\n"
        f"{catchment_file}\n\n"
        "Run Stage 00 before creating "
        "trialParams.nc."
    )


shp = gpd.read_file(
    catchment_file,
    engine="fiona"
)


if len(shp) == 0:

    raise RuntimeError(
        "Prepared catchment contains no HRUs."
    )


missing_fields = [
    field
    for field in (
        hru_field,
        gru_field
    )
    if field not in shp.columns
]


if missing_fields:

    raise RuntimeError(
        "Prepared catchment is missing required "
        "attribute field(s):\n"
        + "\n".join(
            f"  {field}"
            for field in missing_fields
        )
    )


for field in (
    hru_field,
    gru_field
):

    try:

        shp[field] = pd.to_numeric(
            shp[field],
            errors="raise"
        )

    except Exception as exc:

        raise RuntimeError(
            f"Catchment field '{field}' "
            "contains non-numeric values."
        ) from exc


catchment_hru_ids = convert_integer_ids(
    shp[
        hru_field
    ].to_numpy(),
    hru_field
)

catchment_gru_ids = convert_integer_ids(
    shp[
        gru_field
    ].to_numpy(),
    gru_field
)


if len(
    np.unique(
        catchment_hru_ids
    )
) != len(
    catchment_hru_ids
):

    raise RuntimeError(
        f"Duplicate {hru_field} values "
        "found in prepared catchment."
    )


validate_int32(
    catchment_gru_ids,
    gru_field
)


# The catchment and forcing must describe the same HRUs.

missing_from_shape = sorted(
    set(forcing_hru_ids.tolist())
    - set(catchment_hru_ids.tolist())
)

extra_in_shape = sorted(
    set(catchment_hru_ids.tolist())
    - set(forcing_hru_ids.tolist())
)


if (
    missing_from_shape
    or extra_in_shape
):

    raise RuntimeError(
        "Prepared catchment and forcing HRU "
        "sets differ.\n\n"
        f"Missing from catchment: "
        f"{missing_from_shape}\n"
        f"Extra in catchment    : "
        f"{extra_in_shape}"
    )


# Reorder the catchment GRU IDs to the forcing HRU order
# (forcing hruId remains authoritative; it is never changed).

hru_to_gru = (
    pd.Series(
        catchment_gru_ids,
        index=catchment_hru_ids
    )
    .loc[
        forcing_hru_ids
    ]
    .to_numpy(
        dtype=np.int64
    )
)

# Unique GRUs in the order in which they first occur.
gru_ids = pd.unique(
    hru_to_gru
).astype(
    np.int64
)

# SUMMA grouping requirement.
validate_gru_contiguity(
    hru_to_gru
)

num_gru = len(
    gru_ids
)
# <<< END CHANGED (4)


# ============================================================
# READ NUMBER OF TRIAL PARAMETERS
# ============================================================

try:

    num_trial_parameters = int(
        read_from_control(
            CONTROL_FILE,
            "settings_summa_trialParam_n"
        )
    )

except Exception as exc:

    raise ValueError(
        "settings_summa_trialParam_n must be "
        "an integer."
    ) from exc


if num_trial_parameters < 0:

    raise ValueError(
        "settings_summa_trialParam_n "
        "cannot be negative."
    )


# ============================================================
# READ TRIAL PARAMETERS
# ============================================================

trial_parameters = {}


for index in range(
    1,
    num_trial_parameters + 1
):

    setting_name = (
        f"settings_summa_trialParam_{index}"
    )


    parameter_setting = (
        read_from_control(
            CONTROL_FILE,
            setting_name
        )
    )


    pieces = [
        item.strip()
        for item in parameter_setting.split(",")
    ]


    if len(pieces) < 2:

        raise ValueError(
            f"{setting_name} must contain at least:\n"
            "parameter,value"
        )


    parameter_name = pieces[0]


    if parameter_name == "":

        raise ValueError(
            f"{setting_name} contains an empty "
            "parameter name."
        )


    if parameter_name in trial_parameters:

        raise ValueError(
            "Duplicate trial parameter found:\n"
            f"{parameter_name}"
        )


    value_strings = pieces[1:]


    if any(
        value == ""
        for value in value_strings
    ):

        raise ValueError(
            f"{setting_name} contains an empty "
            "parameter value:\n"
            f"{parameter_setting}"
        )


    try:

        values = np.asarray(
            [
                float(value)
                for value in value_strings
            ],
            dtype=np.float64
        )

    except ValueError as exc:

        raise ValueError(
            "Non-numeric trial-parameter value found.\n"
            f"Setting : {setting_name}\n"
            f"Value   : {parameter_setting}"
        ) from exc


    if not np.all(
        np.isfinite(
            values
        )
    ):

        raise ValueError(
            f"{parameter_name} contains non-finite "
            "trial-parameter values."
        )


    # --------------------------------------------------------
    # One value -> same parameter for all HRUs
    # --------------------------------------------------------

    if len(values) == 1:

        values = np.full(
            num_hru,
            values[0],
            dtype=np.float64
        )


    # --------------------------------------------------------
    # Multiple values -> one value for every HRU
    # --------------------------------------------------------

    elif len(values) != num_hru:

        raise ValueError(
            f"Trial parameter '{parameter_name}' specifies "
            f"{len(values)} values, but the domain contains "
            f"{num_hru} HRUs.\n\n"
            "Supply either:\n"
            "  1 value for all HRUs\n"
            "or\n"
            f"  exactly {num_hru} HRU-specific values."
        )


    trial_parameters[
        parameter_name
    ] = values


# ============================================================
# REPORT
# ============================================================

print()
print("=" * 70)
print("CREATE SUMMA TRIAL PARAMETERS")
print("=" * 70)

print(
    f"Domain           : {domain_name}"
)

print(
    f"Control file     : {CONTROL_FILE}"
)

print(
    f"Forcing list     : {forcing_list_file}"
)

print(
    f"Forcing template : {forcing_file}"
)

print(
    f"HRUs             : {num_hru}"
)

print(
    f"First HRU ID     : {forcing_hru_ids[0]}"
)

print(
    f"Last HRU ID      : {forcing_hru_ids[-1]}"
)

# >>> CHANGED (5): report GRU information
print(
    f"Catchment        : {catchment_file}"
)

print(
    f"GRUs             : {num_gru}"
)

print(
    f"First GRU ID     : {gru_ids[0]}"
)

print(
    f"Last GRU ID      : {gru_ids[-1]}"
)
# <<< END CHANGED (5)

print(
    f"Trial parameters : {num_trial_parameters}"
)


if trial_parameters:

    print()

    for (
        name,
        values
    ) in trial_parameters.items():

        if np.allclose(
            values,
            values[0]
        ):

            print(
                f"  {name} = "
                f"{values[0]:g} "
                "(all HRUs)"
            )

        else:

            print(
                f"  {name} = "
                "HRU-specific values"
            )

            print(
                f"    min = {values.min():g}"
            )

            print(
                f"    max = {values.max():g}"
            )

else:

    print()
    print(
        "  No trial parameters specified."
    )


print()

print(
    f"Output           : {trialparams_file}"
)


# ============================================================
# CREATE trialParams.nc
# ============================================================

# Existing output is replaced only after all input and
# control-file validation above has passed.

with nc4.Dataset(
    trialparams_file,
    "w",
    format="NETCDF4"
) as tp:

    now = datetime.now()


    # --------------------------------------------------------
    # Global attributes
    # --------------------------------------------------------

    tp.setncattr(
        "Author",
        "NWAM-SUMMA workflow"
    )

    tp.setncattr(
        "History",
        "Created "
        + now.strftime(
            "%Y/%m/%d %H:%M:%S"
        )
    )

    tp.setncattr(
        "Purpose",
        "SUMMA trial parameter values"
    )

    tp.setncattr(
        "Domain",
        domain_name
    )

    tp.setncattr(
        "HRU_order_source",
        forcing_file.name
    )

    # >>> CHANGED (6a): record where the GRU IDs came from
    tp.setncattr(
        "Catchment_source",
        str(
            catchment_file
        )
    )
    # <<< END CHANGED (6a)


    # --------------------------------------------------------
    # Dimensions
    # --------------------------------------------------------

    tp.createDimension(
        "hru",
        num_hru
    )

    # >>> CHANGED (6b): add the 'gru' dimension (as in attributes.nc)
    tp.createDimension(
        "gru",
        num_gru
    )
    # <<< END CHANGED (6b)


    # --------------------------------------------------------
    # HRU IDs
    # --------------------------------------------------------

    variable = tp.createVariable(
        "hruId",
        "i8",
        ("hru",)
    )

    variable.setncattr(
        "units",
        "-"
    )

    variable.setncattr(
        "long_name",
        "Hydrological response unit identifier"
    )

    variable[:] = (
        forcing_hru_ids
    )


    # >>> CHANGED (6c): add gruId(gru), same dtype/attributes as
    # >>> attributes.nc
    # --------------------------------------------------------
    # GRU IDs
    # --------------------------------------------------------

    variable = tp.createVariable(
        "gruId",
        "i4",
        ("gru",)
    )

    variable.setncattr(
        "units",
        "-"
    )

    variable.setncattr(
        "long_name",
        "Grouped response unit identifier"
    )

    variable[:] = gru_ids.astype(
        np.int32
    )
    # <<< END CHANGED (6c)


    # --------------------------------------------------------
    # Trial parameters
    # --------------------------------------------------------

    for (
        parameter_name,
        values
    ) in trial_parameters.items():

        variable = tp.createVariable(
            parameter_name,
            "f8",
            ("hru",)
        )

        variable[:] = (
            values
        )


# ============================================================
# VERIFY OUTPUT
# ============================================================

with xr.open_dataset(
    trialparams_file
) as saved:

    # --------------------------------------------------------
    # HRU dimension
    # --------------------------------------------------------

    if "hru" not in saved.sizes:

        raise RuntimeError(
            "trialParams.nc is missing the "
            "'hru' dimension."
        )


    if saved.sizes[
        "hru"
    ] != num_hru:

        raise RuntimeError(
            "trialParams.nc has the wrong HRU count.\n"
            f"Expected : {num_hru}\n"
            f"Found    : {saved.sizes['hru']}"
        )


    # >>> CHANGED (7a): verify the 'gru' dimension
    if "gru" not in saved.sizes:

        raise RuntimeError(
            "trialParams.nc is missing the "
            "'gru' dimension."
        )


    if saved.sizes[
        "gru"
    ] != num_gru:

        raise RuntimeError(
            "trialParams.nc has the wrong GRU count.\n"
            f"Expected : {num_gru}\n"
            f"Found    : {saved.sizes['gru']}"
        )
    # <<< END CHANGED (7a)


    # --------------------------------------------------------
    # HRU ID
    # --------------------------------------------------------

    if "hruId" not in saved:

        raise RuntimeError(
            "hruId is missing from trialParams.nc."
        )


    output_hru_ids = (
        saved[
            "hruId"
        ]
        .values
        .astype(np.int64)
    )


    if not np.array_equal(
        forcing_hru_ids,
        output_hru_ids
    ):

        raise RuntimeError(
            "trialParams.nc HRU order does not "
            "match SUMMA forcing."
        )


    # >>> CHANGED (7b): verify gruId
    # --------------------------------------------------------
    # GRU ID
    # --------------------------------------------------------

    if "gruId" not in saved:

        raise RuntimeError(
            "gruId is missing from trialParams.nc."
        )


    output_gru_ids = (
        saved[
            "gruId"
        ]
        .values
        .astype(np.int64)
    )


    if not np.array_equal(
        gru_ids,
        output_gru_ids
    ):

        raise RuntimeError(
            "trialParams.nc gruId validation failed."
        )
    # <<< END CHANGED (7b)


    # --------------------------------------------------------
    # Trial parameters
    # --------------------------------------------------------

    for (
        parameter_name,
        expected_values
    ) in trial_parameters.items():

        if parameter_name not in saved:

            raise RuntimeError(
                "Trial parameter missing from "
                f"saved NetCDF: {parameter_name}"
            )


        saved_values = np.asarray(
            saved[
                parameter_name
            ].values,
            dtype=np.float64
        )


        if saved_values.shape != (
            num_hru,
        ):

            raise RuntimeError(
                f"{parameter_name} has an unexpected "
                "shape in trialParams.nc.\n"
                f"Expected : {(num_hru,)}\n"
                f"Found    : {saved_values.shape}"
            )


        if not np.all(
            np.isfinite(
                saved_values
            )
        ):

            raise RuntimeError(
                f"{parameter_name} contains non-finite "
                "values in trialParams.nc."
            )


        if not np.allclose(
            saved_values,
            expected_values,
            rtol=0.0,
            atol=0.0
        ):

            raise RuntimeError(
                "Saved trial-parameter values do not "
                "match the values requested in the "
                f"control file for {parameter_name}."
            )


# ============================================================
# LOGGING
# ============================================================

log_folder = (
    settings_path
    / "_workflow_log"
)


log_folder.mkdir(
    parents=True,
    exist_ok=True
)


this_file = Path(
    __file__
).name


copy2(
    Path(
        __file__
    ).resolve(),
    log_folder
    / this_file
)


copy2(
    CONTROL_FILE,
    log_folder
    / CONTROL_FILE.name
)


now = datetime.now()


log_file = (
    log_folder
    / (
        f"{now:%Y%m%d_%H%M%S}_"
        "create_summa_trial_params.txt"
    )
)


with open(
    log_file,
    "w"
) as file:

    file.write(
        f"Log generated by {this_file} "
        f"on {now:%Y/%m/%d %H:%M:%S}\n"
    )

    file.write(
        f"Domain: {domain_name}\n"
    )

    file.write(
        f"Control file: {CONTROL_FILE}\n"
    )

    file.write(
        f"Forcing list: {forcing_list_file}\n"
    )

    file.write(
        f"Forcing template: {forcing_file}\n"
    )

    file.write(
        f"HRUs: {num_hru}\n"
    )

    file.write(
        f"First HRU ID: {forcing_hru_ids[0]}\n"
    )

    file.write(
        f"Last HRU ID: {forcing_hru_ids[-1]}\n"
    )

    # >>> CHANGED (8): log GRU information
    file.write(
        f"Catchment: {catchment_file}\n"
    )

    file.write(
        f"GRUs: {num_gru}\n"
    )

    file.write(
        f"First GRU ID: {gru_ids[0]}\n"
    )

    file.write(
        f"Last GRU ID: {gru_ids[-1]}\n"
    )
    # <<< END CHANGED (8)

    file.write(
        f"Trial parameters: "
        f"{num_trial_parameters}\n"
    )


    for (
        name,
        values
    ) in trial_parameters.items():

        if np.allclose(
            values,
            values[0]
        ):

            file.write(
                f"{name}: {values[0]:g} "
                "(all HRUs)\n"
            )

        else:

            file.write(
                f"{name}: HRU-specific; "
                f"min={values.min():g}; "
                f"max={values.max():g}\n"
            )


    file.write(
        f"trialParams file: {trialparams_file}\n"
    )

    file.write(
        "Shared control_active.txt used: no\n"
    )


# ============================================================
# FINISH
# ============================================================

print()
print("=" * 70)
print("SUMMA TRIAL PARAMETERS CREATION COMPLETED")
print("=" * 70)

print(
    f"Domain           : {domain_name}"
)

print(
    f"Control file     : {CONTROL_FILE}"
)

print(
    f"HRUs             : {num_hru}"
)

# >>> CHANGED (9): final summary shows GRU count
print(
    f"GRUs             : {num_gru}"
)
# <<< END CHANGED (9)

print(
    f"Trial parameters : {num_trial_parameters}"
)

print(
    "HRU order        : matches SUMMA forcing"
)

print(
    f"Output           : {trialparams_file}"
)

print(
    f"Workflow log     : {log_file}"
)

print()
print(
    "No control_active.txt was created or modified."
)
