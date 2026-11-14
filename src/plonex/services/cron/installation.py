"""Requirements and command for the project job worker."""

from pathlib import Path

PROTOCOL_VERSION = 1
WORKER_REQUIREMENTS = ("huey[stats]>=3.5,<4",)


BACKENDS = {
    "sqlite": ("SqliteHuey", ()),
    "cy-sqlite": ("CySqliteHuey", ("cysqlite>=0.3.5",)),
    "redis": ("RedisHuey", ("redis",)),
    "redis-expire": ("RedisExpireHuey", ("redis",)),
    "priority-redis": ("PriorityRedisHuey", ("redis",)),
    "priority-redis-expire": ("PriorityRedisExpireHuey", ("redis",)),
    "postgres": ("PostgresHuey", ("psycopg>=3.2",)),
    "file": ("FileHuey", ()),
    "memory": ("MemoryHuey", ()),
    "blackhole": ("BlackHoleHuey", ()),
}


def backend_config(options):
    backend = options.get("cron_backend", "sqlite")
    if not isinstance(backend, str) or backend not in BACKENDS:
        raise ValueError("cron_backend must be one of: " + ", ".join(BACKENDS))
    settings = options.get("cron_backend_options", {})
    if not isinstance(settings, dict) or not all(isinstance(k, str) for k in settings):
        raise ValueError("cron_backend_options must be a mapping with string keys")
    if {"name", "results", "utc", "immediate", "storage_class"} & settings.keys():
        raise ValueError("cron_backend_options contains a reserved Huey option")
    return backend, dict(settings)


def worker_requirements(options):
    backend, _ = backend_config(options)
    return (*WORKER_REQUIREMENTS, *BACKENDS[backend][1])


def runtime_requirement() -> str:
    return "plonex"


def runtime_command(target: Path, configs=()) -> list[str]:
    command = [
        str(target / ".venv/bin/python"),
        "-I",
        "-B",
        "-m",
        "plonex.services.cron.runtime",
        "--target",
        str(target),
    ]
    for config in configs:
        command.extend(["--config", str(Path(config).absolute())])
    return command
