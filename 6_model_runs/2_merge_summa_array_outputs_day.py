#!/usr/bin/env python3

"""
Merge spatially split SUMMA array outputs into one day file
for mizuRoute.

Example SUMMA array files:
    run1_G001-010_day.nc
    run1_G011-020_day.nc
    ...

Output:
    run1_day.nc

The script:
    - reads control_active.txt
    - finds the active domain and experiment
    - discovers SUMMA array day files
    - ignores interrupted files with zero time steps
    - rejects overlapping/stale GRU-array files
    - verifies all array files use the same time axis
    - verifies GRU IDs are unique
    - verifies GRU IDs exactly match attributes.nc
    - preserves the expected GRU ordering
    - merges averageRoutedRunoff along gru and scalarTotalSoilWat
      and scalarSWE along hru
    - verifies the merged output
    - samples runoff values for NaN/Inf
    - writes provenance information

The merged file contains the spatially combined SUMMA variables,
including the runoff input expected by mizuRoute.
"""


from pathlib import Path
from datetime import datetime
from shutil import copyfile
import re

import netCDF4 as nc
import numpy as np

import os

# ============================================================
# PATHS
# ============================================================


SCRIPT_DIR = Path(__file__).resolve().parent
CWARHM_ROOT = SCRIPT_DIR.parent
print("CWARHM_ROOT: ")
print(CWARHM_ROOT)

#CONTROL_FILE = (
#    CWARHM_ROOT 
#    / "0_control_files" 
#    / "control_MERIT_71.txt"
#)

CONTROL_FILE = (
    CWARHM_ROOT
    / "0_control_files"
    / os.environ.get("CONTROL_FILE", "control_active.txt")
)


print("CONTROL_FILE: ")
print(CONTROL_FILE)
# ============================================================
# CONTROL READER
# ============================================================

def read_control(setting):
    """Read one exact setting from control_active.txt."""

    with open(CONTROL_FILE) as contents:

        for line in contents:

            stripped = line.strip()

            if (
                not stripped
                or stripped.startswith("#")
                or "|" not in stripped
            ):
                continue

            left, right = stripped.split("|", 1)

            if left.strip() == setting:

                return (
                    right
                    .split("#", 1)[0]
                    .strip()
                )

    raise ValueError(
        f"Setting not found in control file: {setting}"
    )


# ============================================================
# SETTINGS
# ============================================================

root_path = Path(
    read_control("root_path")
)

domain_name = read_control(
    "domain_name"
)

experiment_id = read_control(
    "experiment_id"
)


# ------------------------------------------------------------
# SUMMA output path
# ------------------------------------------------------------

summa_output = read_control(
    "experiment_output_summa"
)

if summa_output == "default":

    summa_output = (
        root_path
        / f"domain_{domain_name}"
        / "simulations"
        / experiment_id
        / "SUMMA"
    )

else:

    summa_output = Path(
        summa_output
    )


# ------------------------------------------------------------
# SUMMA settings path
# ------------------------------------------------------------

settings_path = read_control(
    "settings_summa_path"
)

if settings_path == "default":

    settings_path = (
        root_path
        / f"domain_{domain_name}"
        / "settings"
        / "SUMMA"
    )

else:

    settings_path = Path(
        settings_path
    )


# ------------------------------------------------------------
# SUMMA attributes file
# ------------------------------------------------------------

attributes_name = read_control(
    "settings_summa_attributes"
)

attributes_file = (
    settings_path
    / attributes_name
)


# ============================================================
# INPUT / OUTPUT FILE DISCOVERY
# ============================================================

pattern = re.compile(
    rf"^{re.escape(experiment_id)}_"
    r"G(\d+)-(\d+)_day\.nc$"
)

spatial_variable_dimensions = {
    "averageRoutedRunoff": ("time", "gru"),
    "scalarTotalSoilWat": ("time", "hru", "dom"),
    "scalarSWE": ("time", "hru", "dom"),
}
spatial_variables = tuple(
    spatial_variable_dimensions
)


array_files = []


for file in summa_output.glob(
    f"{experiment_id}_G*-*_day.nc"
):

    match = pattern.match(
        file.name
    )

    if match:

        start = int(
            match.group(1)
        )

        end = int(
            match.group(2)
        )

        array_files.append(
            (
                start,
                end,
                file
            )
        )


