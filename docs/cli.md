# Command reference

Every `govwren` command. This page is written from the program itself, so it always matches
the version it ships with. Run commands with `uv run govwren …` from the project directory.

Options that come before the command apply to all of them:

```text
govwren [-h] [--version] [-c FILE] [-v | -q] COMMAND ...
```

## Commands

| Command | What it does |
|---|---|
| [`govwren init`](#govwren-init) | Set up a new installation |
| [`govwren serve`](#govwren-serve) | Run the web server |
| [`govwren demo`](#govwren-demo) | Build a fictional organization to explore |
| [`govwren db`](#govwren-db) | Look after the database schema |
| [`govwren users`](#govwren-users) | Manage accounts from the command line |
| [`govwren mail`](#govwren-mail) | Send waiting email, or test the mail settings |
| [`govwren program`](#govwren-program) | Export or load the governance program as a file |
| [`govwren verify`](#govwren-verify) | Check that the history has not been altered |
| [`govwren doctor`](#govwren-doctor) | Check that this installation is healthy |

## `govwren init`

Write a configuration file if there is none, create the data home, create or upgrade the database, and create the first administrator if there is none. Safe to run again.

| Option | Meaning |
|---|---|
| `--force` | overwrite an existing configuration file |
| `--admin-email` `EMAIL` | create the first administrator with this address |
| `--admin-name` `NAME` | the first administrator's name |
| `--password-stdin` | read the password from standard input instead of asking |

## `govwren serve`

Run GovWren's web server. It refuses to start on a database whose schema is behind; run `govwren db upgrade` first.

| Option | Meaning |
|---|---|
| `--host` | address to listen on (default: from the configuration) |
| `--port` `PORT` | port to listen on (default: from the configuration) |
| `--workers` `WORKERS` | server processes (default: from the configuration) |
| `--reload` | restart when the code changes (development) |
| `--demo-on-network` | let a demo organization listen beyond this machine (anyone who reaches it can sign in as its sample people) |

## `govwren demo`

Build the Alderpoint Institute for Medical Research, a fictional organization with thirty months of history, in its own directory. Everything in it is made by the same code the app uses. Start it with the command it prints.

| Option | Meaning |
|---|---|
| `PATH` | where to build it (default: ./demo) |
| `--seed` `SEED` | a different number gives a different Alderpoint |
| `--port` `PORT` | the port its server will use (default: 8010) |
| `--force` | rebuild a demo that is already there |

## `govwren db`

Look after the database schema.

### `govwren db upgrade`

Apply any migrations the database has not had. Export first: an upgrade cannot be undone except by restoring.

### `govwren db current`

Show which migration the database is at, and which this version expects. Exits with 1 when they differ.

## `govwren users`

Manage accounts from the command line: for setting up, and for getting back in when nobody can sign in. Everyday account management is in the app, under Admin. Changes made here are recorded in the history as made at the command line.

### `govwren users add`

Add an account. It asks for a password unless --password-stdin or --invite is given.

| Option | Meaning |
|---|---|
| `EMAIL` | the email address the person signs in with |
| `--name` | the person's name |
| `--title` | their job title |
| `--role` `ROLE` | a role: admin, governance, auditor, reviewer, reviewer=function:KEY, or steward=unit:CODE (may be repeated) |
| `--unit` `CODE` | a unit they work in, by code (may be repeated) |
| `--password-stdin` | read the password from standard input instead of asking |
| `--invite` | add them without a password: they can be named on records now, and sign in once they are given a password or use single sign-on |

### `govwren users list`

List every account with its status and roles.

### `govwren users disable`

Stop an account signing in and end its sessions. Its records and history are kept. The last active administrator cannot be disabled.

| Option | Meaning |
|---|---|
| `EMAIL` | the account's email address |

### `govwren users enable`

Let a disabled account sign in again.

| Option | Meaning |
|---|---|
| `EMAIL` | the account's email address |

### `govwren users reset-password`

Give an account a new password and end its sessions.

| Option | Meaning |
|---|---|
| `EMAIL` | the account's email address |
| `--password-stdin` | read the password from standard input instead of asking |

### `govwren users roles`

Show an account's roles, or with --set replace the roles granted in GovWren. Roles mapped from an identity provider are left alone. The last active administrator cannot lose that role.

| Option | Meaning |
|---|---|
| `EMAIL` | the account's email address |
| `--set` `ROLE` | a role: admin, governance, auditor, reviewer, reviewer=function:KEY, or steward=unit:CODE (may be repeated); with none, removes every role |

## `govwren mail`

The server sends email by itself while it runs. These commands are for testing the settings, and for sending what is waiting when the server is not running.

### `govwren mail run`

Turn waiting notices into messages, put together daily summaries if it is time, and send what is in the outbox. Exits with 1 if anything could not be sent.

### `govwren mail test`

Send one message now, to the address of an existing account, and say whether the mail server accepted it.

| Option | Meaning |
|---|---|
| `EMAIL` | the account to send it to |

## `govwren program`

The governance program (forms, the scoring model, and vocabularies) can be written out as one file, kept under version control, reviewed, and loaded into another installation.

### `govwren program export`

Write the published forms, the scoring model, and every vocabulary as one program pack.

| Option | Meaning |
|---|---|
| `--out` `FILE` | write to this file instead of the screen |

### `govwren program import`

Load a program pack. The whole file is checked first, and nothing is loaded if anything is wrong. What differs from the published program becomes a new version; earlier versions are kept, so past requests still show the form they were answered on.

| Option | Meaning |
|---|---|
| `FILE` | the pack to load |
| `--check` | check the file and change nothing |

## `govwren verify`

Recompute the hash chain over every event in the history and report the first one that does not hold. Exits with 1 if the history is broken.

## `govwren doctor`

Check the configuration, the data home, the database and its schema, and the history. Exits with 1 if anything must be fixed.
