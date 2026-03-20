# Releasing FinchVox to PyPI

Step-by-step guide for manually releasing FinchVox to PyPI.

## Prerequisites

- [ ] PyPI account with API token configured
- [ ] `uv` installed (or `pip`)
- [ ] Clean git working directory

## Release Workflow

### 1. Update Version

Edit `pyproject.toml`:

```toml
version = "0.0.2"  # Increment version
```

### 2. Update Changelog (Optional)

Add release notes to `CHANGELOG.md`.

### 3. Commit and Tag

```bash
# Commit changes
git add -A
git commit -m "Release v0.0.2"

# Create git tag
git tag v0.0.2

# Push commits and tags
git push && git push --tags
```

## Build Package

### 1. Clean Previous Builds

```bash
rm -rf dist/
```

### 2. Build

```bash
uv build
```

Expected output: Creates `dist/finchvox-0.0.2-py3-none-any.whl` and `dist/finchvox-0.0.2.tar.gz`

### 3. Verify Build

```bash
ls -lh dist/
```

## Upload to PyPI

```bash
UV_PUBLISH_TOKEN=$(grep UV_PUBLISH_TOKEN .env | cut -d= -f2) uv publish dist/*
```

Enter your PyPI API token when prompted.

### 3. Verify Upload

Visit: https://pypi.org/project/finchvox/

## Create GitHub Release

```bash
gh release create v0.0.2 --title "v0.0.2" --notes "Release notes here"
```

Visit: https://github.com/finchvox/finchvox/releases