array_files.sort(
    key=lambda item: item[0]
)


output_file = (
    summa_output
    / f"{experiment_id}_day.nc"
)


# ============================================================
# BASIC CHECKS
# ============================================================

if not summa_output.exists():

    raise FileNotFoundError(
        "SUMMA output directory does not exist:\n"
        f"{summa_output}"
    )


if not array_files:

    raise RuntimeError(
        "No SUMMA array day files found in:\n"
        f"{summa_output}"
    )


if not attributes_file.exists():

    raise FileNotFoundError(
        "SUMMA attributes file not found:\n"
        f"{attributes_file}"
    )


# ============================================================
# EXPECTED GRU INFORMATION FROM ATTRIBUTES.NC
# ============================================================

with nc.Dataset(
    attributes_file
) as ds:

    if "gru" not in ds.dimensions:

        raise RuntimeError(
            "SUMMA attributes file does not contain "
            "the 'gru' dimension."
        )

    if "gruId" not in ds.variables:

        raise RuntimeError(
            "SUMMA attributes file does not contain "
            "the 'gruId' variable."
        )

    if "hru" not in ds.dimensions:

        raise RuntimeError(
            "SUMMA attributes file does not contain "
            "the 'hru' dimension."
        )

    if (
        "hruId" not in ds.variables
        or "hru2gruId" not in ds.variables
    ):

        raise RuntimeError(
            "SUMMA attributes file must contain "
            "'hruId' and 'hru2gruId' variables."
        )

    expected_grus = len(
        ds.dimensions["gru"]
    )

    expected_hrus = len(
        ds.dimensions["hru"]
    )

    expected_gru_ids = np.asarray(
        ds.variables["gruId"][:],
        dtype=np.int64
    )

    expected_hru_ids = np.asarray(
        ds.variables["hruId"][:],
        dtype=np.int64
    )

    expected_hru2gru_ids = np.asarray(
        ds.variables["hru2gruId"][:],
        dtype=np.int64
    )


if len(expected_gru_ids) != expected_grus:

    raise RuntimeError(
        "gruId length in attributes.nc does not match "
        "the gru dimension."
    )

if (
    len(expected_hru_ids) != expected_hrus
    or len(expected_hru2gru_ids) != expected_hrus
):

    raise RuntimeError(
        "HRU ID or hru2gruId length in attributes.nc "
        "does not match the hru dimension."
    )


if len(
    np.unique(expected_gru_ids)
) != expected_grus:

    raise RuntimeError(
        "Duplicate gruId values detected in attributes.nc."
    )

if len(
    np.unique(expected_hru_ids)
) != expected_hrus:

    raise RuntimeError(
        "Duplicate hruId values detected in attributes.nc."
    )

if not np.all(
    np.isin(expected_hru2gru_ids, expected_gru_ids)
):

    raise RuntimeError(
        "attributes.nc contains hru2gruId values "
        "that do not exist in gruId."
    )

gru_index_by_id = {
    int(gru_id): index
    for index, gru_id in enumerate(expected_gru_ids)
}

hru_indices_by_gru_id = {
    int(gru_id): np.flatnonzero(
        expected_hru2gru_ids == gru_id
    )
    for gru_id in expected_gru_ids
}


# ============================================================
# INITIAL REPORT
# ============================================================

print()
print("============================================================")
print("MERGE SUMMA ARRAY OUTPUTS")
print("============================================================")

print(f"Domain          : {domain_name}")
print(f"Experiment      : {experiment_id}")
print(f"SUMMA output    : {summa_output}")
print(f"Attributes file : {attributes_file}")
print(f"Expected GRUs   : {expected_grus}")

print()


# ============================================================
# INSPECT ARRAY FILES
# ============================================================

valid_files = []

reference_time = None
reference_time_units = None
ntime = None
reference_dom_count = None


