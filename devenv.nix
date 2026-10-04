# @autorun
{ pkgs, config, ... }:
let
  # Sample library and app data. Never point this at a real library
  devDir = "${config.devenv.root}/.dev";

  # Used by bumpVersion and bumpPluginVersion
  bump = { name, file, prefix, next, check ? "" }: ''
    new="$1"
    if [ -z "$new" ] || [[ "$new" == *\"* ]]; then
      echo "Usage: ${name} 1.2.3" >&2
      exit 1
    fi
    ${check}
    file="$DEVENV_ROOT/${file}"
    old=$(sed -nE 's/^${prefix}"([^"]+)"$/\1/p' "$file")
    if [ -z "$old" ]; then
      echo "No version found in $file" >&2
      exit 1
    fi
    escaped=$(printf '%s' "$new" | sed 's/[\/&\\]/\\&/g')
    sed -i -E "s/^(${prefix})\"[^\"]+\"$/\1\"$escaped\"/" "$file"
    echo "Current version: $old"
    echo "New version:     $new"
    echo "${next}"
  '';
in
{
  dotenv.disableHint = true;

  languages.python = {
    enable = true;
    package = pkgs.python313;
    venv = {
      enable = true;
      requirements = "-e ${config.devenv.root}[test]";
    };
  };

  packages = [
    # For tests/lua/harness.lua, LuaJIT as KOReader uses it
    (pkgs.luajit.withPackages (ps: [ ps.luasocket ps.dkjson ]))
  ];

  env = {
    CALIBRE_TYPO_LIBRARY = "${devDir}/library";
    CALIBRE_TYPO_DATA = "${devDir}/data";
  };

  scripts = {
    run.exec = ''
      [ -f "$CALIBRE_TYPO_LIBRARY/metadata.db" ] || sample-library
      calibre-typo serve
    '';
    # Reachable from LAN. Opens the port in NixOS firewall
    runOnLan.exec = ''
      port="''${CALIBRE_TYPO_PORT:-8090}"
      ip=$(ip -4 route get 1.1.1.1 | sed -nE 's/.* src ([0-9.]+).*/\1/p')
      if [ -z "$ip" ]; then
        echo "Couldn't find this machine's LAN address" >&2
        exit 1
      fi
      rule=(nixos-fw -p tcp --dport "$port" -j nixos-fw-accept)
      sudo iptables -I "''${rule[@]}" || exit 1
      sudo ip6tables -I "''${rule[@]}" 2>/dev/null
      close() {
        sudo iptables -D "''${rule[@]}"
        sudo ip6tables -D "''${rule[@]}" 2>/dev/null
        echo "Closed port $port"
      }
      trap close EXIT
      trap 'exit 130' INT TERM
      echo "Opened port $port, open http://$ip:$port on your devices"
      [ -f "$CALIBRE_TYPO_LIBRARY/metadata.db" ] || sample-library
      CALIBRE_TYPO_HOST=0.0.0.0 CALIBRE_TYPO_PUBLIC_URL="http://$ip:$port" calibre-typo serve
    '';
    tests.exec = ''pytest "$@"'';
    sample-library.exec = ''python "$DEVENV_ROOT/tests/sample_library.py" "$CALIBRE_TYPO_LIBRARY"'';
    reset-dev.exec = ''rm -rf "${devDir}" && echo "Removed ${devDir}"'';
    reset-password.exec = ''calibre-typo reset-password'';
    bumpVersion.exec = bump {
      name = "bumpVersion";
      file = "src/calibre_typo/__init__.py";
      prefix = "__version__ = ";
      next = "Now commit it and create a release on GitHub";
      # Validate against python packaging formats
      check = ''
        python -c 'import sys; from packaging.version import Version; Version(sys.argv[1])' "$new" 2>/dev/null || {
          echo "\"$new\" isn't a valid Python package version (e.g. 1.2.3, 1.2.3rc1)" >&2
          exit 1
        }
      '';
    };
    bumpPluginVersion.exec = bump {
      name = "bumpPluginVersion";
      file = "koreader/calibretypo.koplugin/calibretypo/version.lua";
      prefix = "return ";
      next = "The plugin ships with the server, so also run bumpVersion, then create a release on GitHub";
    };
  };

  processes.server.exec = "run";

  enterTest = "pytest";

  enterShell = ''
    echo "calibre-typo dev shell"
    echo "  run             start the server on http://127.0.0.1:8090 (sample library in .dev/)"
    echo "  runOnLan        same, reachable from your LAN (opens the port with sudo until stopped)"
    echo "  tests           run the test suite, including the KOReader plugin harness"
    echo "  reset-dev       delete the sample library and app data"
    echo "  bumpVersion 1.2.3        set the server version"
    echo "  bumpPluginVersion 1.2.3  set the KOReader plugin version"
  '';
}
