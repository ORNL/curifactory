# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


## [unreleased]

### Added
* An `ImageReporter` for adding any generated and saved images into the output
  report




## [0.17.1] - 2023-12-07

### Added
* Link to the output log in generated reports.

### Changed
* `--print-params` output is now conditioned on `--verbose`: whether specifying
  a hash directly or the flag by itself, the `_DRY_REPS` will be included when
  `--verbose` is specified and removed when not.

### Fixed
* Excessive "no run info" warnings from caching when running an experiment
  notebook.
* `run_experiment` not correctly handling a `param_files` of `None`




## [0.17.0] - 2023-11-16

### Added
* Templating/keyword formating for cacher path overrides. This allows overriding
  cacher paths (at the expense of automatically not tracking them) to specify
  paths outside of the cache folder or directly including parameters in the
  filename etc.
* `PathRef` cacher, a special type of cacher that allows exclusively passing around
  paths and short-circuiting directly based on that path's existence (as opposed
  to the `FileReferenceCacher` which saves a file containing the path), rather
  than handling saving/loading itself.
* `--hashes` debugging flag, when specified it prints out the hash and name of
  each parameter set passed into an experiment and then exits.
* `--print-params` debugging flag, when specified it prints out the full string
  representation of each parameter set passed into an experiment, or, if at
  least the first few characters of a hash are specified, it prints out the
  corresponding parameter set hash from the `params_registry.json`. Note that
  both this and the `--hashes` flag are temporary debugging tools until the CLI
  gets broken out into subcommands, where they may become part of a separate
  command.

### Fixed
* `--notebook` manager's not using modified experiment cache paths.
* Manager maps are disabled after a `run_experiment` call, so managers used in
  live contexts (e.g. notebooks) may continue to run stages after the experiment
  has completed.
* Experiments generating multiple reports instead of just once and
  linking/copying the folders as necessary.

### Removed
* Old `ExperimentArgs` references and associated deprecation warnings.




## [0.16.1] - 2023-10-23

### Fixed
* Accidental singleton cacher objects in stage decorators causing all DAG-mode
  reproduction artifacts to always show as the artifacts from the first record.




## [0.16.0] - 2023-10-16

### Added
* Optional dependency `curifactory[h5]` (pytables, for h5 pandas cacher) to setup.
* Ability to configure whether non-curifactory logs are silenced with
  `--all-loggers` flag.

### Changed
* Repr for Lazy objects, so OutputSignatureErrors don't just list pointer addresses.
* Procedures initialized without an artifact manager don't auto-create one.
  Instead, the `procedure.run()` function now optionally takes a manager and
  records list.

### Fixed
* Lazy instance cached from previous run not displaying correct preview in detailed report map.
* Experiment run spewing out command error if running from non-git-repo. (Single line
  warning is now displayed instead.)
* Raising InputSignatureError for potentially unrelated TypeErrors raised within stages.
* Completer parsing for experiments and parameters on MacOS.
* `generate_report()` calls inside an experiment `run()` breaking in map mode.
* Fallback package report CSS not being used if report path has no style.css.




## [0.15.1] - 2023-08-09

### Added
* Hash dry representation output to params registry, to help debug hashing.

### Fixed
* Spacing issue around parameter set list in generated notebook.
* Extra metadata not grabbed in save_metadata if metadata had already been collected.




## [0.15.0] - 2023-08-01

### Added
* `PandasCacher` as a more generalized variant of `PandasCsvCacher` and
  `PandasJsonCacher`, supporting much more of the IO types pandas supports.

### Changed
* `args.ExperimentArgs` to `params.ExperimentParameters` (former still exists with deprecation warning.)
* `Record.args` to `Record.params` (former still exists with deprecation warning.)
* Organization in examples directory.

### Fixed
* None extension for cacher not correctly handled in get_path.
* Generated experiment notebook not reference correct cache path for artifacts on store full runs.
* `set_logging_prefix` incorrectly handling global logging scope (which can lead
  to recursion errors.)




## [0.14.2] - 2023-07-24

### Fixed
* DAG mapping incorrectly handling stages with missing inputs in state.




## [0.14.1] - 2023-07-21

### Fixed
* DAG never adding a stage with no outputs to the execution list.




## [0.14.0] - 2023-07-19

DAG-based execution of stages is finally here!

### Added
* DAG representation of experiment, this is created and analyzed during the experiment
  mapping phase. The DAG is used to more intelligently determine which stages need to
  execute, based on which outputs are ever actually needed for the final experiment
  outputs (leaf nodes).
* `--map` CLI flag, this runs the mapping phase of the experiment and then exits, printing
  out the experiment DAG and showing which artifacts it found in cache and the run name
  that generated them.
* `inputs` to aggregate stage decorator. This acts similarly to `inputs` on a regular
  stage, except these input artifacts are searched for in the list of records the aggregate
  is running across, rather than the aggregate's own record. It is also not a requirement
  that the requested artifact exist in every passed record (though it will throw a warning
  on any records where it doesn't exist.) Similar to `stage`, each input needs to have a
  corresponding argument (with the same name as in the string) in the function definition.
  The artifacts for each input will be passed as a dictionary, where the values are the
  artifacts, and the keys are the records they come from. Note that while you can technically
  have `None` as the inputs and still access each record's state, in order for the DAG
  to compute properly, you must specify each needed state artifact in the inputs. (or use the
  `--no-dag` flag listed below.)
* `stage_cachers` list to record, at the beginning of every stage this will contain
  references to the initialized cachers for that stage - this can be used to get
  output path information.
* `-n` CLI flag shorthand for `--names`
* `--params` CLI flag long form of `-p`
* `RawJupyterNotebookCacher`, which takes a list of cells of raw strings of python code and
  stores them as a notebook. This is useful for exporting an interactive analysis with each
  experiment run.

### Changed
* `--no-map` CLI flag to `--no-dag`, which disables both the mapping phase and the
  DAG analysis/DAG-based execution determination. This returns curifactory to its
  regular stage-by-stage cache short-circuit determination.
  NOTE: if any weird bugs are encountered, or if `inputs` isn't set on
  aggregate stages, it's advisable to use this flag.
* `--parallel-mode` flag to `--parallel-safe`

### Fixed
* Record copy not also containing a copy of the state artifact representations.
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
