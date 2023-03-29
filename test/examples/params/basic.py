from dataclasses import dataclass, field

from curifactory import ExperimentArgs


@dataclass
class Args(ExperimentArgs):
    starting_data: list[int] = field(default_factory=lambda: [1, 2, 3, 4])
