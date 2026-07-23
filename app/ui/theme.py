"""Tema visual compartilhado por todas as páginas: paleta de cores e tipografia."""

from nicegui import ui

PRIMARY = "#4f46e5"
SECONDARY = "#64748b"
ACCENT = "#4f46e5"
POSITIVE = "#16a34a"
NEGATIVE = "#dc2626"
WARNING = "#d97706"
INFO = "#0284c7"
DARK = "#1e293b"
DARK_PAGE = "#0f172a"

_HEAD_STYLES = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  body, .q-field, .q-btn, .q-table, .q-item, .q-card { font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }

  /* body.body--dark já é definido pelo Quasar com maior especificidade e prevalece no dark mode */
  body { background: #eef1f6; }

  .surface-card { border: 1px solid rgba(0, 0, 0, .07); }
  body.body--dark .surface-card { border: 1px solid rgba(255, 255, 255, .08); }

  .text-muted { color: rgba(0, 0, 0, .55); }
  body.body--dark .text-muted { color: rgba(255, 255, 255, .6); }

  .icon-badge {
    width: 2.75rem; height: 2.75rem; border-radius: 0.9rem;
    display: flex; align-items: center; justify-content: center;
    background: rgba(79, 70, 229, .12); color: #4f46e5;
  }

  .hover-lift { transition: transform .15s ease, box-shadow .15s ease; }
  .hover-lift:hover { transform: translateY(-2px); }
</style>
"""


class AppTheme:
    """Aplica a paleta de cores global e injeta a fonte/estilos compartilhados por página."""

    def configure_colors(self) -> None:
        """Define a paleta de cores da aplicação (Quasar), válida para todos os clientes.

        Deve ser chamado uma única vez, na inicialização do app (antes de
        `ui.run_with`), pois configura o tema em nível de aplicação.
        """
        from nicegui import app

        app.colors(
            primary=PRIMARY,
            secondary=SECONDARY,
            accent=ACCENT,
            positive=POSITIVE,
            negative=NEGATIVE,
            warning=WARNING,
            info=INFO,
            dark=DARK,
            dark_page=DARK_PAGE,
        )

    def apply_page_styles(self) -> None:
        """Injeta a fonte (Inter) e os estilos utilitários compartilhados no `<head>` da página atual.

        Deve ser chamado uma vez no início de cada função de página (`@ui.page`).
        """
        ui.add_head_html(_HEAD_STYLES)
