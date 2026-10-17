# Tiger Data setup for Sid

**Current status:** Sid has already created `planit-control-dev` and reported
successful migrations 001/002 plus site, weather and historical loads. Keep
using that service. For the new model-evidence migration and restricted `/ask`
login, follow [model/CORRECTIONS.md](../model/CORRECTIONS.md). The original
first-time walkthrough below is retained as reference.

The data collectors already work locally. This setup gives the team a shared
PostgreSQL database; it does not train the hazard model or connect the frontend.

## 1. Choose the team's service

Confirm which Tiger Data project Alan and the team will use. Reuse an existing
team service if there is one, so everyone connects to the same database.

If none exists, follow Tiger Data's [official service-creation guide](https://www.tigerdata.com/docs/get-started/quickstart/create-service):

1. Sign in to Tiger Console and select **New service**.
2. Choose **Shared / free** compute if offered, a suitable region, and the
   **Development** environment. Keep TimescaleDB enabled; do not choose plain
   PostgreSQL. Review any displayed cost before creating it.
3. Give it a clear team name such as `planit-control-dev` and create the service.
4. Download its database configuration into a secure place. The initial password
   is only shown during creation. Wait until the service says **Ready**.

## 2. Connect locally without putting the password in chat

Get the PostgreSQL connection URI from the service's connection details. Keep
its supplied SSL options. It looks like `postgresql://...`; that entire value
is a secret, including the password. Keep it in your password manager.

In your existing macOS **zsh** terminal inside `planit-control`, use this hidden
prompt to set it for that terminal session:

```sh
read -s "DATABASE_URL?Paste the PostgreSQL URI (input hidden): "
export DATABASE_URL
```

Paste the URI only when the hidden prompt is waiting, then press Enter. The
value is not part of the shell command history. Closing that terminal removes
this session's variable. The `.venv` can stay active. Our ingestion commands do
not currently load `.env` automatically, so saving it there alone is insufficient.

## 3. Inspect before changing a shared database

Before applying migrations, check the service's TimescaleDB version and whether
the team has already created tables. Report **Ready** to continue the guided
inspection; do not send the URI or configuration file in chat.

The intended order after inspection is foundation migration, 60-site load, then
weather load. Existing conflicting tables must be reconciled, not dropped.
Aryan owns the separate report-table setup. Hypertable conversion and the
restricted Gemini database login still require their own version/permission
checks; neither happens automatically in the current migration.

### Small hands-on check

In Tiger Console's SQL editor, run this read-only query:

```sql
SELECT current_database(), current_user;
```

It shows which database and login you reached. No secrets or data rows need to
be shared to confirm this check succeeded.
