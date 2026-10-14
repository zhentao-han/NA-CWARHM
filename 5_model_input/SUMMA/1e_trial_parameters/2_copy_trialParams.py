#!/usr/bin/env python3
# coding: utf-8
"""
Copy a-priori / calibrated parameter variables into trialParams.nc.

src : every trialParam*.nc found under `calib_params_file_path`
      (read from the control file; searched recursively)
dst : trialparams_file
      = <settings_summa_path>/<settings_summa_trialParams>
      (same definition as in 1_create_trialParams.py)

All variables except hruId and gruId are copied from each src file to dst,
matched on gruId.

Usage
-----
python copy_calib_params_to_trialParams.py /path/to/control_DOMAIN.txt [--no-backup]
"""

import argparse
import shutil
from pathlib import Path
from datetime import datetime

import netCDF4 as nc4
import numpy as np
import pandas as pd

SKIP = {"hruId", "gruId"}

# ============================================================
# CONTROL FILE (same helpers as 1_create_trialParams.py)
# ============================================================

ap = argparse.ArgumentParser()
ap.add_argument("control_file")
ap.add_argument("--no-backup", action="store_true")
args = ap.parse_args()

CONTROL_FILE = Path(args.control_file).resolve()
if not CONTROL_FILE.exists():
    raise FileNotFoundError(f"Control file not found:\n{CONTROL_FILE}")


def read_from_control(file, setting):
    """Read one setting using exact control-key matching."""
    with open(file) as contents:
        for line in contents:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "|" not in stripped:
                continue
            left, right = stripped.split("|", 1)
            if left.strip() != setting:
                continue
            value = right.split("#", 1)[0].strip()
            if value == "":
                raise ValueError(f"Setting '{setting}' is empty in:\n{file}")
            return value
    raise ValueError(f"Setting '{setting}' not found in:\n{file}")


def make_default_path(suffix):
    root_path = Path(read_from_control(CONTROL_FILE, "root_path"))
    domain_name = read_from_control(CONTROL_FILE, "domain_name")
    return root_path / f"domain_{domain_name}" / suffix


def resolve_path(setting, default_suffix):
    value = read_from_control(CONTROL_FILE, setting)
    if value == "default":
        return make_default_path(default_suffix)
    return Path(value)


# ============================================================
# PATHS
# ============================================================

settings_path = resolve_path("settings_summa_path", "settings/SUMMA")
trialparams_name = read_from_control(CONTROL_FILE, "settings_summa_trialParams")
trialparams_file = settings_path / trialparams_name

calib_value = read_from_control(CONTROL_FILE, "calib_params_file_path")
if calib_value == "default":
    raise ValueError(
        "calib_params_file_path is 'default' in the control file; "
        "set it to the directory holding the trialParam*.nc files."
    )
calib_path = Path(calib_value)

if not trialparams_file.exists():
    raise FileNotFoundError(f"trialParams file (dst) not found:\n{trialparams_file}")
if not calib_path.exists():
    raise FileNotFoundError(f"calib_params_file_path not found:\n{calib_path}")

# trialParams.nc itself matches the pattern trialParam*.nc, so exclude it
dst_resolved = trialparams_file.resolve()
src_files = sorted(
    p for p in calib_path.rglob("trialParam*.nc") if p.resolve() != dst_resolved
)
if not src_files:
    raise RuntimeError(f"No trialParam*.nc files found under:\n{calib_path}")

print()
print("=" * 70)
print("COPY CALIBRATION PARAMETERS INTO trialParams.nc")
print("=" * 70)
print(f"Control file : {CONTROL_FILE}")
print(f"dst          : {trialparams_file}")
print(f"src dir      : {calib_path}")
print(f"src files    : {len(src_files)}")
for p in src_files:
    print(f"   {p}")

if not args.no_backup:
    backup = trialparams_file.with_name(trialparams_file.name + ".bak")
    shutil.copy2(trialparams_file, backup)
    print(f"Backup       : {backup}")


def read_values(var):
    data = var[:]
    if np.ma.isMaskedArray(data):
        data = data.filled(np.nan)
    return np.asarray(data, dtype=np.float64)


