#!/bin/bash

#SBATCH --job-name=SUMMA_merge
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=04:00:00
#SBATCH --output=SUMMA_merge_logs/SUMMA_merge_%j.out
#SBATCH --error=SUMMA_merge_logs/SUMMA_merge_%j.err

set -euo pipefail

mkdir -p ./SUMMA_merge_logs
# ============================================================
# PATHS
# ============================================================

#SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

#MERGE_SCRIPT="${SCRIPT_DIR}/2_merge_summa_array_outputs.py"

CWARHM="${CWARHM:-/home/zhentao/projects/rrg-h294liu/zhentao/NA-CWARHM1}"

MERGE_SCRIPT="${CWARHM}/6_model_runs/2_merge_summa_array_outputs.py"

CONTROL_FILE="${CWARHM}/0_control_files/${CONTROL_FILE}"

if [ ! -f "$CONTROL_FILE" ]; then
    echo
    echo "ERROR: Control file not found:"
    echo "$CONTROL_FILE"
    exit 1
fi

export CONTROL_FILE

echo "Control file: $CONTROL_FILE"

# ============================================================
# ENVIRONMENT
# ============================================================

#module load conda/base

#conda activate nwam_parallel


#if [ "${CONDA_DEFAULT_ENV:-}" != "nwam_parallel" ]; then

#    echo
#    echo "ERROR: Failed to activate nwam_parallel."
#    echo "Active environment: ${CONDA_DEFAULT_ENV:-none}"

#    exit 1
#fi


#PYTHON_EXE="${CONDA_PREFIX}/bin/python"

#if [ ! -x "$PYTHON_EXE" ]; then

#    echo
#    echo "ERROR: Python executable not found:"
#    echo "$PYTHON_EXE"
#
#    exit 1
#fi


if [ ! -f "$MERGE_SCRIPT" ]; then

    echo
    echo "ERROR: SUMMA merge script not found:"
    echo "$MERGE_SCRIPT"

    exit 1
fi


# ============================================================
# REPORT
# ============================================================

echo
echo "============================================================"
echo "MERGE SUMMA ARRAY OUTPUTS"
echo "============================================================"

#echo "Environment : $CONDA_DEFAULT_ENV"
#echo "Python      : $PYTHON_EXE"
echo "Script      : $MERGE_SCRIPT"
echo "Start       : $(date)"

echo "============================================================"
echo


# ============================================================
# RUN MERGE
# ============================================================

set +e

#"$PYTHON_EXE" \
python \
    "$MERGE_SCRIPT"

STATUS=$?

set -e


# ============================================================
# RESULT
# ============================================================

echo

if [ "$STATUS" -eq 0 ]; then

    echo "============================================================"
    echo "SUMMA MERGE COMPLETED SUCCESSFULLY"
    echo "============================================================"

    echo "End: $(date)"

else

    echo "============================================================"
    echo "SUMMA MERGE FAILED"
    echo "============================================================"

    echo "Return code: $STATUS"
    echo "End        : $(date)"

fi

echo "============================================================"

exit "$STATUS"
