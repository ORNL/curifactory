from dataclasses import dataclass, field
from typing import List

from curifactory import ExperimentArgs


@dataclass
class Args(ExperimentArgs):
    starting_data: List[int] = field(default_factory=lambda: [1, 2, 3, 4])
