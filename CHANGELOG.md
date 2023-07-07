# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [unreleased]

### Added
* `stage_cachers` list to record, at the beginning of every stage this will contain
  references to the initialized cachers for that stage - this can be used to get
  output path information.

### Fixed
* Wrong progress bar updating if multiple records/args had the same hash




## [0.13.2] - 2023-05-05

### Fixed
* Docker module incorrectly using the `run_command` function.
* Experiment passing in a cutoff run folder to the docker command.




## [0.13.1] - 2023-04-26

### Fixed
* Reportables that implement render using the old `name` instead of `qualified_name`, causing
  unintended figure image overwrites.




## [0.13.0] - 2023-04-21

### Added
* Check for `get_params()` functions that aren't returning lists.

### Changed
* An aggregate stage that is not explicitly given a set of records now takes manager records minus
  the record containing the currently running aggregate stage.

### Fixed
* Record `make_copy` adding the new record to the artifact manager twice.
* Reportables ToC in report not correctly using the qualified names when cached reportables found.
* `LinePlotReporter` not adding a legend when dictionaries provided for both `x` and `y`.
* Potential error when collecting metadata if manager run info doesn't have "status".




## [0.12.0] - 2023-03-30

### Added
- Bash/zsh tab-completion via `argcomplete`. (This requires installing `argcomplete` outside of the
  environment and adding a line to your shell's rc file in order to use. You can run
  `curifactory completion [--bash|--zsh]` to add the line, or just run `curifactory completion` for
  instructions.)
- `resolve` option to `Lazy` outputs - this allows not automatically loading the object on an input
  to the stage, directly providing the lazy instance instead. This allows delaying the loading, or
  simply getting the path of the object to deal with in some other way (e.g. passing to an external
  command.)

### Fixed
- `experiment ls` incorrectly handling curifactory configurations with experiment/param modules located
  in subdirectories.




## [0.11.1] - 2023-03-29

### Fixed
- `--names` flag incorrectly checking existence of parameterset name.




## [0.11.0] - 2023-03-29

### Added
- Curifactory submodules to top level import, so separately importing submodules is no longer necessary.

### Changed
- Minimum python version to 3.9.
- Parameterset `name` to be ignored by hashing mechanism.

### Fixed
- No longer using backported package `importlib_resources` that wasn't in the setup.




## [0.10.1] - 2023-03-28

### Fixed
- Hash computation not correctly handling sub-dataclasses recursively.




## [0.10.0] - 2023-03-28

### Added
- Metadata output for every cached artifact. Alongside every output cache file will be a `[file]_metadata.json`,
  containing information about the run that generated it, the parameters, and previous stages run in the same record.
- `track` parameter to cachers, indicating whether the output files should be copied into a full store run folder or not.
  (It is true by default.)
- Optional cacher prefixes, which replaces the first part of a cached filepath name (normally the experiment name) with the provided
  prefix. This allows cross-experiment caching (use with care!)
- Optional cacher subdir, which places output files into the specified subdirectory in the cache/run folder (allows better organization,
  e.g. Kedro's data engineering convention of 01_raw, 02_intermediate, etc.)
- Allowing exact path overrides to be used by a cacher, making it cleaner to use them on the fly/outside of stages.
- `--version` flag on the `curifactory` command.

### Changed
- Full store cached files are now placed into an `artifacts/` subdirectory of the run folder.
- `PickleCacher`'s extension is now correctly set to `.pkl` (we aren't actually running gzip on it.)
- Full store runs no longer call a cacher's `save` function a second time with a new path, instead relying
  on `Record`'s path tracking to simply copy the cached files into the full store folder at the end of a stage.
- Cachers' path mechanism - rather than expecting a cacher's `set_path` to be called beforehand, `save` and `load`
  should call the cacher's `get_path()`.
- The default cachers' `save()` functions return the path that was saved to.
- `--name` flag to `--prefix` to make it more consistent to caching terminology.

### Fixed
- Reportable names doubling when loading from cache.
- Silent execution when no parametersets provided or a requested parameterset name wasn't found, (now errors and exits.)




## [0.9.3] - 2023-03-21

### Fixed
- Lack of proper html escaping of args dump in output reports.




## [0.9.2] - 2023-03-20

### Fixed
- String hash representation not recursively getting a string hash
  representation from any parameter sub-dataclasses.




## [0.9.1] - 2023-03-15

### Changed
- String representation of hashed arguments will include the actual value of
  the parameters in `IGNORED_PARAMS` for reporting purposes.

### Fixed
- Distributed run detection not checking `RANK` env variable.




## [0.9.0] - 2023-03-10

### Added
- Git init prompt on `curifactory init`, if run in a folder that doesn't contain a `.git`

