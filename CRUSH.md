# CRUSH.md

## Commands
- **Lint**: `ruff check .`
- **Format**: `ruff format .`
- **Docker**: `run_using_docker.sh`
- **Deploy**: `run_using_fly.sh`  
- **Test**: `python -m pytest tests/ -v` (single test: `python -m pytest tests/test_file.py::test_name -v`)
- **Type check**: `python -m mypy .`
- **Pre-commit**: `pre-commit run --all-files`

## Style
- **Imports**: Sort with ruff (I rules), stdlib first, then 3rd party, then local
- **Naming**: snake_case for vars/functions, PascalCase for classes, UPPER for constants
- **Types**: Type hints required, use Python 3.13+ features
- **Quotes**: Double quotes only
- **Indent**: 4 spaces
- **Line length**: 120 chars
- **Error handling**: Specific exceptions, avoid bare except: