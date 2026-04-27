import logging

from bs4 import BeautifulSoup, Tag


class BS:
    """Wrapper de BeautifulSoup com parser primário e fallback automático.

    Centraliza a inicialização de objetos BeautifulSoup garantindo resiliência:
    se o parser principal falhar, tenta automaticamente o parser de fallback.
    """

    def __init__(
        self,
        logger_name: str | None = None,
        parser: str = "lxml",
        fallback_parser: str = "html5lib",
    ) -> None:
        """Inicializa o wrapper com os parsers desejados.

        Parameters
        ----------
        logger_name : str, optional
            Nome do logger. Se não fornecido, usa o nome da classe.
        parser : str, optional
            Parser principal do BeautifulSoup. Padrão: ``"lxml"``.
        fallback_parser : str, optional
            Parser utilizado caso o principal falhe. Padrão: ``"html5lib"``.
        """
        self._logger_name = logger_name or self.__class__.__name__
        self._parser = parser
        self._fallback_parser = fallback_parser

        self._logger = logging.getLogger(self._logger_name)

    def inicialize(self, html: str, *args, **kwargs) -> BeautifulSoup:
        """Cria um objeto BeautifulSoup com fallback automático de parser.

        Tenta inicializar com o parser principal. Em caso de falha, registra
        um aviso no logger e tenta novamente com o parser de fallback.

        Parameters
        ----------
        html : str
            Conteúdo HTML a ser parseado.
        *args
            Argumentos posicionais extras repassados ao BeautifulSoup.
        **kwargs
            Argumentos nomeados extras repassados ao BeautifulSoup.

        Returns
        -------
        BeautifulSoup
            Árvore HTML parseada pelo parser principal ou pelo fallback.

        Raises
        ------
        Exception
            Se o parser de fallback também falhar.
        """
        try:
            soup = BeautifulSoup(html, self._parser, *args, **kwargs)
        except Exception as e:
            self._logger.warning(
                f"Erro utilizando parser '{self._parser}': {e}\n"
                f"Tentando parser '{self._fallback_parser}'"
            )
            soup = BeautifulSoup(html, self._fallback_parser, *args, **kwargs)
        return soup

    @staticmethod
    def get_root_el(tag: Tag) -> Tag | BeautifulSoup:
        parent = tag
        while parent.parent is not None:
            parent = parent.parent
        return parent

    @staticmethod
    def has_tag_children(node):
        return any(isinstance(child, Tag) for child in node.children)

    @staticmethod
    def is_first_child_not_p(node) -> bool:
        return BS.is_first_child_not_name(node, "p")

    @staticmethod
    def is_first_child_not_name(node, name) -> bool:
        for child in node.children:
            if child.name is not None:
                return child.name != name
        return False

    @staticmethod
    def name_first_parent_in_list(node, list_names) -> str:
        for child in node.parents:
            if child.name in list_names:
                return child.name
        return ""

    @staticmethod
    def has_single_child(node, name) -> bool:
        found = False
        for child in node.children:
            if child.name is None:
                continue
            if found or child.name != name:
                return False
            found = True
        return found
