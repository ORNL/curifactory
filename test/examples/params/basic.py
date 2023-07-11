from dataclasses import dataclass, field

from curifactory import ExperimentParameters


@dataclass
class Args(ExperimentParameters):
    starting_data: list[int] = field(default_factory=lambda: [1, 2, 3, 4])
