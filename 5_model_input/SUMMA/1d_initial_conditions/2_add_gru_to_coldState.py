#!/usr/bin/env python3
# coding: utf-8
"""Add GRU IDs from trialParams.nc to coldState.nc after matching HRU IDs."""

import argparse
from datetime import datetime
from pathlib import Path

import netCDF4 as nc4
import numpy as np


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


def read_ids(dataset, name, dimension):
    if name not in dataset.variables:
        raise RuntimeError(f"{dataset.filepath()} has no '{name}' variable.")

    variable = dataset[name]
    if variable.dimensions != (dimension,):
        raise RuntimeError(
            f"{dataset.filepath()} variable '{name}' must use only "
            f"the '{dimension}' dimension; found {variable.dimensions}."
        )

    values = np.ma.asarray(variable[:])
    if np.ma.getmaskarray(values).any():
        raise RuntimeError(
            f"{dataset.filepath()} variable '{name}' contains masked IDs."
        )

    values = np.asarray(values)
    if values.ndim != 1 or values.size == 0:
        raise RuntimeError(
            f"{dataset.filepath()} variable '{name}' must be a non-empty "
            "one-dimensional array."
        )
    if not np.issubdtype(values.dtype, np.integer):
        raise RuntimeError(
            f"{dataset.filepath()} variable '{name}' must contain integer IDs."
        )
    if len(np.unique(values)) != values.size:
        raise RuntimeError(
            f"{dataset.filepath()} variable '{name}' contains duplicate IDs."
        )
    return values


def main():
    parser = argparse.ArgumentParser(
        description="Add the trialParams GRU dimension and gruId to coldState.nc."
    )
    parser.add_argument("control_file", type=Path)
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
    trialparams_file = settings_path / read_from_control(
        control_file, "settings_summa_trialParams"
    )

    for path in (coldstate_file, trialparams_file):
        if not path.is_file():
            raise FileNotFoundError(f"Required NetCDF file not found:\n{path}")

    with nc4.Dataset(trialparams_file) as trialparams:
        if "hru" not in trialparams.dimensions or "gru" not in trialparams.dimensions:
            raise RuntimeError(
                f"{trialparams_file} must contain 'hru' and 'gru' dimensions."
            )

        trial_hru_ids = read_ids(trialparams, "hruId", "hru")
        gru_ids = read_ids(trialparams, "gruId", "gru")
        if len(gru_ids) != trialparams.dimensions["gru"].size:
            raise RuntimeError(
                f"{trialparams_file} gruId length does not match its 'gru' dimension."
            )

        gru_variable = trialparams["gruId"]
        gru_dtype = gru_variable.dtype
        gru_attrs = {
            attr: gru_variable.getncattr(attr)
            for attr in gru_variable.ncattrs()
            if attr != "_FillValue"
        }

    with nc4.Dataset(coldstate_file) as coldstate:
        if "hru" not in coldstate.dimensions:
            raise RuntimeError(f"{coldstate_file} has no 'hru' dimension.")

        coldstate_hru_ids = read_ids(coldstate, "hruId", "hru")
        if len(coldstate_hru_ids) != coldstate.dimensions["hru"].size:
            raise RuntimeError(
                f"{coldstate_file} hruId length does not match its 'hru' dimension."
            )

        if not np.array_equal(np.sort(coldstate_hru_ids), np.sort(trial_hru_ids)):
            raise RuntimeError(
                "coldState.nc and trialParams.nc contain different HRU ID sets; "
                "refusing to add GRU IDs."
            )

        if "gru" in coldstate.dimensions:
            if coldstate.dimensions["gru"].size != len(gru_ids):
                raise RuntimeError(
                    f"{coldstate_file} already has a 'gru' dimension with the "
                    "wrong size."
                )
        if "gruId" in coldstate.variables:
            existing = coldstate["gruId"]
            if existing.dimensions != ("gru",) or not np.array_equal(
                np.asarray(existing[:]), gru_ids
            ):
                raise RuntimeError(
                    f"{coldstate_file} already has a conflicting 'gruId' variable."
                )

    with nc4.Dataset(coldstate_file, "a") as coldstate:
        changed = False
        if "gru" not in coldstate.dimensions:
            coldstate.createDimension("gru", len(gru_ids))
            changed = True

        if "gruId" not in coldstate.variables:
            variable = coldstate.createVariable("gruId", gru_dtype, ("gru",))
            for name, value in gru_attrs.items():
                variable.setncattr(name, value)
            variable[:] = gru_ids
            changed = True

        if changed:
            coldstate.setncattr(
                "History",
                str(getattr(coldstate, "History", ""))
                + " | Added gru and gruId from "
                + f"{trialparams_file} after matching hruId on "
                + f"{datetime.now():%Y/%m/%d %H:%M:%S}",
            )

    print(f"coldState.nc : {coldstate_file}")
    print(f"trialParams.nc: {trialparams_file}")
    print(f"HRU IDs matched: {len(coldstate_hru_ids)}")
    print(f"GRUs added    : {len(gru_ids)}")


if __name__ == "__main__":
    main()
