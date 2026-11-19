# Configuration

This guide is for whoever runs the server. It covers `govwren.toml`, environment overrides, the data home, PostgreSQL, running behind a reverse proxy, and the guard on demo installations.

## What is configured where

GovWren keeps two kinds of settings apart.

| Kind | Where it lives | Examples |
|---|---|---|
| How the server runs | `govwren.toml` and the environment | Address, port, database, data home |
| The program and the product's look | The database, set in the app or by a program pack | Forms, risk tiers, routing rules, vocabularies, name, logo, colors |

This guide is about the first. For the second, see [Running the program](running-the-program.md).

## Where the file is found

`uv run govwren init` writes a commented `govwren.toml` in the current directory. Every command looks for the file in this order:

1. The `--config FILE` option (short form `-c`), given before the command.
2. The `GOVWREN_CONFIG` environment variable.
3. `./govwren.toml`.

```bash
uv run govwren --config /etc/govwren/govwren.toml doctor
```

Relative paths in the file are resolved against the file's own directory, not the directory you run from. An installation therefore moves as a unit.

## Every section and key

The file has three sections. A section or key that GovWren does not know is an error, not something it ignores. Every problem in the file is reported together.

### `[server]`

| Key | Default | Meaning |
|---|---|---|
| `host` | `"127.0.0.1"` | The address the web server listens on. Keep `127.0.0.1` when a reverse proxy on the same machine terminates TLS. Use `0.0.0.0` only behind one |
| `port` | `8000` | The port, from 1 to 65535 |
| `workers` | `1` | How many server processes to run, from 1 to 64. One is enough for SQLite and small teams |
| `base_url` | `""` | The public address people use to reach GovWren, such as `"https://govwren.example.org"`, with no path. Meant for links in messages GovWren sends. This release sends no email, so it can stay empty |
| `session_idle_hours` | `12` | A sign-in ends after this long without activity. At least 1 |
| `session_max_days` | `7` | A sign-in ends after this long in any case. At least 1 |

`host`, `port`, and `workers` can also be given to `uv run govwren serve` as `--host`, `--port`, and `--workers`, which take precedence for that run.

### `[database]`

