#!/bin/bash
# Launch the GPU monitor using the project's own venv, regardless of where
# this script is invoked from. nohup output is kept in the project directory.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR" || exit 1
nohup "$DIR/.venv/bin/python" "$DIR/src/main.py"
