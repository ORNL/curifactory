# Publishing Checklist

1. Run `pytest`
2. Update version in `curifactory/__init__.py`
3. Update changelog (`CHANGELOG.md`)
4. Generate documentation in `sphinx` directory with `make html` (if doc updates)
5. Apply documentation `make apply-docs` (if doc updates)
6. Update `docs/index.html` links
7. Commit
8. Push to github
9. Publish to pypi `make publish`
10. Tag release on github
