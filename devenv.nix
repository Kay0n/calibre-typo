# @autorun
{ pkgs, config, ... }:
let
  # Sample library and app data. Never point this at a real library
  devDir = "${config.devenv.root}/.dev";
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
    tests.exec = ''pytest "$@"'';
    sample-library.exec = ''python "$DEVENV_ROOT/tests/sample_library.py" "$CALIBRE_TYPO_LIBRARY"'';
    reset-dev.exec = ''rm -rf "${devDir}" && echo "Removed ${devDir}"'';
    reset-password.exec = ''calibre-typo reset-password'';
  };

  processes.server.exec = "run";

  enterTest = "pytest";

  enterShell = ''
    echo "calibre-typo dev shell"
    echo "  run             start the server on http://127.0.0.1:8090 (sample library in .dev/)"
    echo "  tests           run the test suite, including the KOReader plugin harness"
    echo "  reset-dev       delete the sample library and app data"
  '';
}
