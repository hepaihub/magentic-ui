


import os
from typing_extensions import Annotated
import typer
from typing import Optional
from pathlib import Path
from contextlib import asynccontextmanager
import uvicorn
from src.magentic_ui.backend.cli import (
    ui, get_env_file_path,
    check_docker_running,
    check_browser_image,
    check_python_image,
    build_browser_image,
    build_python_image)

from src.magentic_ui.backend.web.app import app


here = Path(__file__).parent.resolve()

def run(
    host: str = "0.0.0.0",
    port: int = 8081,
    workers: int = 1,
    reload: Annotated[bool, typer.Option("--reload")] = False,
    docs: bool = True,
    appdir: str = str(Path.home() / ".magentic_ui"),
    database_uri: Optional[str] = None,
    upgrade_database: bool = False,
    config: Optional[str] = None,
    rebuild_docker: Optional[bool] = False,
):
    typer.echo(typer.style("Starting Magentic-UI", fg=typer.colors.GREEN, bold=True))

    # Set things up for Docker
    typer.echo("Checking if Docker is running...", nl=False)

    if not check_docker_running():
        typer.echo(typer.style("Failed\n", fg=typer.colors.RED, bold=True))
        typer.echo("Docker is not running. Please start Docker and try again.")
        raise typer.Exit(1)
    else:
        typer.echo(typer.style("OK", fg=typer.colors.GREEN, bold=True))

    typer.echo("Checking Docker vnc browser image...", nl=False)
    if not check_browser_image() or rebuild_docker:
        typer.echo(typer.style("Update\n", fg=typer.colors.YELLOW, bold=True))
        typer.echo("Building Docker vnc image (this WILL take a few minutes)")
        build_browser_image()
        typer.echo("\n")
    else:
        typer.echo(typer.style("OK", fg=typer.colors.GREEN, bold=True))

    typer.echo("Checking Docker python image...", nl=False)
    if not check_python_image() or rebuild_docker:
        typer.echo(typer.style("Update\n", fg=typer.colors.YELLOW, bold=True))
        typer.echo("Building Docker python image (this WILL take a few minutes)")
        build_python_image()
        typer.echo("\n")
    else:
        typer.echo(typer.style("OK", fg=typer.colors.GREEN, bold=True))

    # check the images again and throw an error if they are not found
    if not check_browser_image() or not check_python_image():
        typer.echo(typer.style("Failed\n", fg=typer.colors.RED, bold=True))
        typer.echo("Docker images not found. Please build the images and try again.")
        raise typer.Exit(1)

    typer.echo("Launching Web Application...")
    
    # Write configuration
    env_vars = {
        "_HOST": host,
        "_PORT": port,
        "_API_DOCS": str(docs),
    }

    if appdir:
        env_vars["_APPDIR"] = appdir
    if database_uri:
        env_vars["DATABASE_URI"] = database_uri
    if upgrade_database:
        env_vars["_UPGRADE_DATABASE"] = "1"

    env_vars["INSIDE_DOCKER"] = "0"
    env_vars["EXTERNAL_WORKSPACE_ROOT"] = appdir
    env_vars["INTERNAL_WORKSPACE_ROOT"] = appdir

    # If the config file is not provided, check for the default config file
    if not config:
        if os.path.isfile("config.yaml"):
            config = f"config.yaml"
        else:
            typer.echo("Config file not provided. Using default settings.")
    if config:
        env_vars["_CONFIG"] = config

    # Create temporary env file to share configuration with uvicorn workers
    env_file_path = get_env_file_path()
    with open(env_file_path, "w") as temp_env:
        for key, value in env_vars.items():
            temp_env.write(f"{key}={value}\n")
            
    uvicorn.run(
        # "magentic_ui.backend.web.app:app",
        app,
        host=host,
        port=port,
        workers=workers,
        reload=reload,
        reload_excludes=["**/alembic/*", "**/alembic.ini", "**/versions/*"]
        if reload
        else None,
        env_file=env_file_path,
    )
    
    
if __name__ == "__main__":
    
    run(
        config=f"{here}/config.yaml",
    )
    # ui(port=8081, reload=False)
