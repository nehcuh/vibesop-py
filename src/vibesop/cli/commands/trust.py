"""vibe trust - Manage user trust list for skill packs."""

import typer
from rich.console import Console
from rich.table import Table

from vibesop.core.skills.trust import TrustStore

console = Console()


def trust(
    pack: str = typer.Argument(..., help="Pack name or source URL to trust"),
    source_url: str = typer.Option("", "--source", "-s", help="Source URL"),
    revoke: bool = typer.Option(False, "--revoke", "-r", help="Revoke trust"),
    list_trusted: bool = typer.Option(False, "--list", "-l", help="List trusted packs"),
) -> None:
    """Manage the skill pack trust list."""
    store = TrustStore()

    if list_trusted:
        _list_trusted(store)
        return

    if revoke:
        if store.revoke(pack):
            console.print(f"Revoked trust for {pack}")
        else:
            console.print(f"{pack} was not trusted")
        return

    if pack.startswith(("http://", "https://")):
        store.trust_source(pack)
        console.print(f"Trusted source: {pack}")
    else:
        store.trust_pack(pack, source_url)
        console.print(f"Trusted pack: {pack}")


def _list_trusted(store: TrustStore) -> None:
    t = Table(title="Trusted Skill Packs & Sources")
    t.add_column("Name/Source")
    t.add_column("Type")
    t.add_column("Trusted At")

    for name, info in store.get_trusted_packs().items():
        t.add_row(name, "pack", str(info.get("trusted_at", "")))
    for url, info in store.get_trusted_sources().items():
        t.add_row(url, "source", str(info.get("trusted_at", "")))

    console.print(t)