for start, end, file in array_files:

    with nc.Dataset(
        file
    ) as ds:

        # ----------------------------------------------------
        # Required dimensions
        # ----------------------------------------------------

        if (
            "time" not in ds.dimensions
            or "gru" not in ds.dimensions
        ):

            print(
                f"SKIP: {file.name} "
                "(missing time/gru dimension)"
            )

            continue


        nt = len(
            ds.dimensions["time"]
        )

        ng = len(
            ds.dimensions["gru"]
        )

        if (
            "hru" not in ds.dimensions
            or "dom" not in ds.dimensions
        ):

            raise RuntimeError(
                f"{file.name} is missing the 'hru' "
                "or 'dom' dimension required by "
                "the scalar variables."
            )

        nh = len(
            ds.dimensions["hru"]
        )

        nd = len(
            ds.dimensions["dom"]
        )

        if reference_dom_count is None:

            reference_dom_count = nd

        elif nd != reference_dom_count:

            raise RuntimeError(
                f"Domain dimension mismatch in {file.name}: "
                f"{nd} != {reference_dom_count}"
            )


        # ----------------------------------------------------
        # Ignore interrupted diagnostic files
        # ----------------------------------------------------

        if nt == 0:

            print(
                f"SKIP: {file.name} "
                "(0 time steps)"
            )

            continue


        # ----------------------------------------------------
        # Required variables
        # ----------------------------------------------------

        required_variables = {
            "time",
            "gruId",
            *spatial_variables,
        }

        missing = (
            required_variables
            - set(ds.variables)
        )

        if missing:

            raise RuntimeError(
                f"{file.name} is missing required variables: "
                f"{sorted(missing)}"
            )


        # ----------------------------------------------------
        # Validate filename range
        # ----------------------------------------------------

        expected_count_from_name = (
            end
            - start
            + 1
        )

        if expected_count_from_name != ng:

            raise RuntimeError(
                f"{file.name}: filename implies "
                f"{expected_count_from_name} GRUs, "
                f"but file contains {ng}."
            )


        # ----------------------------------------------------
        # Time axis
        # ----------------------------------------------------

        time_var = ds.variables[
            "time"
        ]

        times = np.asarray(
            time_var[:]
        )


        if len(times) != nt:

            raise RuntimeError(
                f"{file.name}: time variable length "
                "does not match time dimension."
            )


        if not np.all(
            np.isfinite(times)
        ):

            raise RuntimeError(
                f"{file.name}: non-finite values found "
                "in time coordinate."
            )


        if np.any(
            np.diff(times) <= 0
        ):

            raise RuntimeError(
                f"{file.name}: time values are not "
                "strictly increasing."
            )


        time_units = getattr(
            time_var,
            "units",
            None
        )


        if reference_time is None:

            reference_time = times.copy()

            reference_time_units = (
                time_units
            )

            ntime = nt

        else:

            if nt != ntime:

                raise RuntimeError(
                    f"Time dimension mismatch in "
                    f"{file.name}: "
                    f"{nt} != {ntime}"
                )


            if not np.array_equal(
                times,
                reference_time
            ):

                raise RuntimeError(
                    f"Time values differ in "
                    f"{file.name}"
                )


            if (
                time_units
                != reference_time_units
            ):

                raise RuntimeError(
                    f"Time units differ in "
                    f"{file.name}"
                )


        # ----------------------------------------------------
        # GRU IDs
        # ----------------------------------------------------

        gru_ids = np.asarray(
            ds.variables[
                "gruId"
            ][:],
            dtype=np.int64
        )


        if len(gru_ids) != ng:

            raise RuntimeError(
                f"gruId size mismatch in "
                f"{file.name}"
            )


        if len(
            np.unique(gru_ids)
        ) != ng:

            raise RuntimeError(
                f"Duplicate gruId values inside "
                f"{file.name}"
            )

        unknown_gru_ids = [
            int(gru_id)
            for gru_id in gru_ids
            if int(gru_id) not in gru_index_by_id
        ]

        if unknown_gru_ids:

            raise RuntimeError(
                f"{file.name} contains GRU IDs not found "
                f"in attributes.nc: {unknown_gru_ids[:10]}"
            )


        for variable_name in spatial_variables:

            variable = ds.variables[
                variable_name
            ]

            expected_dimensions = (
                spatial_variable_dimensions[
                    variable_name
                ]
            )

            if variable.dimensions != expected_dimensions:

                raise RuntimeError(
                    f"{file.name}: "
                    f"{variable_name} has dimensions "
                    f"{variable.dimensions}, "
                    f"expected {expected_dimensions}."
                )

            dimension_sizes = {
                "time": nt,
                "gru": ng,
                "hru": nh,
                "dom": nd,
            }

            expected_shape = tuple(
                dimension_sizes[dimension]
                for dimension in expected_dimensions
            )

            if variable.shape != expected_shape:

                raise RuntimeError(
                    f"{file.name}: "
                    f"{variable_name} has shape "
                    f"{variable.shape}, "
                    f"expected {expected_shape}."
                )


        hru_output_indices = np.concatenate(
            [
                hru_indices_by_gru_id[int(gru_id)]
                for gru_id in gru_ids
            ]
        )

        if len(hru_output_indices) != nh:

            raise RuntimeError(
                f"{file.name}: contains {nh} HRUs, but "
                f"attributes.nc maps {len(hru_output_indices)} "
                "HRUs to this file's GRUs."
            )

        gru_output_indices = np.asarray(
            [
                gru_index_by_id[int(gru_id)]
                for gru_id in gru_ids
            ],
            dtype=np.int64
        )

        valid_files.append(
            (
                start,
                end,
                file,
                ng,
                gru_ids,
                nh,
                nd,
                gru_output_indices,
                hru_output_indices
            )
        )


        print(
            f"OK: {file.name:<32} "
            f"time={nt:<8} "
            f"gru={ng:<5} "
            f"range={start}-{end}"
        )


