# Development Guide


## Setup

### Install Pre-commit Hooks

```bash
uv run pre-commit install
```

This installs a git hook that runs ruff (linting and formatting) before each commit.

To run manually:

```bash
uv run scripts/fix-ruff.sh
```


## Testing

### Run Automated Tests

```bash
# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=finchvox.collector --cov-report=term-missing

# Run specific test file
pytest tests/test_writer.py -v
```

### Manual Testing with otel-cli

For testing without a Pipecat application:

#### Via `otel-cli`

```bash
# Install otel-cli (macOS)
brew install otel-cli

# Send a test span
otel-cli span --endpoint localhost:4317 --name "test-span" --service "test-service"

# Send multiple spans in same trace (they'll be grouped in one file)
otel-cli span --endpoint localhost:4317 --name "span-1" --service "test" --traceparent "00-12345678901234567890123456789012-1234567890123456-01"
otel-cli span --endpoint localhost:4317 --name "span-2" --service "test" --traceparent "00-12345678901234567890123456789012-1234567890123457-01"
```

#### Via test_send_spans.py

```bash
# Run the test script to send sample spans
python tests/test_send_spans.py
```


### Running Tests

```bash
# Watch mode (requires pytest-watch)
pip install pytest-watch
ptw tests/
```

### Tests failing

```bash
# Ensure dependencies are installed
uv pip install --system -e ".[dev]"

# Run tests with verbose output
pytest tests/ -v

# Check Python version (requires 3.11+)
python --version
```