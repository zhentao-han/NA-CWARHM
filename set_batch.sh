export REPO_ROOT="/home/zhentao/projects/rrg-h294liu/zhentao/NA-CWARHM"
export DATA_ROOT="/home/zhentao/projects/rrg-h294liu/zhentao/NA-CWARHM/Data"
export CONTROL_DIR="${REPO_ROOT}/0_control_files"

export BASIN_TASK="/home/zhentao/projects/rrg-h294liu/zhentao/NA-CWARHM/0_control_files/multibasin_preprocessing_CAN.txt"
export MONTH_TASK="/home/zhentao/projects/rrg-h294liu/zhentao/NA-CWARHM/0_control_files/month_tasks_CAN.txt"
export NBASIN=$(wc -l < "$BASIN_TASK")
export NMONTH=$(wc -l < "$MONTH_TASK")
