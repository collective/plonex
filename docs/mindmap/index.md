# plonex: installing and running Plone without the pain

## 1. The promise

The PyPI page says:

```bash
pip install Plone
```

**How far are we from this being enough?** Quite far.

## 2. Problem 1: installing

### Plone is a lot of packages

```console
$ uv pip compile <(echo Plone) --no-annotate > /dev/null
Resolved 243 packages in 10ms
```

### "OK, but it installs, so are we good?" Not really

- Unpinned resolution can give you **wrong or unsupported versions**
- Are you using a **virtualenv**?
- Is the result **reproducible**?

### Constraints are required

- Plone follows the Zope and Python release lines
- Official constraints live on **dist.plone.org**
- **plonex:** pins packages automatically from the Plone version you choose
- Or bring your own constraints file

> Result: Plone installed, with the right versions.

## 3. Problem 2: running

### The database: ZEO server

If you want multiple clients, the data must live in a ZEO server.

```console
$ .venv/bin/runzeo -C zeo.conf
...
```

- `zeo.conf` is tens of lines you don't want to read, let alone write
- Historically: `plone.recipe.zeoserver` generated it for you

### The clients: WSGI instances

```console
$ .venv/bin/runwsgi wsgi.ini
...
```

- `wsgi.ini`: ~100 lines
- It points to `zope.conf`: tens more lines
- Historically: `plone.recipe.zope2instance` (buildout)
- Today: various other ways to generate this scaffolding

## 4. Problem 3: operating

Config files exist. Now you have to **run and manage** the processes.

- More than one instance? Start, stop, and monitor them all
- Routine maintenance:
  - Backup
  - Pack
  - Cron jobs
  - Updating package dependencies
  - Running upgrade steps

## 5. Enter plonex

- Install: versions pinned from the Plone version
- Run: configuration generated for you
- Operate: one tool for the maintenance tasks
- Demo / quick start
