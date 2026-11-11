#!/usr/bin/env python3
# coding: utf-8
"""
Copy calibrated cold-state variables into coldState.nc, matched by gruId.

All variables except hruId, gruId, and dt_init are copied from each
coldState*.nc found recursively under calib_params_file_path.

Usage
-----
python 3_copy_coldState.py /path/to/control_DOMAIN.txt [--no-backup]
"""

import argparse
import shutil
from datetime import datetime
from pathlib import Path

import netCDF4 as nc4
import numpy as np

SKIP = {"hruId", "gruId", "dt_init"}


def read_from_control(control_file, setting):
    """Read one setting using exact control-key matching."""
    with open(control_file) as contents:
        for line in contents:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "|" not in stripped:
                continue
            left, right = stripped.split("|", 1)
            if left.strip() != setting:
                continue
            value = right.split("#", 1)[0].strip()
            if not value:
                raise ValueError(f"Setting '{setting}' is empty in:\n{control_file}")
            return value
    raise ValueError(f"Setting '{setting}' not found in:\n{control_file}")


def resolve_path(control_file, setting, default_suffix):
    value = read_from_control(control_file, setting)
    if value != "default":
        return Path(value)

    root_path = Path(read_from_control(control_file, "root_path"))
    domain_name = read_from_control(control_file, "domain_name")
    return root_path / f"domain_{domain_name}" / default_suffix


def read_ids(dataset):
    if "gruId" not in dataset.variables:
        raise RuntimeError(f"{dataset.filepath()} has no 'gruId' variable.")
    if "gru" not in dataset.dimensions:
        raise RuntimeError(f"{dataset.filepath()} has no 'gru' dimension.")

    variable = dataset["gruId"]
    if variable.dimensions != ("gru",):
        raise RuntimeError(
            f"{dataset.filepath()} variable 'gruId' must use only the "
            f"'gru' dimension; found {variable.dimensions}."
        )

    values = np.ma.asarray(variable[:])
    if np.ma.getmaskarray(values).any():
        raise RuntimeError(f"{dataset.filepath()} contains masked gruId values.")
    values = np.asarray(values)
    if values.ndim != 1 or values.size != dataset.dimensions["gru"].size:
        raise RuntimeError(
            f"{dataset.filepath()} gruId length does not match its 'gru' dimension."
        )
    if not np.issubdtype(values.dtype, np.integer):
        raise RuntimeError(f"{dataset.filepath()} gruId values must be integers.")
    if len(np.unique(values)) != values.size:
        raise RuntimeError(f"{dataset.filepath()} contains duplicate gruId values.")
    return values.astype(np.int64)


def read_unmasked_values(variable, file_path):
    values = np.ma.asarray(variable[:])
    if np.ma.getmaskarray(values).any():
        raise RuntimeError(
            f"{file_path} variable '{variable.name}' contains masked values."
        )
    return np.asarray(values)


