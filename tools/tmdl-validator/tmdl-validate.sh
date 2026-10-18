#!/usr/bin/env bash
# Validate a Power BI / Analysis Services TMDL folder with Microsoft's own TOM TmdlSerializer.
# Usage: tmdl-validate.sh <definition folder | *.SemanticModel folder> [--json] [--roundtrip <dir>] [--strict] ...
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
. "$HERE/env.sh"
exec "$DOTNET_ROOT/dotnet" "$HERE/bin/TmdlValidator.dll" "$@"
