#!/bin/bash

#SBATCH --job-name=SUMMA_MPI
#SBATCH --ntasks=4
#SBATCH --cpus-per-task=1
#SBATCH --mem-per-cpu=1G
#SBATCH --time=2-00:00:00
#SBATCH --output=SUMMA_slurm_logs/SUMMA_%j.out
#SBATCH --error=SUMMA_slurm_logs/SUMMA_%j.err

# Usage (CONTROL_FILE must be set, SBATCH --output dir must exist before submit):
#   mkdir -p SUMMA_slurm_logs
#   CONTROL_FILE=control_xxx.txt sbatch run_summa_mpi.sh
#   (override rank count at submit time: sbatch --ntasks=8 run_summa_mpi.sh)

set -euo pipefail


# ============================================================
# PATHS
# ============================================================

CWARHM="${CWARHM:-/home/zhentao/projects/rrg-h294liu/zhentao/NA-CWARHM1}"
CONTROL_FILE="${CONTROL_FILE:?CONTROL_FILE was not supplied (use CONTROL_FILE=... sbatch ...)}"
CONTROL="${CWARHM}/0_control_files/${CONTROL_FILE}"

if [ ! -f "$CONTROL" ]; then
    echo "ERROR: control file not found: $CONTROL"
    exit 1
fi

mkdir -p ./SUMMA_slurm_logs


# ============================================================
# CONTROL READER
# ============================================================

read_control() {

    local key="$1"

    awk -F'|' -v key="$key" '

        /^[[:space:]]*#/ {
            next
        }

        NF >= 2 {

            left=$1
            gsub(/^[ \t]+|[ \t]+$/, "", left)

            if (left == key) {

                right=$2
                sub(/#.*/, "", right)
                gsub(/^[ \t]+|[ \t]+$/, "", right)

                print right
                exit
            }
        }

    ' "$CONTROL"
}


# ============================================================
# SETTINGS
# ============================================================

ROOT_PATH="$(read_control root_path)"
DOMAIN_NAME="$(read_control domain_name)"
EXPERIMENT_ID="$(read_control experiment_id)"

SUMMA_PATH="$(read_control install_path_summa)"
SUMMA_EXE="$(read_control exe_name_summa)"

SETTINGS_PATH="$(read_control settings_summa_path)"
FILEMANAGER="$(read_control settings_summa_filemanager)"

MIZU_SETTINGS_PATH="$(read_control settings_mizu_path)"
MIZU_CONTROL_NAME="$(read_control settings_mizu_control_file)"

OUTPUT_PATH="$(read_control experiment_output_summa)"
LOG_PATH="$(read_control experiment_log_summa)"

DO_BACKUP="$(read_control experiment_backup_settings)"


# ============================================================
# DEFAULT PATHS
# ============================================================

if [ "$SUMMA_PATH" = "default" ]; then
    SUMMA_PATH="${ROOT_PATH}/installs/summa"
fi

if [ "$SETTINGS_PATH" = "default" ]; then
    SETTINGS_PATH="${ROOT_PATH}/domain_${DOMAIN_NAME}/settings/SUMMA"
fi

if [ "$MIZU_SETTINGS_PATH" = "default" ]; then
    MIZU_SETTINGS_PATH="${ROOT_PATH}/domain_${DOMAIN_NAME}/settings/mizuRoute"
fi

if [ "$OUTPUT_PATH" = "default" ]; then
    OUTPUT_PATH="${ROOT_PATH}/domain_${DOMAIN_NAME}/simulations/${EXPERIMENT_ID}/SUMMA"
fi

if [ "$LOG_PATH" = "default" ]; then
    LOG_PATH="${OUTPUT_PATH}/SUMMA_logs"
fi


SUMMA_EXEC="${SUMMA_PATH}/bin/${SUMMA_EXE}"
FILEMANAGER_PATH="${SETTINGS_PATH}/${FILEMANAGER}"
CONTROL_TOML="${MIZU_SETTINGS_PATH}/${MIZU_CONTROL_NAME}"

NTASKS="${SLURM_NTASKS:-1}"
LOG_FILE="${LOG_PATH}/summa_mpi_np${NTASKS}_${SLURM_JOB_ID:-local}.txt"

