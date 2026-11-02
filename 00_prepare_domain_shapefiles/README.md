# Fix the self-looped segments in river network shp files.

`1_prepare_river_network.py` is edited to set up features for self-looped segments. Specifically,


- `river_down_seg_id = 0` (as a natural outlet)
- `slope = 0.0001` 
- `length = sqrt(4*area/pi)`
- change the Point feature to Line by draw a line east-west in direction and 1 m in length