# ============================================================
# CHECK VALID FILES
# ============================================================

if not valid_files:

    raise RuntimeError(
        "No valid SUMMA day files found."
    )


# ============================================================
# CHECK FOR OVERLAPPING / STALE ARRAY FILES
# ============================================================

for previous, current in zip(
    valid_files[:-1],
    valid_files[1:]
):

    previous_start = previous[0]
    previous_end = previous[1]
    previous_file = previous[2]

    current_start = current[0]
    current_end = current[1]
    current_file = current[2]


    if current_start <= previous_end:

        raise RuntimeError(
            "\nOverlapping SUMMA array outputs detected.\n\n"
            f"Previous: {previous_file.name} "
            f"({previous_start}-{previous_end})\n"
            f"Current : {current_file.name} "
            f"({current_start}-{current_end})\n\n"
            "This usually means an old diagnostic or test "
            "SUMMA file remains in the output directory.\n"
            "Remove stale array outputs before merging."
        )


# ============================================================
# CHECK ARRAY RANGE CONTINUITY
# ============================================================

expected_start = 1


for (
    start,
    end,
    file,
    ng,
    gru_ids,
    nh,
    nd,
    gru_output_indices,
    hru_output_indices
) in valid_files:

    if start != expected_start:

        raise RuntimeError(
            "Gap detected in SUMMA array ranges.\n"
            f"Expected next range to start at GRU "
            f"{expected_start}, "
            f"but {file.name} starts at {start}."
        )

    expected_start = (
        end
        + 1
    )


if expected_start - 1 != expected_grus:

    raise RuntimeError(
        "SUMMA array ranges do not cover all expected GRUs.\n"
        f"Array files cover GRUs 1-{expected_start - 1}, "
        f"but attributes.nc contains {expected_grus} GRUs."
    )

input_hrus = sum(
    item[5]
    for item in valid_files
)

if input_hrus != expected_hrus:

    raise RuntimeError(
        "SUMMA array files do not cover all expected HRUs.\n"
        f"Array files contain {input_hrus} HRUs, "
        f"but attributes.nc contains {expected_hrus}."
    )


# ============================================================
# COMBINE GRU IDS
# ============================================================

all_gru_ids = np.concatenate(
    [
        item[4]
        for item in valid_files
    ]
).astype(
    np.int64
)


# ============================================================
# VALIDATE COMBINED GRUS
# ============================================================

if len(all_gru_ids) != expected_grus:

    raise RuntimeError(
        f"Combined SUMMA files contain "
        f"{len(all_gru_ids)} GRUs, "
        f"but attributes.nc contains "
        f"{expected_grus}."
    )


if len(
    np.unique(all_gru_ids)
) != expected_grus:

    raise RuntimeError(
        "Duplicate gruId values detected "
        "across SUMMA array files."
    )


# Verify the GRU IDs form the same complete set. Input files can
# store them in a different order than attributes.nc.

if not np.array_equal(
    np.sort(all_gru_ids),
    np.sort(expected_gru_ids)
):

    raise RuntimeError(
        "SUMMA array GRU IDs do not match the IDs "
        "in attributes.nc."
    )


print()
print(
    "GRU validation passed: "
    f"{expected_grus} unique GRUs "
    "match attributes.nc."
)


