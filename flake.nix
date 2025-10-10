{
  description = "A simple flake including pytest for development";

  inputs.pyproject-nix.url = "github:pyproject-nix/pyproject.nix";
  inputs.pyproject-nix.inputs.nixpkgs.follows = "nixpkgs";

  outputs =
    { nixpkgs, pyproject-nix, ... }:
    let
      pkgs = nixpkgs.legacyPackages.x86_64-linux;

      python = pkgs.python313;
      project = pyproject-nix.lib.project.loadPyproject {
        projectRoot = ./.;
      };
    in
    {
      devShells.x86_64-linux.default =
        let
          arg = project.renderers.mkPythonEditablePackage { inherit python; };
          pythonEnv = python.pkgs.mkPythonEditablePackage arg;
        in
        pkgs.mkShell {
          packages = [
            pythonEnv

            python.pkgs.pytest

            pkgs.ruff
            pkgs.basedpyright
          ];
        };
    };
}
