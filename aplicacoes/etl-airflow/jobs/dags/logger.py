"""logger module."""

import logging

logger = logging.getLogger(__name__)

# Cria um manipulador para o console
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.WARNING)

# Formata a mensagem de log
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
console_handler.setFormatter(formatter)

# Adiciona o manipulador ao logger
logger.addHandler(console_handler)