| Key | Default | Meaning |
|---|---|---|
| `url` | `""` | Empty means SQLite, in the file `govwren.db` inside the data home. For PostgreSQL, an address beginning `postgresql+psycopg://`. See [Use PostgreSQL](#use-postgresql) |

### `[data]`

| Key | Default | Meaning |
|---|---|---|
| `home` | `"var"` | The data home: the one directory that holds everything not in the database |

### The file as written by `init`

With its comments left out:

```toml
[server]
host = "127.0.0.1"
port = 8000
workers = 1
base_url = ""
session_idle_hours = 12
session_max_days = 7

[database]
url = ""

[data]
home = "var"
```

GovWren also gives advice that does not stop it running. `serve` and `doctor` warn when several workers share one SQLite file, and when `base_url` is `http://` on a host other than localhost.

## Environment overrides

Any value can be overridden by an environment variable named `GOVWREN_<SECTION>_<KEY>`, in capitals. The environment wins over the file.

| Variable | Overrides |
|---|---|
| `GOVWREN_SERVER_HOST` | `[server] host` |
| `GOVWREN_SERVER_PORT` | `[server] port` |
| `GOVWREN_SERVER_WORKERS` | `[server] workers` |
| `GOVWREN_SERVER_BASE_URL` | `[server] base_url` |
| `GOVWREN_SERVER_SESSION_IDLE_HOURS` | `[server] session_idle_hours` |
| `GOVWREN_SERVER_SESSION_MAX_DAYS` | `[server] session_max_days` |
| `GOVWREN_DATABASE_URL` | `[database] url` |
| `GOVWREN_DATA_HOME` | `[data] home` |

```bash
GOVWREN_SERVER_PORT=8080 uv run govwren serve
```

Numbers are read from the variable's text, so `8080` works without quotes. `GOVWREN_CONFIG` is separate: it names the file itself.

## Secrets are refused in the file

`govwren.toml` is meant to be safe to read, copy, and keep under version control. GovWren refuses to start if the file holds a secret:

- A key named `password`, `secret`, `token`, `api_key`, or `key`, or ending in one of those after an underscore, is an error wherever it appears.
- A database address with a password in it is an error when it is written in the file.

Put secrets in the environment instead. For the database, set the password in `PGPASSWORD`, or put the whole address, password and all, in `GOVWREN_DATABASE_URL`.

## The data home

The data home is created by `init`. With the default settings it is `./var`.

| Path | Holds |
|---|---|
| `govwren.db` | The SQLite database, when no database address is set |
| `brand/` | Uploaded logos and the tab icon |
| `logs/` | `govwren.log`, rotated at about 5 MB, with five older files kept |
| `files/` | Reserved for evidence files and attachments, which come in a later release |
| `exports/` | Reserved for exports |
| `.govwren-home` | A marker that says this directory is a data home |

- Back it up as a whole. With PostgreSQL, back up the database as well.
- Do not edit its contents by hand.
- It must be writable by the account that runs the server.
- Request bodies and form answers are never written to the log.

## Use PostgreSQL

SQLite is the default and needs no setup. Use PostgreSQL when many people will use GovWren at once or you want more than one server process. The features and the data model are the same on both.

1. Install the driver, which is optional:

   ```bash
   uv sync --extra postgres
   ```

2. Create an empty database and a role that owns it, with your usual PostgreSQL tools.

3. Set the address in `govwren.toml`, without the password:

   ```toml
   [database]
   url = "postgresql+psycopg://govwren@db.example.org:5432/govwren"
   ```

4. Put the password in the environment, then set up and check:

   ```bash
   export PGPASSWORD='the database password'
   uv run govwren init
   uv run govwren doctor
   ```

`init` creates the schema, loads the default program, and creates the first administrator, exactly as it does on SQLite. `doctor` should report `Database: PostgreSQL`.

The address must begin `postgresql+psycopg://`. Other drivers and other databases are refused. The variable holding the password must be set for every `govwren` command and for the server.

When you update GovWren, apply schema changes before starting the server. `serve` refuses to start on a database whose schema is behind.

```bash
uv run govwren db current    # where the database is, and what this version expects
uv run govwren db upgrade    # apply what is missing
```

## Run behind a reverse proxy

GovWren serves plain HTTP. For anything beyond your own machine, put a reverse proxy in front of it to terminate TLS.

1. Keep `host = "127.0.0.1"`, so that only the proxy can reach GovWren.
2. Have the proxy forward every path to `http://127.0.0.1:8000`.
3. Have the proxy pass these headers:

| Header | Why |
|---|---|
| `Host`, or `X-Forwarded-Host` | GovWren refuses changes whose `Origin` does not match the host it was asked for. If the proxy rewrites `Host`, it must send the public name in `X-Forwarded-Host` |
| `X-Forwarded-Proto: https` | So that the session cookie is marked `Secure` |

4. Set `base_url` to the public address, such as `"https://govwren.example.org"`.

What GovWren does itself, so the proxy need not:

- It sends a strict content security policy and related security headers on every response.
- It marks API responses `Cache-Control: no-store`.
- The session cookie is `HttpOnly` and `SameSite=Strict`.
- It refuses changes that a browser marks as coming from another site.

For health checks, use `GET /api/v1/health/live` (the process is running) and `GET /api/v1/health/ready` (the database answers and its schema is current; it answers 503 when not). Neither needs a sign-in.

Sign-in is throttled after five failures in fifteen minutes, by account and, for callers that are not on the same machine, by address.

Ready-made deployment recipes are planned for a later release; see the [roadmap](../spec/roadmap.md).

## The demo and the network

A demo organization offers sign-in as any of its sample people with no password. That is safe on your own machine and nowhere else, so two guards apply.

- `serve` refuses to start a demo on any address other than `127.0.0.1`, `localhost`, or `::1`.
- Passwordless sign-in is answered only for callers on the same machine.

To let a demo be reached from other machines, for example to show it to colleagues on a trusted network, say so explicitly:

```bash
uv run govwren --config demo/govwren.toml serve --host 0.0.0.0 --demo-on-network
```

`--demo-on-network` lifts both guards for that run. Anyone who can reach the server can then sign in as any sample person, including its administrator. Do not use it on a network you do not trust, and do not publish a demo through a proxy: a proxy on the same machine can make every caller look local.

A demo is recognized by what is in its database, not by its directory. The guard does not apply to an ordinary installation, and nothing in an ordinary installation offers passwordless sign-in.

## Check your settings

```bash
uv run govwren doctor
```

`doctor` reads the configuration the same way the server does, so it is the quickest way to find a mistake. It reports the file it used, any advice, the data home, the database and its schema, and whether the history verifies.
