# Publishing Checklist

1. Run `pytest`
2. Update version in `curifactory/__init__.py`
3. Update changelog (`CHANGELOG.md`)
4. Generate documentation in `sphinx` directory with `make html` (if doc updates)
5. Apply documentation `scripts/apply-docs` (if doc updates)
6. Commit
7. Push to github
8. Publish to pypi `scripts/build`
9. Tag release on github
