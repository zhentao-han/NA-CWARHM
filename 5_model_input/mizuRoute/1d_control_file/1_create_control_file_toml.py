#!/usr/bin/env python3
# coding: utf-8

"""
Create mizuroute.control (TOML format) for a selected NWAM/CWARHM domain.

Purpose
-------
Create the mizuRoute runtime control file using an explicitly
specified domain control file.

The generated control has three sections:

  [mizuRoute]   routing parameter namelist, routing method, time step,
                output switches
  [simulation]  simulation switches
  [hydrofabric] topology file and variable names

IMPORTANT
---------
This script does NOT read, create, or modify control_active.txt.

Usage
-----
python 1_create_control_file.py \
/path/to/control_DOMAIN.txt
"""


import sys
from pathlib import Path
from shutil import copy2
from datetime import datetime


# ============================================================
# CONTROL FILE
# ============================================================

if len(sys.argv) != 2:

    raise SystemExit(
        "Usage:\n"
        "python 1_create_control_file.py "
        "/path/to/control_DOMAIN.txt"
    )


CONTROL_FILE = Path(
    sys.argv[1]
).resolve()


if not CONTROL_FILE.exists():

    raise FileNotFoundError(
        "Control file not found:\n"
        f"{CONTROL_FILE}"
    )


if not CONTROL_FILE.is_file():

    raise RuntimeError(
        "Control-file path is not a file:\n"
        f"{CONTROL_FILE}"
    )


# ============================================================
# PROJECT PATHS
# ============================================================

SCRIPT_DIR = Path(
    __file__
).resolve().parent


# Script location:
#
# CWARHM_multibasin/
#   5_model_input/
#     mizuRoute/
#       1d_control_file/
#         1_create_control_file.py

CWARHM_ROOT = (
    SCRIPT_DIR.parents[2]
)


# ============================================================
# CONTROL FUNCTIONS
# ============================================================

def read_from_control(
    file,
    setting
):
    """
    Read one control setting using exact key matching.
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


def make_default_path(
    suffix
):
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


def resolve_path(
    setting,
    default_suffix
):
    """
    Resolve a control-file path setting.
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


# ============================================================
# DOMAIN / EXPERIMENT
# ============================================================

domain_name = read_from_control(
    CONTROL_FILE,
    "domain_name"
)


experiment_id = read_from_control(
    CONTROL_FILE,
    "experiment_id"
)


# ============================================================
# MIZUROUTE SETTINGS DIRECTORY
# ============================================================

control_path = resolve_path(
    "settings_mizu_path",
    "settings/mizuRoute"
)


control_name = read_from_control(
    CONTROL_FILE,
    "settings_mizu_control_file"
)


control_path.mkdir(
    parents=True,
    exist_ok=True
)


control_output = (
    control_path
    / control_name
)


# mizuRoute ancillary directory.
# Used for both namelist_path and hfabric_path.

path_to_settings = (
    control_path
)


# ============================================================
# PARAMETER NAMELIST
# ============================================================

parameter_name = read_from_control(
    CONTROL_FILE,
    "settings_mizu_parameters"
)


parameter_file = (
    path_to_settings
    / parameter_name
)


if not parameter_file.exists():

    raise FileNotFoundError(
        "mizuRoute parameter namelist not found:\n"
        f"{parameter_file}\n\n"
        "Run the mizuRoute base-settings copy step first."
    )


# ============================================================
# TOPOLOGY FILE
# ============================================================

topology_name = read_from_control(
    CONTROL_FILE,
    "settings_mizu_topology"
)


topology_file = (
    path_to_settings
    / topology_name
)


if not topology_file.exists():

    raise FileNotFoundError(
        "mizuRoute topology file not found:\n"
        f"{topology_file}\n\n"
        "Run 1_create_network_topology_file.py first."
    )


# Output topology file written by mizuRoute.

topology_new_name = "topology_new.nc"


# Names generated by topology.nc.

topology_seg_dim = "seg"
topology_hru_dim = "hru"

topology_var_area = "area"
topology_var_length = "length"
topology_var_slope = "slope"

topology_var_hru_id = "hruId"
topology_var_hru_to_seg = "hruToSegId"

topology_var_seg_id = "segId"
topology_var_down_seg_id = "downSegId"


# Negative value means use the complete supplied topology.

topology_outlet = -9999


# ============================================================
# ROUTING METHOD
# ============================================================

# Historical CWARHM control key:
#
# settings_mizu_output_vars
#
# is being retained here because it currently stores route_opt
# in the existing control files.

route_opt_text = read_from_control(
    CONTROL_FILE,
    "settings_mizu_output_vars"
)


try:

    route_opt = int(
        route_opt_text
    )

