# src/api_gsc_glpi/cli.py

import typer
from .worker import run_cycle  # Função de orquestração do worker

app = typer.Typer()

@app.command()
def run():
    """Rodar o worker em modo contínuo."""
    typer.echo("Iniciando o ciclo do worker...")
    run_cycle()  # Aqui a função do seu ciclo de trabalho

@app.command()
def once():
    """Rodar apenas um ciclo do worker."""
    typer.echo("Executando um ciclo único...")
    run_cycle()  # Só uma execução, sem loop infinito

if __name__ == "__main__":
    app()