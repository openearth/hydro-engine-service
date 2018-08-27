# -*- coding: utf-8 -*-

"""Console script for hydroengine_service."""
import sys
import click

import hydroengine_service.main


@click.command()
def main(args=None):
    """Console script for hydroengine_service."""

    hydroengine_service.main.app.run(host='127.0.0.1', port=8080, debug=True)


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
