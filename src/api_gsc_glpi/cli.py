# src/api_gsc_glpi/cli.py
from time import sleep

import typer
from api_gsc_glpi.worker import run_cycle
from api_gsc_glpi.config import (
    POLL_INTERVAL_SECONDS
)

app = typer.Typer()

@app.command()
def run():
    while True:
        typer.echo("Iniciando o ciclo do worker...")
        run_cycle()
        sleep(POLL_INTERVAL_SECONDS)

@app.command()
def once():
    typer.echo("Executando um ciclo único...")
    run_cycle()

if __name__ == "__main__":
    app()