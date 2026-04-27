import copy

from bs4 import Tag

from .bs4 import BS


class Table:
    @staticmethod
    def no_span(table, logger=None):
        """
        Normaliza uma tabela HTML expandindo células com rowspan/colspan,
        reconstruindo as linhas sem spans, repetindo o conteúdo das celulas
        mescladas.

        Args:
            table: Elemento <table> (BeautifulSoup).
            logger: Logger opcional para debug.

        Returns:
            A tabela modificada, sem atributos rowspan e colspan.
        """

        def debug(mensagem):
            if logger:
                logger.debug(mensagem)

        soup = table
        while soup.parent is not None:
            soup = soup.parent

        rows = table.find_all("tr")
        grid = []

        for row_idx, row in enumerate(rows):
            debug(f"Processando linha {row_idx}")

            if len(grid) <= row_idx:
                grid.append([])

            col_idx = 0
            cells = row.find_all(["td", "th"])

            for cell in cells:
                # pular colunas já ocupadas
                while (
                    col_idx < len(grid[row_idx]) and grid[row_idx][col_idx] is not None
                ):
                    col_idx += 1

                # proteção contra valores inválidos
                try:
                    rowspan = max(1, int(cell.get("rowspan", 1)))
                except (TypeError, ValueError):
                    rowspan = 1

                try:
                    colspan = max(1, int(cell.get("colspan", 1)))
                except (TypeError, ValueError):
                    colspan = 1

                for r in range(rowspan):
                    target_row = row_idx + r

                    # garantir existência da linha
                    while len(grid) <= target_row:
                        grid.append([])

                    for c in range(colspan):
                        target_col = col_idx + c
                        row_ref = grid[target_row]

                        # expandir linha se necessário
                        if len(row_ref) <= target_col:
                            row_ref.extend([None] * (target_col + 1 - len(row_ref)))

                        row_ref[target_col] = cell

                col_idx += colspan

        # Normaliza largura
        if grid:
            max_cols = max(len(r) for r in grid)

            for r in grid:
                if len(r) < max_cols:
                    r.extend([None] * (max_cols - len(r)))

        for row_idx, row in enumerate(rows):
            row.clear()

            for cell in grid[row_idx]:
                if cell is None:
                    new_cell = soup.new_tag("td")
                else:
                    new_cell = copy.copy(cell)
                    new_cell.attrs.pop("rowspan", None)
                    new_cell.attrs.pop("colspan", None)

                row.append(new_cell)

            debug(f"Linha reconstruída {row_idx}")

        return table

    @staticmethod
    def cells_to_divs(table: Tag):
        soup = BS.get_root_el(table)
        new_divs = []

        row_parents = [table] + table.find_all(
            ["tbody", "thead", "tfoot"], recursive=False
        )

        for row_parent in row_parents:
            for tr in row_parent.find_all("tr", recursive=False):
                for cell in tr.find_all(["td", "th"], recursive=False):
                    div = soup.new_tag("div")
                    div.extend(cell.contents[:])
                    new_divs.append(div)

        for div in new_divs:
            table.insert_before(div)

        table.decompose()
        return new_divs