# SUMMA's messages end up in the Slurm output file (not LOG_FILE), so the
# success check reads from there.
SLURM_OUT="${SLURM_SUBMIT_DIR:-.}/SUMMA_slurm_logs/SUMMA_${SLURM_JOB_ID:-local}.out"


# ============================================================
# ENVIRONMENT (must match the modules SUMMA was built with)
# ============================================================

# module purge
# module load StdEnv/2023 gcc openmpi netcdf-fortran   # <-- adjust to your build

export OMP_NUM_THREADS=1


# ============================================================
# REQUIRED FILE CHECKS
# ============================================================

if [ ! -x "$SUMMA_EXEC" ]; then
    echo
    echo "ERROR: SUMMA executable not found:"
    echo "$SUMMA_EXEC"
    exit 1
fi

if [ ! -f "$FILEMANAGER_PATH" ]; then
    echo
    echo "ERROR: SUMMA fileManager not found:"
    echo "$FILEMANAGER_PATH"
    exit 1
fi

if [ ! -f "$CONTROL_TOML" ]; then
    echo
    echo "ERROR: SUMMA control TOML not found:"
    echo "$CONTROL_TOML"
    exit 1
fi


# ============================================================
# OUTPUT DIRECTORIES
# ============================================================

mkdir -p "$OUTPUT_PATH"
mkdir -p "$LOG_PATH"

# rm -rf "${OUTPUT_PATH}/*"
# ============================================================
# SETTINGS BACKUP
# ============================================================

if [ "$DO_BACKUP" = "yes" ]; then

    BACKUP_PATH="${OUTPUT_PATH}/run_settings"

    mkdir -p "$BACKUP_PATH"

    cp -Rf \
        "${SETTINGS_PATH}/." \
        "$BACKUP_PATH/"

fi


# ============================================================
# REPORT
# ============================================================

echo "============================================================"
echo "RUN SUMMA (MPI)"
echo "============================================================"

echo "Domain       : $DOMAIN_NAME"
echo "Experiment   : $EXPERIMENT_ID"
echo "Job ID       : ${SLURM_JOB_ID:-none}"
echo "MPI ranks    : $NTASKS"
echo "Nodes        : ${SLURM_JOB_NODELIST:-none}"
echo "Executable   : $SUMMA_EXEC"
echo "FileManager  : $FILEMANAGER_PATH"
echo "Control TOML : $CONTROL_TOML"
echo "Output       : $OUTPUT_PATH"
echo "Log          : $SLURM_OUT"
echo "Start        : $(date)"

echo "============================================================"


# ============================================================
# RUN SUMMA
# ============================================================

set +e

srun "$SUMMA_EXEC" \
    -m "$FILEMANAGER_PATH" \
#    -c "$CONTROL_TOML" \
    > "$LOG_FILE" 2>&1

# mpirun alternative (use instead of srun if srun fails to launch):
# mpirun -np "$NTASKS" "$SUMMA_EXEC" \
#     -m "$FILEMANAGER_PATH" \
#     -c "$CONTROL_TOML" \
#     > "$LOG_FILE" 2>&1

STATUS=$?

set -e


# ============================================================
# VERIFY SUMMA SUCCESS
# ============================================================

MODEL_SUCCESS="no"

if grep -qi \
    "finished simulation successfully" \
    "$SLURM_OUT"
then
    MODEL_SUCCESS="yes"
fi


if [ "$STATUS" -ne 0 ] \
    || [ "$MODEL_SUCCESS" != "yes" ]; then

    echo
    echo "============================================================"
    echo "SUMMA MPI RUN FAILED"
    echo "============================================================"

    echo "Return code : $STATUS"
    echo "Model success message found: $MODEL_SUCCESS"

    echo
    echo "Last 40 lines of SUMMA log:"
    echo "------------------------------------------------------------"

    tail -40 "$SLURM_OUT" || true

    exit 1
fi


# ============================================================
# SUCCESS
# ============================================================

echo
echo "============================================================"
echo "SUMMA MPI RUN COMPLETED SUCCESSFULLY"
echo "============================================================"

echo "MPI ranks : $NTASKS"
echo "End       : $(date)"

echo "============================================================"
