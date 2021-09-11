### Install dependencies

```
python -m pip install -r requirements.txt
```

### Download datasets

The randomizer makes use of a locally stored dataset. You can manage
this dataset using the dfrandomizer.dataset module. The first time you
run this will take awhile so grab a coffee, the downloaded data will
be stored in the dataset/ folder. The script has been written in a way
that interrupting it _should_ not lose much progress.

```
# Can rerun including '--update-levels' to incorporate new levels into dataset
python -m dfrandomizer.dataset --update-levels -v
```

### Generate a randomized nexus file

You can generate a nexus from the command like using the
`dfrandomizer.randomizer` module. Use `--help` to see a full listing of options.
The below command will generate a randomized nexus at the path "my-nexus" based
off the template nexus at "bin/randomizer\_nexus"

```
python -m dfrandomizer.randomizer --min-difficulty 0.5 bin/randomizer_nexus my-nexus
```

### Run web server

The randomizer nexus also comes with a minimal flask web server to generate
nexuses from a web interface. It is the intention that this service will
be hosted and available at https://dustkid.com/randomizer.

```
python -m dfrandomizer.web bin/randomizer_nexus
```

### Add a new nexus template

Copy the nexus file you want to be a template into into the nexus\_templates
directory and preprocess with a command like:

```
python -m dfrandomizer.nexus_templates nexus_templates/mynewnexus
```

Any doors that lead to a known playable level will be randomized,
all other doors will be converted into back nexus doors. The key get type for
each level will always be the next higher key type than the one used to access
that level, with the highest lock type yielding red keys.
