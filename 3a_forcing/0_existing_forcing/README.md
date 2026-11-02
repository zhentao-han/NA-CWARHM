`3a_forcing/0_existing_forcing/3_prepare_era5_forcing.py`: Change the source path of "airpres", "LWRadAtm",  "SWRadAtm", "spechum", "windspd" to MSWX corresponding paths.


`3a_forcing/0_existing_forcing/1_prepare_emearth_forcing.py`: Change the source path of “pptrate” and “airtemp” to MSWEP and MSWX/Temp, respectively. 

EM-Earth data for North America is hard-coded here.

Forcing data preparation start and end time: Originally processes all months between the start year and the end year. But there is a time gap on 1979031 for LWd and SWd. Edit all relevant scripts to accept an optional month on either end.

Switch to ERA5 and EM-Earth: change the `1_prepare_emearth_forcing_bk_emearch.py` to `1_prepare_emearth_forcing.py`, and change the `3_prepare_era5_forcing_bk_era5.py` to `3_prepare_era5_forcing.py`

