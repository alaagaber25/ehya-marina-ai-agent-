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
      imports = [inputs.process-compose-flake.flakeModule];

      perSystem = {
        config,
        pkgs,
        ...
      }: let
        db = {
          name = "voomi";
          user = "postgres";
          password = "postgres";
          port = 5432;
        };

        env = rec {
          LD_LIBRARY_PATH = "${pkgs.stdenv.cc.cc.lib}/lib";
          DATABASE_URL = "postgresql+asyncpg://${db.user}:${db.password}@localhost:${toString db.port}/${db.name}";
        };
      in {
        process-compose.dev = {
          imports = [
            inputs.services-flake.processComposeModules.default
          ];

          services = {
            postgres.pg = {
              enable = true;
              package = pkgs.postgresql_17;
              initialScript.after = ''
                CREATE USER ${db.user} WITH password '${db.password}' SUPERUSER;
                GRANT ALL PRIVILEGES ON DATABASE ${db.name} TO ${db.user};
              '';
              initialDatabases = [{inherit (db) name;}];
            };
          };
        };

        devShells.default = pkgs.mkShell {
          inherit env;
          inputsFrom = [config.process-compose.dev.services.outputs.devShell];
          buildInputs = with pkgs; [uv];
          shellHook = ''
            print() {
              echo
              bold=$(printf '\033[1m')
              normal=$(printf '\033[0m')
              lines=(
              "🚀 Ready to launch into dev mode!"
              ""
              "Run: ''${bold}uv sync''${normal} to install dependencies"
              "Run: ''${bold}nix run .#dev''${normal} to start PostgreSQL"
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
