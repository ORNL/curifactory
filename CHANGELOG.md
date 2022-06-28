# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Paths returned from record's `get_path` and `get_dir` are now tracked and copied
  into a store full run.
- `PandasCSVCacher` and `PandasJSONCacher` argument dictionaries to pass into pandas
  to/read calls.

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
