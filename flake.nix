{
  inputs = {
    systems.url = "github:nix-systems/x86_64-linux";
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-parts.url = "github:hercules-ci/flake-parts";
    process-compose-flake.url = "github:Platonic-Systems/process-compose-flake";
    services-flake.url = "github:juspay/services-flake";
  };

  outputs = inputs:
    inputs.flake-parts.lib.mkFlake {inherit inputs;} {
      systems = import inputs.systems;
      # imports = [inputs.process-compose-flake.flakeModule];

      perSystem = {pkgs, ...}: let
        env = {
          LD_LIBRARY_PATH = "${pkgs.stdenv.cc.cc.lib}/lib";
        };
      in {
        devShells.default = pkgs.mkShell {
          inherit env;
          buildInputs = with pkgs; [python312];
          shellHook = ''
            print() {
              echo
              bold=$(printf '\033[1m')
              normal=$(printf '\033[0m')
              lines=(
              "🚀 Ready to launch into dev mode!"
              ""
              "Run: ''${bold}nix run .#dev''${normal}"
              ""
              "✨ Let the magic begin! ✨"
              )
              printf "%s\n" "''${lines[@]}" | ${pkgs.boxes}/bin/boxes -d info -a l -p h2v1 -s 40
            }
            print
          '';
        };
      };
    };
}