# ============================================================
# REMOVE EXISTING MERGED FILE
# ============================================================

if output_file.exists():

    print()
    print(
        "Removing existing merged file:"
    )
    print(
        output_file
    )

    output_file.unlink()


# ============================================================
# WRITE MERGED FILE
# ============================================================

first_file = valid_files[0][2]


with nc.Dataset(
    first_file
) as source, nc.Dataset(
    output_file,
    "w",
    format="NETCDF4"
) as output:

    # --------------------------------------------------------
    # Dimensions
    # --------------------------------------------------------

    output.createDimension(
        "time",
        ntime
    )

    output.createDimension(
        "gru",
        expected_grus
    )

    output.createDimension(
        "hru",
        expected_hrus
    )

    output.createDimension(
        "dom",
        reference_dom_count
    )


    # --------------------------------------------------------
    # Time
    # --------------------------------------------------------

    src_time = source.variables[
        "time"
    ]

    dst_time = output.createVariable(
        "time",
        src_time.dtype,
        ("time",)
    )


    for attr in src_time.ncattrs():

        dst_time.setncattr(
            attr,
            src_time.getncattr(
                attr
            )
        )


    dst_time[:] = (
        reference_time
    )


    # --------------------------------------------------------
    # GRU coordinate
    # --------------------------------------------------------

    dst_gru = output.createVariable(
        "gru",
        "i4",
        ("gru",)
    )


    dst_gru[:] = np.arange(
        1,
        expected_grus + 1,
        dtype=np.int32
    )


    # --------------------------------------------------------
    # GRU IDs
    # --------------------------------------------------------

    src_gruid = source.variables[
        "gruId"
    ]


    dst_gruid = output.createVariable(
        "gruId",
        src_gruid.dtype,
        ("gru",)
    )


    for attr in src_gruid.ncattrs():

        dst_gruid.setncattr(
            attr,
            src_gruid.getncattr(
                attr
            )
        )


    dst_gruid[:] = (
        expected_gru_ids
    )

    dst_hru_id = output.createVariable(
        "hruId",
        expected_hru_ids.dtype,
        ("hru",)
    )

    dst_hru_id[:] = (
        expected_hru_ids
    )

    dst_hru2gruid = output.createVariable(
        "hru2gruId",
        expected_hru2gru_ids.dtype,
        ("hru",)
    )

    dst_hru2gruid[:] = (
        expected_hru2gru_ids
    )

    # --------------------------------------------------------
    # HRU and domain coordinates
    # --------------------------------------------------------

    src_hru = source.variables.get(
        "hru"
    )

    dst_hru = output.createVariable(
        "hru",
        src_hru.dtype if src_hru is not None else "i4",
        ("hru",)
    )

    if src_hru is not None:

        for attr in src_hru.ncattrs():

            dst_hru.setncattr(
                attr,
                src_hru.getncattr(
                    attr
                )
            )

    dst_hru[:] = np.arange(
        1,
        expected_hrus + 1,
        dtype=dst_hru.dtype
    )

    src_dom = source.variables.get(
        "dom"
    )

    dst_dom = output.createVariable(
        "dom",
        src_dom.dtype if src_dom is not None else "i4",
        ("dom",)
    )

    if src_dom is not None:

        for attr in src_dom.ncattrs():

            dst_dom.setncattr(
                attr,
                src_dom.getncattr(
                    attr
                )
            )

        dst_dom[:] = src_dom[:]

    else:

        dst_dom[:] = np.arange(
            1,
            reference_dom_count + 1,
            dtype=dst_dom.dtype
        )


    # --------------------------------------------------------
    # Spatial variables
    # --------------------------------------------------------

    destination_variables = {}

    for variable_name in spatial_variables:

        src_variable = source.variables[
            variable_name
        ]

        dimensions = spatial_variable_dimensions[
            variable_name
        ]

        if "gru" in dimensions:

            chunksizes = (
                min(8760, ntime),
                min(10, expected_grus),
            )

        else:

            chunksizes = (
                min(8760, ntime),
                min(10, expected_hrus),
                reference_dom_count,
            )

        dst_variable = output.createVariable(
            variable_name,
            src_variable.dtype,
            dimensions,
            zlib=True,
            complevel=1,
            chunksizes=chunksizes
        )

        for attr in src_variable.ncattrs():

            dst_variable.setncattr(
                attr,
                src_variable.getncattr(
                    attr
                )
            )

        destination_variables[
            variable_name
        ] = dst_variable


    # --------------------------------------------------------
    # Copy spatial blocks
    # --------------------------------------------------------

    print()
    time_chunk = 8760

    for variable_name in spatial_variables:

        print(f"Copying {variable_name} data...")
        spatial_dimension = spatial_variable_dimensions[
            variable_name
        ][1]

        for (
            start,
            end,
            file,
            ng,
            gru_ids,
            nh,
            nd,
            gru_output_indices,
            hru_output_indices
        ) in valid_files:

            if spatial_dimension == "gru":

                output_indices = gru_output_indices

            else:

                output_indices = hru_output_indices

            print(
                f"  {file.name}: "
                f"{len(output_indices)} {spatial_dimension} values"
            )

            with nc.Dataset(
                file
            ) as source_part:

                source_variable = (
                    source_part.variables[
                        variable_name
                    ]
                )

                # Copy in time chunks to avoid loading an entire
                # large array file into memory.
                for t0 in range(
                    0,
                    ntime,
                    time_chunk
                ):

                    t1 = min(
                        t0 + time_chunk,
                        ntime
                    )

                    if spatial_dimension == "gru":

                        destination_variables[
                            variable_name
                        ][
                            t0:t1,
                            output_indices
                        ] = source_variable[
                            t0:t1,
                            :
                        ]

                    else:

                        destination_variables[
                            variable_name
                        ][
                            t0:t1,
                            output_indices,
                            :
                        ] = source_variable[
                            t0:t1,
                            :,
                            :
                        ]

    # --------------------------------------------------------
    # Metadata
    # --------------------------------------------------------

    output.setncattr(
        "domain",
        domain_name
    )

    output.setncattr(
        "experiment",
        experiment_id
    )

    output.setncattr(
        "source",
        "Merged SUMMA GRU-array day outputs"
    )

    output.setncattr(
        "created",
        datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
    )

    output.setncattr(
        "number_of_input_files",
        len(
            valid_files
        )
    )


