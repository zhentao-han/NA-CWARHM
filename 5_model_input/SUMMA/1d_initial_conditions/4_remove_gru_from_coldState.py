#!/usr/bin/env python3
# coding: utf-8
"""Remove the GRU dimension and gruId variable from coldState.nc."""

import argparse
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import netCDF4 as nc4


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


def variable_creation_options(variable):
    """Return NetCDF creation options needed to retain storage settings."""
    options = {
        "zlib": False,
        "complevel": 0,
        "shuffle": False,
        "fletcher32": False,
        "endian": variable.endian(),
    }

    filters = variable.filters()
    options["zlib"] = filters.get("zlib", False)
    options["complevel"] = filters.get("complevel", 0)
    options["shuffle"] = filters.get("shuffle", False)
    options["fletcher32"] = filters.get("fletcher32", False)

    chunking = variable.chunking()
    if isinstance(chunking, str) and chunking == "contiguous":
        options["contiguous"] = True
    elif not isinstance(chunking, str):
        options["chunksizes"] = chunking

    if "_FillValue" in variable.ncattrs():
        options["fill_value"] = variable.getncattr("_FillValue")

    return options


def copy_without_gru(source_path, temporary_path):
    with nc4.Dataset(source_path) as source:
        if "gru" not in source.dimensions and "gruId" not in source.variables:
            return False

        dependent_variables = [
            name
            for name, variable in source.variables.items()
            if name != "gruId" and "gru" in variable.dimensions
        ]
        if dependent_variables:
            raise RuntimeError(
                "Cannot remove the 'gru' dimension because these variables "
                "depend on it:\n"
                + "\n".join(f"  {name}" for name in dependent_variables)
            )

        expected_variables = {
            name for name in source.variables if name != "gruId"
        }

        with nc4.Dataset(
            temporary_path,
            "w",
            format=source.data_model,
        ) as destination:
            for name in source.ncattrs():
                if name != "_NCProperties":
                    destination.setncattr(name, source.getncattr(name))

            destination.setncattr(
                "History",
                str(getattr(source, "History", ""))
                + f" | Removed gru and gruId on {datetime.now():%Y/%m/%d %H:%M:%S}",
            )

            for name, dimension in source.dimensions.items():
                if name == "gru":
                    continue
                size = None if dimension.isunlimited() else len(dimension)
                destination.createDimension(name, size)

            for name, variable in source.variables.items():
                if name == "gruId":
                    continue
                output_variable = destination.createVariable(
                    name,
                    variable.datatype,
                    variable.dimensions,
                    **variable_creation_options(variable),
                )
                for attr in variable.ncattrs():
                    if attr != "_FillValue":
                        output_variable.setncattr(
                            attr, variable.getncattr(attr)
                        )
                output_variable[...] = variable[...]

    with nc4.Dataset(temporary_path) as check:
        if "gru" in check.dimensions or "gruId" in check.variables:
            raise RuntimeError("Temporary coldState file still contains GRU data.")
        if set(check.variables) != expected_variables:
            raise RuntimeError(
                "Temporary coldState file does not contain the expected variables."
            )
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Remove the gru dimension and gruId variable from coldState.nc."
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
    if not coldstate_file.is_file():
        raise FileNotFoundError(f"coldState file not found:\n{coldstate_file}")

    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{coldstate_file.name}.",
        suffix=".tmp.nc",
        dir=coldstate_file.parent,
    )
    os.close(file_descriptor)
    temporary_path = Path(temporary_name)

    try:
        changed = copy_without_gru(coldstate_file, temporary_path)
        if not changed:
            print(f"No GRU dimension or gruId variable found in {coldstate_file}; unchanged.")
            return

        if not args.no_backup:
            backup = coldstate_file.with_name(coldstate_file.name + ".bak")
            shutil.copy2(coldstate_file, backup)
            print(f"Backup: {backup}")

        os.replace(temporary_path, coldstate_file)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()

    print(f"Removed the 'gru' dimension and 'gruId' variable from:\n{coldstate_file}")


if __name__ == "__main__":
    main()
