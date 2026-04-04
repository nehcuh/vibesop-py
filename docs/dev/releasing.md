# Release Process

## Versioning

VibeSOP uses semantic versioning (SemVer): `MAJOR.MINOR.PATCH`

Versions are automatically managed by `hatch-vcs` from git tags.

## Creating a Release

### 1. Ensure all tests pass

```bash
make check
```

### 2. Update CHANGELOG.md

Add a new section for the release following [Keep a Changelog](https://keepachangelog.com/).

### 3. Create and push tag

```bash
git tag v2.2.0
git push origin v2.2.0
```

### 4. GitHub Actions will automatically:
- Run CI checks
- Build the package
- Publish to PyPI
- Create a GitHub Release with release notes

## Release Checklist

- [ ] All tests passing
- [ ] Coverage above 80%
- [ ] CHANGELOG.md updated
- [ ] Version tag created
- [ ] PyPI package published
- [ ] GitHub Release created
- [ ] Documentation updated