# ============================================================
# VERIFY MERGED OUTPUT
# ============================================================

print()
print("Verifying merged output...")


with nc.Dataset(
    output_file
) as ds:

    # --------------------------------------------------------
    # Dimensions
    # --------------------------------------------------------

    written_ntime = len(
        ds.dimensions["time"]
    )

    written_grus = len(
        ds.dimensions["gru"]
    )


    if written_ntime != ntime:

        raise RuntimeError(
            "Merged time dimension is incorrect.\n"
            f"Expected: {ntime}\n"
            f"Found   : {written_ntime}"
        )


    if written_grus != expected_grus:

        raise RuntimeError(
            "Merged GRU dimension is incorrect.\n"
            f"Expected: {expected_grus}\n"
            f"Found   : {written_grus}"
        )

    written_hrus = len(
        ds.dimensions["hru"]
    )

    if written_hrus != expected_hrus:

        raise RuntimeError(
            "Merged HRU dimension is incorrect.\n"
            f"Expected: {expected_hrus}\n"
            f"Found   : {written_hrus}"
        )


    # --------------------------------------------------------
    # Time coordinate
    # --------------------------------------------------------

    written_time = np.asarray(
        ds.variables["time"][:]
    )


    if not np.array_equal(
        written_time,
        reference_time
    ):

        raise RuntimeError(
            "Time values changed during merge."
        )


    if np.any(
        np.diff(written_time) <= 0
    ):

        raise RuntimeError(
            "Merged time coordinate is not strictly increasing."
        )


    # --------------------------------------------------------
    # GRU IDs
    # --------------------------------------------------------

    written_ids = np.asarray(
        ds.variables[
            "gruId"
        ][:],
        dtype=np.int64
    )


    if not np.array_equal(
        written_ids,
        expected_gru_ids
    ):

        raise RuntimeError(
            "Merged gruId values or ordering are incorrect."
        )

    written_hru_ids = np.asarray(
        ds.variables["hruId"][:],
        dtype=np.int64
    )

    if not np.array_equal(
        written_hru_ids,
        expected_hru_ids
    ):

        raise RuntimeError(
            "Merged hruId values or ordering are incorrect."
        )

    written_hru2gru_ids = np.asarray(
        ds.variables["hru2gruId"][:],
        dtype=np.int64
    )

    if not np.array_equal(
        written_hru2gru_ids,
        expected_hru2gru_ids
    ):

        raise RuntimeError(
            "Merged hru2gruId values or ordering are incorrect."
        )


    for variable_name in spatial_variables:

        variable = ds.variables[
            variable_name
        ]

        expected_dimensions = spatial_variable_dimensions[
            variable_name
        ]

        if variable.dimensions != expected_dimensions:

            raise RuntimeError(
                f"Merged {variable_name} variable has "
                "incorrect dimensions.\n"
                f"Expected: {expected_dimensions}\n"
                f"Found   : {variable.dimensions}"
            )

        dimension_sizes = {
            "time": ntime,
            "gru": expected_grus,
            "hru": expected_hrus,
            "dom": reference_dom_count,
        }

        expected_shape = tuple(
            dimension_sizes[dimension]
            for dimension in expected_dimensions
        )

        if variable.shape != expected_shape:

            raise RuntimeError(
                f"Merged {variable_name} variable has "
                "incorrect shape.\n"
                f"Expected: {expected_shape}\n"
                f"Found   : {variable.shape}"
            )


    runoff = ds.variables[
        "averageRoutedRunoff"
    ]


    # --------------------------------------------------------
    # Sample runoff values
    # --------------------------------------------------------

    sample_indices = sorted(
        set(
            [
                0,
                ntime // 2,
                ntime - 1
            ]
        )
    )


    for index in sample_indices:

        values = np.ma.asarray(
            runoff[
                index,
                :
            ]
        )


        # Use only unmasked values.
        compressed = (
            values.compressed()
        )


        if compressed.size == 0:

            raise RuntimeError(
                "All runoff values are masked at "
                f"day {index}."
            )


        if not np.all(
            np.isfinite(
                compressed
            )
        ):

            raise RuntimeError(
                "Non-finite runoff values detected "
                f"at day {index}."
            )


        print(
            f"  runoff day {index}: "
            f"finite={compressed.size}/{expected_grus}, "
            f"min={compressed.min():.6e}, "
            f"max={compressed.max():.6e}"
        )