def main():
    parser = argparse.ArgumentParser(
        description="Copy calibrated cold-state variables into coldState.nc."
    )
    parser.add_argument("control_file", type=Path)
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()

    control_file = args.control_file.resolve()
    if not control_file.is_file():
        raise FileNotFoundError(f"Control file not found:\n{control_file}")

    settings_path = resolve_path(
        control_file, "settings_summa_path", "settings/SUMMA"
    )
    coldstate_file = settings_path / read_from_control(
        control_file, "settings_summa_coldstate"
    )

    calib_value = read_from_control(control_file, "calib_params_file_path")
    if calib_value == "default":
        raise ValueError(
            "calib_params_file_path is 'default' in the control file; "
            "set it to the directory holding the coldState*.nc files."
        )
    calib_path = Path(calib_value)

    if not coldstate_file.is_file():
        raise FileNotFoundError(f"coldState file (dst) not found:\n{coldstate_file}")
    if not calib_path.is_dir():
        raise FileNotFoundError(f"calib_params_file_path not found:\n{calib_path}")

    dst_resolved = coldstate_file.resolve()
    src_files = sorted(
        path
        for path in calib_path.rglob("coldState*.nc")
        if path.resolve() != dst_resolved
    )
    if not src_files:
        raise RuntimeError(f"No coldState*.nc files found under:\n{calib_path}")

    print()
    print("=" * 70)
    print("COPY CALIBRATION STATES INTO coldState.nc")
    print("=" * 70)
    print(f"Control file : {control_file}")
    print(f"dst          : {coldstate_file}")
    print(f"src dir      : {calib_path}")
    print(f"src files    : {len(src_files)}")
    for path in src_files:
        print(f"   {path}")

    with nc4.Dataset(coldstate_file) as dst:
        dst_gru = read_ids(dst)
        if "hru" not in dst.dimensions:
            raise RuntimeError(f"{coldstate_file} has no 'hru' dimension.")
        if dst.dimensions["hru"].size != len(dst_gru):
            raise RuntimeError(
                "dst hru and gru sizes differ; cannot match hru variables by gruId."
            )

        dst_index = {int(gru_id): index for index, gru_id in enumerate(dst_gru)}
        result = {}

        for src_file in src_files:
            with nc4.Dataset(src_file) as src:
                if "gruId" not in src.variables:
                    print(f"SKIP {src_file.name}: no gruId variable")
                    continue
                src_gru = read_ids(src)
                if "hru" in src.dimensions and src.dimensions["hru"].size != len(src_gru):
                    raise RuntimeError(
                        f"{src_file}: hru and gru sizes differ; "
                        "cannot match hru variables by gruId."
                    )

                src_index = {int(gru_id): index for index, gru_id in enumerate(src_gru)}
                src_for_dst = np.array(
                    [src_index.get(int(gru_id), -1) for gru_id in dst_gru],
                    dtype=np.int64,
                )
                found = src_for_dst >= 0
                dst_indices = np.flatnonzero(found)
                src_indices = src_for_dst[found]
                print(
                    f"\n{src_file.name}: matched {len(dst_indices)} "
                    f"of {len(dst_gru)} dst GRUs"
                )

                for name, variable in src.variables.items():
                    if name in SKIP:
                        continue

                    unit_dims = [
                        dim for dim in variable.dimensions if dim in ("hru", "gru")
                    ]
                    if len(unit_dims) != 1:
                        raise RuntimeError(
                            f"{src_file} variable '{name}' must have exactly one "
                            f"'hru' or 'gru' dimension; found {variable.dimensions}."
                        )
                    unit_dim = unit_dims[0]
                    axis = variable.dimensions.index(unit_dim)
                    if unit_dim not in src.dimensions:
                        raise RuntimeError(
                            f"{src_file} variable '{name}' uses missing "
                            f"dimension '{unit_dim}'."
                        )
                    if variable.shape[axis] != len(src_gru):
                        raise RuntimeError(
                            f"{src_file} variable '{name}' length along "
                            f"'{unit_dim}' does not match its gruId values."
                        )

                    for dim in variable.dimensions:
                        if dim not in dst.dimensions:
                            raise RuntimeError(
                                f"{coldstate_file} has no '{dim}' dimension required "
                                f"by variable '{name}'."
                            )
                        if (
                            dim != unit_dim
                            and src.dimensions[dim].size
                            != dst.dimensions[dim].size
                        ):
                            raise RuntimeError(
                                f"{name}: dimension '{dim}' has size "
                                f"{src.dimensions[dim].size} in {src_file} but "
                                f"{dst.dimensions[dim].size} in {coldstate_file}."
                            )
                    if name in dst.variables:
                        dst_variable = dst[name]
                        if dst_variable.dimensions != variable.dimensions:
                            raise RuntimeError(
                                f"{name}: dst dims {dst_variable.dimensions} != "
                                f"src dims {variable.dimensions}"
                            )
                        output = result.get(name)
                        if output is None:
                            output = np.ma.asarray(dst_variable[:]).copy()
                            result[name] = {
                                "dimensions": variable.dimensions,
                                "values": output,
                                "filled": np.zeros(len(dst_gru), dtype=bool),
                                "attrs": {},
                                "dtype": dst_variable.dtype,
                                "fill_value": (
                                    dst_variable.getncattr("_FillValue")
                                    if "_FillValue" in dst_variable.ncattrs()
                                    else None
                                ),
                            }
                    else:
                        output = result.get(name)
                        if output is None:
                            shape = tuple(dst.dimensions[dim].size for dim in variable.dimensions)
                            output = np.ma.masked_all(shape, dtype=variable.dtype)
                            attrs = {
                                attr: variable.getncattr(attr)
                                for attr in variable.ncattrs()
                                if attr != "_FillValue"
                            }
                            result[name] = {
                                "dimensions": variable.dimensions,
                                "values": output,
                                "filled": np.zeros(len(dst_gru), dtype=bool),
                                "attrs": attrs,
                                "dtype": variable.dtype,
                                "fill_value": (
                                    variable.getncattr("_FillValue")
                                    if "_FillValue" in variable.ncattrs()
                                    else None
                                ),
                            }
                        elif result[name]["dimensions"] != variable.dimensions:
                            raise RuntimeError(
                                f"{name}: inconsistent dimensions in {src_file}; "
                                f"expected {result[name]['dimensions']}, "
                                f"found {variable.dimensions}"
                            )

                    output_info = result[name]
                    values = read_unmasked_values(variable, src_file)
                    overlap = int((output_info["filled"] & found).sum())
                    if overlap:
                        print(
                            f"  warning: {name}: {overlap} GRUs already filled "
                            f"by an earlier file; overwritten by {src_file.name}"
                        )

                    selection = [slice(None)] * values.ndim
                    selection[axis] = dst_indices
                    output_info["values"][tuple(selection)] = np.take(
                        values, src_indices, axis=axis
                    )
                    output_info["filled"] |= found

    if not result:
        raise RuntimeError("No copyable variables were found in source files.")

    if not args.no_backup:
        backup = coldstate_file.with_name(coldstate_file.name + ".bak")
        shutil.copy2(coldstate_file, backup)
        print(f"Backup       : {backup}")

    with nc4.Dataset(coldstate_file, "a") as dst:
        for name, info in result.items():
            if name in dst.variables:
                variable = dst[name]
                variable[:] = info["values"]
                action = "Overwrote"
            else:
                kwargs = {}
                if info["fill_value"] is not None:
                    kwargs["fill_value"] = info["fill_value"]
                variable = dst.createVariable(
                    name,
                    info["dtype"],
                    info["dimensions"],
                    **kwargs,
                )
                for attr, value in info["attrs"].items():
                    variable.setncattr(attr, value)
                variable[:] = info["values"]
                action = "Created  "

            missing = int((~info["filled"]).sum())
            print(
                f"{action} {name}{info['dimensions']}"
                + (f"  [{missing} dst GRUs not found in sources]" if missing else "")
            )

        dst.setncattr(
            "History",
            str(getattr(dst, "History", ""))
            + f" | State variables copied by gruId from {len(src_files)} "
            + f"file(s) under {calib_path} on {datetime.now():%Y/%m/%d %H:%M:%S}",
        )

    print("\nDone.")


if __name__ == "__main__":
    main()
