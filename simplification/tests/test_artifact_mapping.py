"""
Every experiment has an ArtifactManager
Every stage has an ArtifactManager
Flatten where possible
"""

"""Every artifact involved in the compute chain of each experiment output
(artifact) should exist in that experiment's ArtifactManager."""


"""An Artifact can only belong to one ArtifactManager? Artifacts referenced
through a different ArtifactManager must be a copy"""


"""Artifacts are only the same instance throughout a single outermost
experiment. Any time they are referenced from a new experiment context,
they must create a copy first."""
