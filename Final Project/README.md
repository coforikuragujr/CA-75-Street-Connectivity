# Street Connectivity and Housing Outcomes in Chicago CA 75 (Morgan Park)

**Author:** Charles Ofori-Kuragu Jr.

This repository contains code, data pointers, and outputs for my CS 579 final project.  
It extends HW4 by building a drivable OSMnx network, computing connectivity metrics, joining to ACS 2019–2023 block-group outcomes, and producing maps, correlations, OLS, and robustness checks.

## Reproduce
```bash
pip install -r requirements.txt
python code/checkinputs.py
python code/buildnetwork.py
python code/computemetrics.py
python code/aggregatetobg.py
python code/analysismaps.py
python code/olsmodels.py
python code/robustcheck.py

Data

data/census/ca75_acs_blockgroups_updated.csv (ACS 2019–2023 5-year)
data/spatial/ca75_acs_bg_maps.gpkg (BG geometry for CA 75; layer ca75_bg_acs)

Outputs

Tables: outputs/tables/
Figures: outputs/figures/
