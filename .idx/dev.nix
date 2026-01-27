{ pkgs, ... }: {
  # Use the unstable channel to get the latest Python 3.13
  channel = "unstable";

  packages = [
    pkgs.python313
    pkgs.postgresql_16
    pkgs.redis
    pkgs.nodejs
    pkgs.docker
    pkgs.docker-compose
  ];

  env = {
    # Ensure uv uses the installed Python 3.13
    UV_PYTHON = "${pkgs.python313}/bin/python3.13";
    VIRTUAL_ENV = "/home/user/backend/.venv";
    
    # Database configuration for the app
    POSTGRE_DB = "baliblissed";
    POSTGRES_USER = "user";
    POSTGRES_PASSWORD = "password";
    POSTGRES_HOST = "localhost";
    POSTGRES_PORT = "5432";
    
    # Redis configuration for the app
    REDIS_HOST = "localhost";
    REDIS_PORT = "6379";
  };

  # Enable services managed by IDX
  services = {
    postgres = {
      enable = true;
    };
    redis = {
      enable = true;
    };
    docker = {
      enable = true;
    };
  };

  idx = {
    extensions = [
      "ms-python.python"
      "charliermarsh.ruff"
      "visualstudioexptteam.vscodeintellicode"
      "tombi-toml.tombi"
      "PKief.material-icon-theme"
      "esbenp.prettier-vscode"
      "jannchie.ruff-ignore-explainer"
      "ms-azuretools.vscode-docker"
      "docker.docker"
      "DavidAnson.vscode-markdownlint"
      "yzhang.markdown-all-in-one"
      "ms-python.vscode-python-envs"
      "mgesbert.python-path"
      "mikestead.dotenv"
      "ms-vscode-remote.remote-containers"
      "ms-azuretools.vscode-containers"
      "docker.docker"
      "bierner.markdown-emoji"
      "kilocode.kilo-code"
      "cweijan.vscode-database-client2"
      "meta.pyrefly"
      "DotJoshJohnson.xml"
      "redhat.vscode-yaml"
      "ric-v.postgres-explorer"
      "cweijan.vscode-redis-client"
    ];

    workspace = {
      # Runs when a workspace is first created
      onCreate = {
        # 1. Install the latest uv
        install-uv = "curl -LsSf https://astral.sh/uv/install.sh | sh";
        # 2. Sync dependencies
        uv-sync = "$HOME/.local/bin/uv sync";
        # 3. Install global tools
        install-ruff = "$HOME/.local/bin/uv tool install ruff";
        install-pyrefly = "$HOME/.local/bin/uv tool install pyrefly";
        install-pytest = "$HOME/.local/bin/uv tool install pytest";
        # 4. Setup Database
        # We perform a check to avoid errors if re-run, though onCreate only runs once usually.
        setup-db = ''
          if [ ! -d ".idx/.data/postgres" ]; then
            initdb -D .idx/.data/postgres
            pg_ctl -D .idx/.data/postgres start -l .idx/postgres.log || true
            sleep 2
            createuser -s user || true
            createdb -O user baliblissed || true
            pg_ctl -D .idx/.data/postgres stop
          fi
        '';
      };
      # Runs when the workspace is (re)started
      onStart = {
        # 1. Update uv
        update-uv = "if [ -f $HOME/.local/bin/uv ]; then $HOME/.local/bin/uv self update; else curl -LsSf https://astral.sh/uv/install.sh | sh; fi";
        # 2. Sync dependencies
        sync-venv = "$HOME/.local/bin/uv sync";
        # 3. Ensure Postgres is running using the local data dir
        start-postgres = "pg_ctl -D .idx/.data/postgres start -l .idx/postgres.log || true";
        # 4. Ensure Redis is running (if not managed automatically by services.redis.enable)
        # Note: services.redis.enable usually handles it, but we can start it manually if needed.
        # redis-server --daemonize yes
      };
    };
  };
}