except ValueError as exc:

    raise ValueError(
        "settings_mizu_output_vars currently represents "
        "mizuRoute route_opt and must be an integer."
    ) from exc


valid_route_options = {
    0,
    1,
    2,
    3,
    4,
    5,
}


if route_opt not in valid_route_options:

    raise ValueError(
        "Invalid mizuRoute route_opt.\n"
        "Expected:\n"
        "0 = Sum\n"
        "1 = IRF\n"
        "2 = KWT\n"
        "3 = KW\n"
        "4 = MC\n"
        "5 = DW"
    )


# ============================================================
# ROUTING TIME STEP
# ============================================================

routing_dt_text = read_from_control(
    CONTROL_FILE,
    "settings_mizu_routing_dt"
)


try:

    routing_dt_value = float(
        routing_dt_text
    )

except ValueError as exc:

    raise ValueError(
        "settings_mizu_routing_dt must be numeric."
    ) from exc


if routing_dt_value <= 0:

    raise ValueError(
        "settings_mizu_routing_dt must be > 0."
    )


# Use integer text where possible.

if routing_dt_value.is_integer():

    routing_dt = str(
        int(
            routing_dt_value
        )
    )

else:

    routing_dt = str(
        routing_dt_value
    )


# ============================================================
# OUTPUT SWITCHES / SIMULATION SWITCHES
# ============================================================

write_qbasin = "false"
write_qreach = "false"

use_mizuroute = "false"


# ============================================================
# REPORT BEFORE WRITING
# ============================================================

print()
print("=" * 70)
print("CREATE MIZUROUTE CONTROL FILE")
print("=" * 70)

print(
    f"Domain           : {domain_name}"
)

print(
    f"Control file     : {CONTROL_FILE}"
)

print(
    f"Experiment       : {experiment_id}"
)

print(
    f"Settings path    : {path_to_settings}"
)

print(
    f"Parameters       : {parameter_file}"
)

print(
    f"Topology         : {topology_file}"
)

print(
    f"Topology (new)   : {topology_new_name}"
)

print(
    f"Route option     : {route_opt}"
)

print(
    f"Routing dt       : {routing_dt} s"
)

print(
    f"write_qbasin     : {write_qbasin}"
)

print(
    f"write_Qreach     : {write_qreach}"
)

print(
    f"Control output   : {control_output}"
)


# ============================================================
# BUILD CONTROL FILE
# ============================================================

# String values are quoted, numbers and booleans are not.

settings_dir_text = (
    f"{path_to_settings.as_posix()}/"
)


control_lines = [

    "[mizuRoute]",
    "",
    f'namelist_path = "{settings_dir_text}"',
    f'namelist_file = "{parameter_name}"',
    "",
    f'methods = "{route_opt}"',
    "",
    f"dt = {routing_dt}",
    "",
    f"write_qbasin = {write_qbasin}",
    f"write_Qreach = {write_qreach}",
    "",
    "[simulation]",
    "",
    f"use_mizuroute    = {use_mizuroute}",
    "# write_timeseries = true",
    "",
    "[hydrofabric]",
    "",
    f'hfabric_path    = "{settings_dir_text}"',
    f'hfabric_file    = "{topology_name}"',
    f'hfabric_newfile = "{topology_new_name}"',
    "",
    f'dname_seg = "{topology_seg_dim}"',
    f'dname_hru = "{topology_hru_dim}"',
    "",
    f'varname_HRUid     = "{topology_var_hru_id}"',
    f'varname_segId     = "{topology_var_seg_id}"',
    f'varname_hruSegId  = "{topology_var_hru_to_seg}"',
    f'varname_downSegId = "{topology_var_down_seg_id}"',
    "",
    f'varname_area   = "{topology_var_area}"',
    f'varname_slope  = "{topology_var_slope}"',
    f'varname_length = "{topology_var_length}"',
    "",
    f"seg_outlet = {topology_outlet}",
]


# ============================================================
# WRITE
# ============================================================

control_output.write_text(
    "\n".join(
        control_lines
    )
    + "\n"
)


# ============================================================
# VERIFY GENERATED CONTROL
# ============================================================

if not control_output.exists():

    raise RuntimeError(
        "mizuroute.control was not created."
    )


generated_lines = (
    control_output
    .read_text()
    .splitlines()
)


control_text = "\n".join(
    generated_lines
)


# ------------------------------------------------------------
# Required sections
# ------------------------------------------------------------

for section in (
    "[mizuRoute]",
    "[simulation]",
    "[hydrofabric]",
):

    if section not in generated_lines:

        raise RuntimeError(
            "Generated mizuroute.control is missing "
            f"section {section}"
        )