# ============================================================
# COPY
# ============================================================

with nc4.Dataset(trialparams_file, "a") as dst:
    if "gruId" not in dst.variables:
        raise RuntimeError("dst has no gruId variable; cannot match on gruId.")
    if "hru" not in dst.dimensions:
        raise RuntimeError("dst has no 'hru' dimension.")

    dst_gru = np.asarray(dst["gruId"][:]).astype("int64")
    n = len(dst_gru)

    # hru-dimension variables are matched through gruId, which assumes one HRU
    # per GRU in the same order (hru size == gru size) in both dst and src.
    if dst.dimensions["hru"].size != dst.dimensions["gru"].size:
        raise RuntimeError("dst hru and gru sizes differ; cannot match hru variables by gruId.")

    # accumulated result per variable: (dimension, attrs, values, filled-mask)
    result = {}
    never_matched = np.ones(n, dtype=bool)

    for src_file in src_files:
        with nc4.Dataset(src_file) as src:
            if "gruId" not in src.variables:
                print(f"SKIP {src_file.name}: no gruId variable")
                continue
            src_gru = np.asarray(src["gruId"][:]).astype("int64")
            if len(np.unique(src_gru)) != len(src_gru):
                raise RuntimeError(f"Duplicate gruId values in {src_file}")
            if "hru" in src.dimensions and "gru" in src.dimensions \
                    and src.dimensions["hru"].size != src.dimensions["gru"].size:
                raise RuntimeError(f"{src_file}: hru and gru sizes differ.")

            idx = pd.Index(src_gru).get_indexer(dst_gru)
            found = idx >= 0
            never_matched &= ~found
            print(f"\n{src_file.name}: matched {int(found.sum())} of {n} dst GRUs")

            for name, var in src.variables.items():
                if name in SKIP:
                    continue
                if len(var.dimensions) != 1 or var.dimensions[0] not in ("hru", "gru"):
                    print(f"  skip {name}: unexpected dimensions {var.dimensions}")
                    continue
                dim = var.dimensions[0]
                values = read_values(var)

                if name not in result:
                    if name in dst.variables:
                        if dst[name].dimensions != (dim,):
                            raise RuntimeError(
                                f"{name}: dst dims {dst[name].dimensions} != src dims {(dim,)}"
                            )
                        base = read_values(dst[name])
                        filled = np.zeros(n, dtype=bool)
                    else:
                        base = np.full(n, np.nan)
                        filled = np.zeros(n, dtype=bool)
                    attrs = {a: var.getncattr(a) for a in var.ncattrs() if a != "_FillValue"}
                    result[name] = [dim, attrs, base, filled]

                _, _, out, filled = result[name]
                overlap = int((filled & found).sum())
                if overlap:
                    print(f"  warning: {name}: {overlap} GRUs already filled by an earlier "
                          f"file; overwritten by {src_file.name}")
                out[found] = values[idx[found]]
                filled |= found

    # --------------------------------------------------------
    # write to dst
    # --------------------------------------------------------
    print()
    for name, (dim, attrs, out, filled) in result.items():
        if name in dst.variables:
            dst[name][:] = out
            action = "Overwrote"
        else:
            v = dst.createVariable(name, "f8", (dim,), fill_value=np.nan)
            for a, val in attrs.items():
                v.setncattr(a, val)
            v[:] = out
            action = "Created  "
        n_nan = int(np.isnan(out).sum())
        print(f"{action} {name}({dim})" + (f"  [{n_nan} NaN]" if n_nan else ""))

    if never_matched.any():
        print(f"\nWARNING: {int(never_matched.sum())} dst GRUs were not found in any src file "
              f"(first few gruIds: {dst_gru[never_matched][:10]})")

    dst.History = (
        str(getattr(dst, "History", ""))
        + f" | Parameters copied by gruId from {len(src_files)} file(s) under "
        + f"{calib_path} on {datetime.now():%Y/%m/%d %H:%M:%S}"
    )

print("\nDone.")