### Changed
- Argument hashing to allow user to specify `hash_representations` on their
  parameter dataclasses. This allows them to (optionally) provide a function
  for each individual parameter that will return a custom value to be hashed
  rather than simply the default string representation. This also allows
  completely ignoring parameters as part of their hash, by setting their hashing
  function to `None`.
- Arguments whose value is `None` are not included as part of the hash.

### Fixed
- Store full distributed run creating a full store folder for every distributed process.
  Store entire run now auto disabled on all non-rank-zero distributed processes
- `curifactory init` not extracting `debug.py`




## [0.8.2] - 2022-12-14

### Fixed
- Arg hashes and combo hashes attempting to write to parameters registry while in `--parallel-mode`.

### Removed
- Old dataclasses dependency. (Only used pre 3.6.)




## [0.8.1] - 2022-09-13

### Added
- Ability to revert to plain log output (instead of rich logging handler) with
  `--plain`.

### Changed
- Rich progress bars are no longer used by default. They can be enabled with
  the `--progress` CLI flag.

### Fixed
- Bug where the end of an experiment attempts to stop a rich progress bar even
  if one had not been started.




## [0.8.0] - 2022-09-12

### Added
- Command flag to regenerate the report index, useful for when importing run
  from another machine. (run via `experiment reports --update`.)
- Add experiment mapping step before execution - steps through experiment code
  without executing stage bodies and records a list of all records and stages
  they call.
- Warn if calling a stage from within another stage - this breaks experiment mapping.
- Rich library dependency, terminal logging is now fancy with colors and
  progress bars!
- Logging notification if distributed run detected.
- Display control flags: `--no-color`, `--quiet`.

### Changed
- Improved CLI help messages.




## [0.7.0] - 2022-07-08

### Added
- Paths returned from record's `get_path` and `get_dir` are now tracked and copied
  into a store full run.
- `PandasCSVCacher` and `PandasJSONCacher` argument dictionaries to pass into pandas
  to/read calls.
- Dirty git worktree warning in output log and indicator to output reports.

### Changed
- Args hashes are now set from within the record constructor to avoid edge cases
  where hashes changed and broke aggregate hashing.
- Aggregate combo hashes are set on the record directly now, done to track a
  combo hash throughout a record's lifespan that started with an aggregate,
  without breaking the aggregate record's potential args hash as well.

### Fixed
- `PandasCSVCacher` `read_csv` not appropriately handling index column by default.



## [0.6.3] - 2022-03-07

### Added
- Project `curifactory` command tests.

### Changed
- Project init .gitignore handling to check for/add a blank line before adding
  the curfiactory section.

### Fixed
- Notebook experiment folder not being created on init and from experiment.
- Notebook path config value not being used on notebook write.




## [0.6.2] - 2022-02-22

### Added
- Newsgroups example experiment code (see `examples/minimal/experiments/newsgroups.py`.)

### Changed
- Parallel mode will automatically be set in a distributed pytorch scenario for
  all processes that aren't local/node rank 0.

### Fixed
- Parallel mode causing crash if global args indices are not specified.




## [0.6.1] - 2022-02-14

### Changed
- Minimum python version to 3.8.

### Fixed
- Parallel runs with reportable caching crashing due to attempts to pickle
  references containing `multiprocessing.Lock` instances.




## [0.6.0] - 2022-02-10

### Added
- `FileReferenceCacher` for storing lists of referenced file paths without keeping
  file contents in memory.
- Automatic reportable caching. Reportables of Stages that short-circuit will now
  reload and display in the report.
- Misc example project folder for experiments demonstrating various curifactory
  features.

### Changed
- Improve getting started documentation.
- Cacheables are now given a copy of the current record by the stages. This can
  be used to access the current argset and even directly get record state within
  the save/load implementation.

### Fixed
- Missing files in git for example projects.




## [0.5.1] - 2022-02-08

### Changed
- Auto-redirect for docs index.

### Fixed
- `.dockerignore` not correctly included in package data.
- Setup documentation URL.




## [0.5.0] - 2022-02-08

First open source release!

### Added
- `__version__` attribute to package init.
- `curifactory init` runnable to create default project structure and files.
- `get_path` and `get_dir` functions directly on `Record` instances for use in
  stage code. Note that these functions currently DO NOT keep track of usage, so
  whatever is stored at these paths doesn't get copied via store-full yet.
- Example/tutorial notebook number 0, introducing the four primary underlying
  components of curifactory.
- Example/tutorial notebook number 1, introducing caching, lazy objects, and
  reporting.
- BSD 3-clause license.

### Changed
- Significant documentation updates.
- Cleaner minimal example experiment.

### Fixed
- Using the (non-windows) `resource` module without an OS check in the `aggregate`
  decorator.
- Args dump in reports not making any string conversions html-safe (replacing
  `<` and `>` with their `&xx;` equivalents.)
- `--notes` flag not working without an inline message.
