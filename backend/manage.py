#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
import sys


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    if len(sys.argv) > 1 and sys.argv[1] == 'runserver':
        # porta padrão do servidor de desenvolvimento, configurável no .env
        from decouple import config
        from django.core.management.commands.runserver import Command as RunserverCommand

        RunserverCommand.default_port = str(config('DEV_SERVER_PORT', default='8010'))
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
