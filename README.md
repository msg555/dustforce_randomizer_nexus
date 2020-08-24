## Repository layout

Utility scripts for filtering and computing level data for the Randomizer Nexus
are in the root of this repository as Python scripts.

The dustapi scripts that should be attached to the Randomizer Nexus is stored in
the scripts/ directory.

The actual Randomizer Nexus file is stored in bin/. This has some slight
modifications to the "Nexus DX" file in addition to having the randomizer nexus
script attached.

## Modifiying the randomizer nexus script

If you want to make modifications to the randomizer nexus script you'll likely
want to change the include at the beginning of "data.h" to
include "customs\_lite.h" as it is much faster to compile.

Make sure that if you save the nexus file you do so while in editor mode. If you
save while in play mode players will be unable to enter a new seed. If you
accidentally make this mistake you can correct it by returning to editor mode
and saving again.

## Using the utility scripts

```
# Optionally recompute leveldata.json from dataset/solvers.json source data
./playerrank.py > leveldata.json

# Output listing of door entity IDs to levels used in the LEVELS array in
# "randomizer/data.h"
./nexus_door_ids.py < bin/randomizer_nexus

# Output the CUSTOMS array structure used in "randomizer/customs.h" listing
# all the available levels and their metadata.
./format_level_data.py < leveldata.json

# Output the AUTHORS dictionary structure used in "randomizer/authors.h"
# mapping level IDs to author names.
./format_authors.py < dataset/authors.json
```
