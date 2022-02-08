# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.1] - 2022-02-08

### Fixed
* `.dockerignore` not correctly included in package data.
* Setup documentation URL.

### Changed
* Auto-redirect for docs index.

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