# ------------------------------------------------------------
# Required keys
# ------------------------------------------------------------

required_keys = [
    "namelist_path",
    "namelist_file",
    "methods",
    "dt",
    "write_qbasin",
    "write_Qreach",
    "use_mizuroute",
    "hfabric_path",
    "hfabric_file",
    "hfabric_newfile",
    "dname_seg",
    "dname_hru",
    "varname_HRUid",
    "varname_segId",
    "varname_hruSegId",
    "varname_downSegId",
    "varname_area",
    "varname_slope",
    "varname_length",
    "seg_outlet",
]


missing_keys = [
    key
    for key in required_keys
    if not any(
        line.split("=", 1)[0].strip() == key
        for line in generated_lines
        if "=" in line
        and not line.lstrip().startswith("#")
    )
]


if missing_keys:

    raise RuntimeError(
        "Generated mizuroute.control is missing "
        "required keys:\n"
        + "\n".join(
            missing_keys
        )
    )


# ------------------------------------------------------------
# Verify exact settings
# ------------------------------------------------------------

required_exact_lines = {
    f'methods = "{route_opt}"',
    f"dt = {routing_dt}",
    f"use_mizuroute    = {use_mizuroute}",
    f"seg_outlet = {topology_outlet}",
}


missing_exact_lines = (
    required_exact_lines
    - set(
        generated_lines
    )
)


if missing_exact_lines:

    raise RuntimeError(
        "Generated mizuroute.control does not "
        "contain the required exact settings:\n"
        + "\n".join(
            sorted(
                missing_exact_lines
            )
        )
    )


# ------------------------------------------------------------
# Verify the file parses as TOML (Python >= 3.11)
# ------------------------------------------------------------

try:

    import tomllib

except ImportError:

    tomllib = None


if tomllib is not None:

    try:

        parsed = tomllib.loads(
            control_text
        )

    except tomllib.TOMLDecodeError as exc:

        raise RuntimeError(
            "Generated mizuroute.control is not "
            "valid TOML:\n"
            f"{exc}"
        ) from exc

    if parsed["mizuRoute"]["methods"] != str(route_opt):

        raise RuntimeError(
            "Parsed 'methods' does not match route_opt."
        )

    if parsed["hydrofabric"]["seg_outlet"] != topology_outlet:

        raise RuntimeError(
            "Parsed 'seg_outlet' does not match "
            "the expected value."
        )

    # write_qbasin / write_Qreach may be true or false;
    # only require that they parse as booleans.

    for key in (
        "write_qbasin",
        "write_Qreach",
    ):

        if not isinstance(
            parsed["mizuRoute"][key],
            bool
        ):

            raise RuntimeError(
                f"Parsed '{key}' must be true or false."
            )

else:

    print(
        "Python < 3.11: tomllib unavailable, "
        "TOML parse check skipped."
    )


# ============================================================
# WORKFLOW LOG
# ============================================================

log_folder = (
    control_path
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
    Path(__file__).resolve(),
    log_folder
    / this_file
)


# Preserve the actual domain-specific control file,
# under its actual filename.

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
        "create_mizuroute_control.txt"
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
        f"Experiment: {experiment_id}\n"
    )

    file.write(
        f"Route option (methods): {route_opt}\n"
    )

    file.write(
        f"Routing timestep (dt): {routing_dt} s\n"
    )

    file.write(
        f"write_qbasin: {write_qbasin}\n"
    )

    file.write(
        f"write_Qreach: {write_qreach}\n"
    )

    file.write(
        f"use_mizuroute: {use_mizuroute}\n"
    )

    file.write(
        f"Namelist: {parameter_file}\n"
    )

    file.write(
        f"Topology: {topology_file}\n"
    )

    file.write(
        f"Topology (new): {topology_new_name}\n"
    )

    file.write(
        f"seg_outlet: {topology_outlet}\n"
    )

    file.write(
        f"Control output: {control_output}\n"
    )

    file.write(
        "Shared control_active.txt used: no\n"
    )


# ============================================================
# FINAL SUMMARY
# ============================================================

print()
print("=" * 70)
print("MIZUROUTE CONTROL FILE CREATION COMPLETED")
print("=" * 70)

print(
    f"Domain           : {domain_name}"
)

print(
    f"Control file     : {CONTROL_FILE}"
)

print(
    f"Experiment       : {experiment_id}"
)

print(
    f"Route option     : {route_opt}"
)

print(
    f"Routing dt       : {routing_dt} s"
)

print(
    f"Output           : {control_output}"
)

print(
    f"Workflow log     : {log_file}"
)

print()
print(
    "Control syntax validation passed."
)

print(
    "No control_active.txt was created or modified."
)