# ============================================================
# PROVENANCE
# ============================================================

log_folder = (
    summa_output
    / "_workflow_log"
)


log_folder.mkdir(
    parents=True,
    exist_ok=True
)


copyfile(
    Path(
        __file__
    ).resolve(),
    log_folder
    / Path(
        __file__
    ).name
)


log_file = (
    log_folder
    / (
        f"{datetime.now():%Y%m%d_%H%M%S}_"
        "merge_summa_array_outputs.txt"
    )
)


with log_file.open(
    "w"
) as log:

    log.write(
        f"Date: {datetime.now():%Y-%m-%d %H:%M:%S}\n"
    )

    log.write(
        f"Domain: {domain_name}\n"
    )

    log.write(
        f"Experiment: {experiment_id}\n"
    )

    log.write(
        f"Attributes file: {attributes_file}\n"
    )

    log.write(
        f"Input files: {len(valid_files)}\n"
    )

    log.write(
        f"Time steps: {ntime}\n"
    )

    log.write(
        f"GRUs: {expected_grus}\n"
    )

    log.write(
        f"Output: {output_file}\n"
    )

    log.write(
        "GRU order matches attributes.nc: yes\n"
    )

    log.write(
        "Time axes identical across inputs: yes\n"
    )

    log.write(
        "Spatial variables merged: "
        f"{', '.join(spatial_variables)}\n"
    )

    log.write(
        "Merged runoff sampled for finite values: yes\n"
    )


# ============================================================
# SUMMARY
# ============================================================

print()
print("============================================================")
print("SUMMA ARRAY MERGE COMPLETE")
print("============================================================")

print(f"Input files : {len(valid_files)}")
print(f"Time steps  : {ntime}")
print(f"GRUs        : {expected_grus}")
print(f"Output      : {output_file}")
print(f"Log         : {log_file}")

print()
print("Checks:")
print("  Array ranges     : PASS")
print("  Overlap check    : PASS")
print("  Time axes        : PASS")
print("  GRU uniqueness   : PASS")
print("  GRU order        : PASS")
print("  Spatial variable dimensions: PASS")
print("  Runoff samples   : PASS")

print("============================================================")
