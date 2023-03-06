LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "basic": {"format": "[%(asctime)s] %(name)-35s %(levelname)8s] %(message)s"},
        "standard": {"format": "[%(asctime)s] {%(pathname)s:%(lineno)d} %(levelname)s - %(message)s", "datefmt": "%H:%M:%S"},
        "clean": {"format": "%(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "level": "DEBUG", "formatter": "basic", "stream": "ext://sys.stdout"},
        "file_debug": {"class": "logging.FileHandler", "level": "WARNING", "formatter": "standard", "filename": "debug-run.log"},
        "file_archive": {
            "class": "logging.handlers.RotatingFileHandler",
            "level": "DEBUG",
            "formatter": "standard",
            "filename": "opennem.log",
            "maxBytes": 10485760,
            "backupCount": 10,
            "encoding": "utf8",
        },
    },
    "root": {"level": "ERROR", "handlers": ["console", "file_debug"]},
    "loggers": {
        "opennem": {"level": "ERROR", "handlers": ["console", "file_debug"], "propagate": False},
        "opennem.cli": {"level": "INFO", "handlers": ["console"], "propagate": False},
        "opennem.diff": {"level": "DEBUG", "handlers": ["console"], "propagate": False},
        "shapely.geos": {"level": "INFO"},
        "urllib3": {"level": "ERROR"},
        "boto3": {"level": "ERROR"},
        "botocore": {"level": "ERROR"},
        "parso": {"level": "ERROR", "propagate": False},
        "matplotlib": {"level": "WARNING"},
    },
}
