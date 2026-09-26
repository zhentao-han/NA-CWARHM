export SLURM_ACCOUNT=<SLURM_ACCOUNT>

export CWARHM="/home/zhentao/projects/rrg-h294liu/zhentao/NA-CWARHM"
export REPO_ROOT="${CWARHM}"    ##"/home/zhentao/projects/rrg-h294liu/zhentao/NA-CWARHM"
export DATA_ROOT="/home/zhentao/projects/rrg-h294liu/zhentao/NA-CWARHM/Data"
export CONTROL_DIR="${REPO_ROOT}/0_control_files"

export INVENTORY="$CONTROL_DIR/CAN_control_file_inputs.csv" ## <DOMAIN_INVENTORY>.csv
export PREFIX="CAN_"  ## <PREFIX> eg, MERIT_ and CAN_
export START_DOMAIN="CAN_01AD003"
export LIMIT=2        ## <NUMBER_OF_DOMAINS>
export BATCH_NAME="CAN"

export BASIN_TASK="$CONTROL_DIR/multibasin_preprocessing_${BATCH_NAME}.txt"    ##"/home/zhentao/projects/rrg-h294liu/zhentao/NA-CWARHM/0_control_files/multibasin_preprocessing_CAN.txt"
export MONTH_TASK="$CONTROL_DIR/month_tasks_${BATCH_NAME}.txt"      ##"/home/zhentao/projects/rrg-h294liu/zhentao/NA-CWARHM/0_control_files/month_tasks_CAN.txt"
export NBASIN=$(wc -l < "$BASIN_TASK")
export NMONTH=$(wc -l < "$MONTH_TASK")
