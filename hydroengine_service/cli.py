# -*- coding: utf-8 -*-

"""Console script for hydroengine_service."""
import sys
import click

import hydroengine_service.main


@click.command()
@click.option('--port', default=8080, type=int, help='Port number')
def main(port, args=None):
    """Console script for hydroengine_service."""

    hydroengine_service.main.app.run(host='127.0.0.1', port=port, debug=True)


if __name__ == "__main__":
    sys.exit(main())  # pragma: no cover
