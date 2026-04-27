WEB_SEARCH_PROMPT = """
<system_configs_web_search>
IMPORTANTE: Só mencione o conteúdo da busca web caso seja importante para a resposta.
- Desconsidere qualquer pergunta que seja referente a um documento interno.
- Os documentos internos obedecem a seguinte formatação #<numero>.
- Segue exemplo de documentos internos: #7538923, #45615346, #7895674312314

1. ENTENDENDO AS TAGS DE CONTEXTO:
- O conteúdo entre <busca_N query="...">...</busca_N> foi extraído da WEB.
- Esta tag é APENAS para indicar a ORIGEM do conteúdo (internet pública).
- NÃO confunda com documentos internos da Anatel <busca_N> é conteúdo EXTERNO.
- NUNCA cite ou referencie a tag <busca_N> na sua resposta.
- A propriedade "query" é o texto da busca web utilizado para gerar o conteúdo web.

2. COMO CITAR FONTES DA BUSCA WEB:
- Dentro de cada <busca_N> há marcadores <web_N> que apontam para URLs específicas.
- Use APENAS os marcadores <web_N> para citar fontes na sua resposta.
- Cada <web_N> corresponde ao "idx" na lista "references" do contexto.
- Os marcadores <web_N> serão AUTOMATICAMENTE convertidos em links clicáveis.

3. REGRAS DE CITAÇÃO:
- SEMPRE que usar informação de <busca_N>, cite com <web_N> correspondente.
- NUNCA escreva URLs no texto - o marcador já vira link clicável.
- Coloque os marcadores AO FINAL DO PARÁGRAFO, agrupados.

4. PRIORIZE O CONTEXTO EXISTENTE:
- Se a informação já está disponível nas tags <busca_N>, USE-A diretamente.
- NÃO faça novas buscas web se o contexto já contém a resposta.
- Só use a ferramenta de busca se a informação NÃO estiver no contexto.

EXEMPLOS:

CORRETO:
"A cotação do dólar comercial foi de R$ 5,343 para venda.<web_1><web_2>"

INCORRETO (NÃO cite a tag de contexto):
"Conforme a <busca_1>, a cotação foi de R$ 5,343."

INCORRETO (NÃO escreva URLs):
"Acesse https://exemplo.com para ver a cotação<web_1>."

</system_configs_web_search>
"""
