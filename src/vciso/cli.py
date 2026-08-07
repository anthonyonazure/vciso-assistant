"""Typer CLI for vCISO assistant."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from vciso.board_update import generate_board_update
from vciso.db import init_db
from vciso.qa import answer_question
from vciso.seed import seed as seed_db

load_dotenv()

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()


@app.command()
def init():
    asyncio.run(init_db())
    console.print("[green]DB initialized.[/]")


@app.command()
def seed():
    db = Path("vciso.db")
    if db.exists():
        db.unlink()
        console.print("[dim]Removed existing vciso.db[/]")
    asyncio.run(seed_db())
    console.print("[green]Seeded risk register.[/]")


@app.command()
def ask(question: str = typer.Argument(..., help="The question to answer")):
    """Ask the vCISO a question (CLI form of the Slack bot)."""
    ans = asyncio.run(answer_question(question))
    console.print(f"\n[bold]{ans['answer']}[/]\n")
    console.print(
        f"[dim]KB cites: {', '.join(ans.get('kb_citations') or ['(none)'])}[/]"
    )
    if ans.get("risk_citations"):
        console.print(f"[dim]Risks: {', '.join(ans['risk_citations'])}[/]")
    console.print(f"[dim]Confidence: {ans.get('confidence', 0):.2f}[/]")


@app.command(name="board-update")
def board_update(
    period: str = typer.Option(
        None, "--period", help="YYYY-MM (default: current month)"
    ),
):
    """Generate a monthly board update PDF from the risk register."""
    result = asyncio.run(generate_board_update(period))
    console.print(
        f"[green]Board update {result['id']} generated for {result['period']}[/]"
    )
    console.print(f"PDF: {result['pdf_path']}")
    console.print(f"SHA-256: {result['sha256']}")
    s = result["summary"]
    table = Table(show_header=True, box=None)
    table.add_column("Severity")
    table.add_column("Open count")
    for sev in ["critical", "high", "medium", "low"]:
        if s["by_severity"].get(sev):
            table.add_row(sev, str(s["by_severity"][sev]))
    console.print(table)


@app.command(name="slack-bot")
def slack_bot(host: str = "0.0.0.0", port: int = 8765):
    """Run the FastAPI Slack /slack/events endpoint."""
    import uvicorn

    uvicorn.run("vciso.slack_bot:app", host=host, port=port, reload=False)


@app.command()
def version():
    from vciso import __version__

    console.print(f"vciso-assistant {__version__}")


if __name__ == "__main__":
    app()
