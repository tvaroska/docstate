# Alembic Migration Versions

This directory contains Alembic migration scripts for the DocState database schema.

## How to generate migrations

After making changes to the SQLAlchemy models in `docstate/models.py`, 
generate a new migration script by running:

```shell
alembic revision --autogenerate -m "Description of your changes"
```

This will create a new migration script in this directory that captures the differences
between the current database schema and the SQLAlchemy models.

## How to apply migrations

To apply all pending migrations:

```shell
alembic upgrade head
```

To apply migrations up to a specific version:

```shell
alembic upgrade <revision_id>
```

## How to roll back migrations

To roll back the most recent migration:

```shell
alembic downgrade -1
```

To roll back to a specific version:

```shell
alembic downgrade <revision_id>
```

## Migration History

The migration history is maintained by Alembic in the database. Each migration script
contains upgrade and downgrade functions that modify the database schema accordingly.
