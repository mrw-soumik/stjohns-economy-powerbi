# Source this file (do not execute it): . /path/to/tmdl-validator/env.sh
# Keeps the local .NET SDK and all NuGet/CLI state inside the tmdl-validator folder.
TMDLV_HOME="$(cd "$(dirname "${BASH_SOURCE[0]:-${(%):-%x}}")" && pwd)"
export TMDLV_HOME
export DOTNET_ROOT="$TMDLV_HOME/dotnet"
export PATH="$DOTNET_ROOT:$PATH"
export DOTNET_CLI_HOME="$TMDLV_HOME/.dotnet-cli-home"
export NUGET_PACKAGES="$TMDLV_HOME/.nuget/packages"
export NUGET_HTTP_CACHE_PATH="$TMDLV_HOME/.nuget/http-cache"
export NUGET_PLUGINS_CACHE_PATH="$TMDLV_HOME/.nuget/plugins-cache"
export NUGET_SCRATCH="$TMDLV_HOME/.nuget/scratch"
# NuGet on macOS/Linux otherwise writes ~/.local/share/NuGet (migrations marker, http cache)
export XDG_DATA_HOME="$TMDLV_HOME/.xdg/data"
export XDG_CONFIG_HOME="$TMDLV_HOME/.xdg/config"
export XDG_CACHE_HOME="$TMDLV_HOME/.xdg/cache"
export DOTNET_CLI_TELEMETRY_OPTOUT=1
export DOTNET_NOLOGO=1
export DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1
export DOTNET_GENERATE_ASPNET_CERTIFICATE=false
export DOTNET_ADD_GLOBAL_TOOLS_TO_PATH=false
export DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE=1
export MSBUILDDISABLENODEREUSE=1
export DOTNET_CLI_USE_MSBUILD_SERVER=0
mkdir -p "$DOTNET_CLI_HOME" "$NUGET_PACKAGES" "$NUGET_HTTP_CACHE_PATH" "$NUGET_PLUGINS_CACHE_PATH" "$NUGET_SCRATCH" \
  "$XDG_DATA_HOME" "$XDG_CONFIG_HOME" "$XDG_CACHE_HOME"
