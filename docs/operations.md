# Operations

This guide is for whoever keeps a GovWren server running: how large it has been measured, when to add server processes, how to back it up and restore it, and how to move it between SQLite and PostgreSQL.

[Configuration](configuration.md) covers the settings themselves.

## How large it has been measured

GovWren is measured with 10,000 use cases, their owners, links, reviews, decisions, and conditions, and a history of more than 20,000 events. The requests behind the pages people open most are each timed five times, signed in as governance, on one process on a laptop.

| Page | SQLite | PostgreSQL |
|---|---|---|
| A list of use cases: first page, searched, or filtered | under 25 ms | under 25 ms |
| One use case, its history, or its findings | under 10 ms | under 25 ms |
| A record's dossier | 20 ms | 55 ms |
| Home | 100 ms | 275 ms |
| The review queue | 90 ms | 240 ms |
| The portfolio | 150 ms | 200 ms |
| The dashboard | 200 ms | 230 ms |
| The control library | 310 ms | 330 ms |
| Measures | 400 ms | 500 ms |
| The inventory as it stood on a date | 25 ms | 25 ms |

The figures are medians. Nothing took longer than about half a second. The pages that count every record, such as Measures and the dashboard, grow with the inventory; lists and single records do not.

You can repeat the measurement on your own hardware. It builds a throwaway installation in a temporary directory and touches nothing else:

```bash
uv run python scripts/perf.py                    # 10,000 use cases on SQLite
uv run python scripts/perf.py --records 2000
```

To measure PostgreSQL, set `GOVWREN_DATABASE_URL` to an empty database first. The script exits with 1 if a median is over its budget, which is one second unless you give `--budget`.

## How many server processes

One process serves a small team well, and is all that SQLite should be given: SQLite allows one writer at a time, and `serve` warns when several workers share one SQLite file.

With PostgreSQL, add processes when many people work at once:

```toml
[server]
workers = 4
```

Each process is a whole server. They share nothing but the database and the data home, so nothing else needs setting up:

- **Sign-in sessions** are kept in the database, so a person stays signed in whichever process answers.
- **Scheduled work** is claimed in the database before it runs, so a job runs once however many processes there are.
- **The history** is appended under a lock on its last entry, so the chain stays a single line.

A sensible start is one process for each processor core, up to four. To run processes on more than one machine, every machine needs the same configuration, the same database, and the same data home on shared storage.

## Back up

A backup is one file that holds the whole installation:

```bash
uv run govwren backup --out /backups/govwren-$(date +%F).tar.gz
```

It contains every table, every evidence file and brand image, and a manifest that says what is inside. It can be made while the server is running: the tables are read in a single transaction, so they agree with each other.

- **Keep it as carefully as the database.** It holds everything, including the hashed passwords of local accounts.
- **Make one on a schedule,** every night for most installations, and keep copies somewhere other than the server.
- **Make one before every upgrade.**
- **Your configuration is not in it.** Keep `govwren.toml` and the environment variables that hold your secrets with your other server configuration.

You may also back up with your own tools: the PostgreSQL database with `pg_dump` and the data home with a file backup. Take them together, because the database says what each evidence file is and the data home holds it.

## Restore

A backup restores into an installation that holds nothing yet. GovWren refuses to restore into a database that has accounts or history, so a restore can never overwrite anything.

1. Install the same version of GovWren that made the backup, or a newer one.
2. Put your `govwren.toml` in place, pointing at an empty database and the data home you want.
3. Restore:

   ```bash
   uv run govwren restore /backups/govwren-2026-11-19.tar.gz
   ```

4. If GovWren says the backup was at an older migration, bring it up to date:

   ```bash
   uv run govwren db upgrade
   ```

5. Check, then start the server:

   ```bash
   uv run govwren doctor
   uv run govwren serve
   ```

`restore` creates the data home if it is not there, loads every row and file, and then verifies the history. If the history does not verify, it says where and stops.

Do not run `init` first. `init` sets up a new installation with a first administrator, and a database with an account in it is no longer empty.

**Practice a restore** before you need one. Restoring last night's backup onto a spare machine and running `govwren verify` is the only proof that your backups work.

## Move between SQLite and PostgreSQL

A backup does not depend on the kind of database it came from, so moving is a backup and a restore.

To move from SQLite to PostgreSQL:

1. Stop the server, so that nothing changes while you move.
2. Back up:

   ```bash
   uv run govwren backup --out move.tar.gz
   ```

3. Create an empty PostgreSQL database and install the driver, as [Use PostgreSQL](configuration.md#use-postgresql) describes.
4. Set `[database] url` in `govwren.toml` to the new database, and put its password in the environment.
5. Restore, check, and start:

   ```bash
   uv run govwren restore move.tar.gz
   uv run govwren doctor
   uv run govwren serve
   ```

Every reference, every record, and the whole history arrive as they were, and `verify` gives the same result as before the move. The evidence files are already in the data home; the restore writes them again from the backup and they are the same.

Moving from PostgreSQL to SQLite is the same in the other direction: back up, remove `[database] url`, move the old `govwren.db` out of the data home if there is one, and restore.

Keep the old database until you have checked the new one.
