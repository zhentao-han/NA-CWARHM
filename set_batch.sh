export SLURM_ACCOUNT=def-h294liu_cpu

export CWARHM="/home/zhentao/scratch/NAHM/NA-CWARHM"
export REPO_ROOT="${CWARHM}"    ##"/home/zhentao/projects/rrg-h294liu/zhentao/NA-CWARHM"
export DATA_ROOT="/home/zhentao/scratch/NAHM/NA_data"
export CONTROL_DIR="${REPO_ROOT}/0_control_files"

export INVENTORY="$CONTROL_DIR/MERIT_level2_control_file_inputs.csv" ## <DOMAIN_INVENTORY>.csv
export PREFIX="MERIT_"  ## <PREFIX> eg, MERIT_ and CAN_
export START_DOMAIN="MERIT_71"
export LIMIT=14        ## <NUMBER_OF_DOMAINS>
export BATCH_NAME="MERIT"

export BASIN_TASK="$CONTROL_DIR/multibasin_preprocessing_${BATCH_NAME}.txt"    ##"/home/zhentao/projects/rrg-h294liu/zhentao/NA-CWARHM/0_control_files/multibasin_preprocessing_CAN.txt"
export MONTH_TASK="$CONTROL_DIR/month_tasks_${BATCH_NAME}.txt"      ##"/home/zhentao/projects/rrg-h294liu/zhentao/NA-CWARHM/0_control_files/month_tasks_CAN.txt"
export NBASIN=$(wc -l < "$BASIN_TASK")
export NMONTH=$(wc -l < "$MONTH_TASK")

export CHUNK_SIZE=6
N=$(wc -l < $MONTH_TASK)
NJOBS=$(( (N + CHUNK_SIZE - 1) / CHUNK_SIZE ))


