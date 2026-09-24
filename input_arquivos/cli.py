"""Linha de comando `input-arquivos`: sobe o servidor ou gera a chave de cifra das credenciais.

Fica separado de `main.py` de propósito: importar `input_arquivos.main` já
constrói o app e roda o bootstrap (cria o banco local e o arquivo de chave).
`gerar-chave` não pode ter esse efeito colateral — ele serve justamente para
preparar o `.env` do servidor antes do primeiro deploy, sem subir nada.
"""

import argparse

from input_arquivos.backend.security.secret_box import generate_key


class InputArquivosCli:
    """Interpreta os argumentos do console script `input-arquivos` e executa o subcomando pedido."""

    def __init__(self) -> None:
        """Monta o parser com os subcomandos `servir` (padrão) e `gerar-chave`."""
        self._parser = argparse.ArgumentParser(
            prog="input-arquivos", description="Sistema de Ingestão de Arquivos."
        )
        subcommands = self._parser.add_subparsers(dest="command")
        subcommands.add_parser("servir", help="Sobe o servidor web (padrão quando nenhum comando é informado).")
        subcommands.add_parser(
            "gerar-chave",
            help="Imprime uma chave nova para CONFIG_ENCRYPTION_KEY, sem subir o app nem tocar no banco.",
        )

    def run(self, argv: list[str] | None = None) -> None:
        """Executa o subcomando informado.

        Args:
            argv: Argumentos da linha de comando (sem o nome do programa).
                `None` lê de `sys.argv`.
        """
        args = self._parser.parse_args(argv)
        if args.command == "gerar-chave":
            self._print_new_key()
        else:
            self._serve()

    def _print_new_key(self) -> None:
        """Imprime uma chave Fernet nova e como usá-la. Não grava nada em disco."""
        print(f"CONFIG_ENCRYPTION_KEY={generate_key()}")
        print()
        print("Cole a linha acima no .env do servidor (ou num secret do Docker) antes do primeiro deploy.")
        print("Guarde uma cópia num lugar seguro: sem ela, as credenciais salvas em /admin/settings")
        print("não podem ser decifradas. Não troque a chave de uma instalação que já tem credenciais salvas.")

    def _serve(self) -> None:
        """Sobe o servidor Uvicorn (import tardio: só aqui o app é construído)."""
        from input_arquivos.main import start

        start()


def main() -> None:
    """Entrypoint do console script `input-arquivos` declarado em `pyproject.toml`."""
    InputArquivosCli().run()
