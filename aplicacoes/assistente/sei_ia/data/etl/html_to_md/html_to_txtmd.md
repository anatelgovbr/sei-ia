# Função de Conversão de HTML para Texto

Este documento descreve o desenvolvimento de uma nova versão da funcionalidade em `html_to_markdown` do módulo `data.etl.text_preprocess`, que recebe o conteúdo em texto de um documento no formato HTML, com características específicas do editor de texto do SEI, e o transforma em texto no formato Markdown.

A nova funcionalidade é encapsulada na classe `HtmlTxtmd` do módulo `data.etl.html_to_txtmd` e utiliza diversos módulos auxiliares do pacote `data.etl.html`. Esta nova versão não gera um documento estritamente Markdown. Algumas variações são aceitas para representar melhor o conteúdo semântico do documento original.

**Importante**: Como não se trata de uma conversão do formato HTML para o Markdown padrão, o formato de saída, apesar de muito semelhante ao Markdown, aceita ajustes que priorizam a legibilidade do texto, ao invés da compatibilidade estrita com o padrão. Desta forma, considera-se o consumo do resultado final como texto puro, sem processamento por renderizadores Markdown, que não entenderão as especificidades desta conversão.

## Sobre o desenvolvimento da Classe `HtmlTxtmd`

### Ferramentas 

#### BeautifulSoup e parser

É utilizado o BeautifulSoup para navegar pela árvore DOM do documento HTML. Como o parser padrão, `html.parser`, é pouco tolerante a erros e inconsistências, este foi substituído pelo parser `lxml`.

Antes, porém, de chegar a esta decisão foi utilizado o parser `html5lib`, que é o mais robusto e compatível com o padrão HTML5, dentre os três. Porém também é o mais lento.

Depois de muitos testes foi feita a opção final pelo `lxml`, que, além de ser o mais rápido dos três, também é tolerante a erros e inconsistências.

#### Docling

Versões iniciais deste novo desenvolvimento utilizaram a ferramenta Docling como auxiliar na conversão de partes do documento.

Inicialmente, processando o documento inteiro, depois de um pré-processamento de características específicas do editor SEI. Porém essa abordagem não foi viável.

Em um segundo momento chegamos a uma versão funcional utilizando o Docling como auxiliar na conversão de partes do documento, não dele inteiro. Apesar de bons resultados, desta vez foi a performance que se mostrou inviável. Depois de várias otimizações, não conseguimos baixar o tempo de execução a menos de cinco vezes mais que a versão anterior dessa funcionalidade.

Desta forma o Docling foi abandonado.

#### Python

A nova versão, por fim, utiliza apenas o já citado BeautifulSoup e recursos próprios do Python.

### Fluxo

A solução desenvolvida primeiramente:
- Troca todos os caracteres "tab" por um espaço, " ", pois no documento destino (inspirado no Markdown) este caractere pode acabar atrapalhando.
- Elimina todas as tags sem interesse para conversão. Entre outras: `head`, `style` e `script`.
- Elimina todos os elementos com `display:none` no `style`.
- Elimina todos os comentários.
- Trata todos dos elementos classificados como _phrasing content_ no HTML (permitidos dentro de `p`). Caso esses elementos não estejam dentro de uma tag `p`, eles são agrupados em uma. Isso foi feito visando facilitar o fluxo de processamento.
- Trata todas as sequências "ASCII whitespace" (`tab`, `lf`, `ff`, `cr` e `space`) de modo que seja representado mais fielmente o que é visualizado ao renderizar o documento HTML.

Então é iniciada a chamada recursiva de um método que trata as principais tags que definem blocos no HTML. Entre outras: `ol`, `ul`, `table`, `pre` e `p`.

Algumas das tags tratadas nesse método serão tratadas mais abaixo neste documento.

Um fluxo importante de dá sempre que esse método encontra uma tag `p`. Neste ponto é iniciado outra chamada recursiva a um método que cuida especificamente de tags de _phrasing content_. Entre outras: `b`, `i`, `a` e `img`.

Por fim, o texto gerado, antes de ser retornado ainda passa por uma normalização de caracteres unicode, passo que, por exemplo, transforma ligaduras nos caracteres que as formam.

### Característica principal

A principal característica da solução é tratar corretamente os elementos gerados pelo editor do SEI, especialmente aqueles baseados em classes, como o encadeamento numérico de títulos, sub-títulos, alíneas e outros, que o editor SEI gerar utilizando elementos `p` (parágrafo) com classes especiais.

## Detalhamento de algumas funcionalidades

### Caracteres passíveis de normalização por compatibilidade

São caracteres, como ligaduras, unidades de medida, caracteres estilizados, inclusos e frações.

Esses são processados utilizando normalização Unicode por compatibilidade (NFKD), que decompõe determinados caracteres em suas formas canônicas ou compatíveis.

Essa decomposição tende a reduzir variações gráficas, facilitando a leitura e o processamento textual por modelos de linguagem.

Contudo, esse processo não garante a manutenção do significado original. Para diminuir esse risco, é feita uma normalização seletiva. Foram excluídos grupos cujo processo de decomposição poderia alterar o significado semântico do texto.

Grupos excluídos e motivos:
- **Frações**: podem gerar representações de valores numéricos semanticamente distintos do original.
- **Sobrescritos/subscritos**: perdem significado de notação matemática ou química.
- **Caracteres inclusos** (como números ou letras circundadas), exceto quando representados entre parênteses: podem alterar o significado de informações próximas.

### Elementos com estilo `display: none`

Tratados no início do processamento utilizando o BeautifulSoup para identificar e remover explicitamente todos os elementos que contenham `style="display: none"`, prevendo variações de caixa e espaçamentos.

Essa abordagem garante que conteúdos intencionalmente ocultos no HTML original não sejam expostos visualmente na saída em Markdown.

#### Limitação

A remoção de elementos ocultos considera apenas o atributo `style` inline. Regras de exibição herdadas de classes CSS, definidas em tags `style` ou em arquivos externos, não são processadas.

Isso ocorre porque o BeautifulSoup realiza apenas parsing estrutural do HTML e não calcula CSS computado. Para considerar estilos efetivamente aplicados ao documento, seria necessário utilizar um mecanismo de renderização com engine de layout (como Selenium). Essa solução, embora mais completa, aumentaria significativamente a complexidade e o custo computacional.

### Linha Horizontal (como afetou a desenvolvimento)

O elemento `hr` é extremamente simples, tanto em HTML, quando em Markdown.

É um elemento do tipo "vazio" (*void*), que não pode ter nenhum nó filho. No entanto, durante testes do pré-processamento, foi descoberto um bug no tratamento do `hr`, que, dependendo do contexto, englobava parte do documento.

Pesquisas indicaram que o bug era causado pelo parser padrão do BeautifulSoup, `html.parser`. Este foi um dos motivos da adoção inicial do parser `html5lib`, muito mais confiável e resiliente.

Contudo, como já citado, o parser `html5lib` trouxe um problema de performance. O que nos levou à adoção final do parser `lxml`, com ótimo equilíbrio entre velocidade e resiliência.

### Cabeçalhos

Elementos de cabeçalho (`h1` a `h6`) no Markdown não aceitam quebra de linha (`br`). Assim as quebras de linha são substituídas por um separador _em dash_ `" — "`.

### Elementos Bloco de Código e Código Pré-formatado

O elemento `<pre>` indicam um bloco onde todos os espaçamentos originais são preservados.

Ocorrências de `<code><pre>` são tratadas como `<pre>`.

Ocorrências de `<code>` não seguidas de `<pre>` são tratadas como _phrasing_ do HTML.

### Elementos Sobrescritos e Subscritos

As ocorrências desses elementos são convertidas para o padrão do LaTeX. Tags aninhadas estão previstas.

### Listas Não Numeradas

Seguindo o padrão Markdown, é ignorada a diferenciação por tipos de bullets. Todas as listas, em todos os níveis, são geradas com marcador traço "-".

### Listas Numeradas

O formato Markdown não reconhece como item de `ol` nada além de dígitos com parêntese `")"` ou com ponto `"."`. Nem dígitos com traço `"-"`, muito menos letras ou algarismos romanos. Dessa forma, o gerado difere da especificação do Markdown.

Foi desenvolvida uma rotina que identifica, no elemento `ol`, a classe do tipo de "numeração" e cria os itens adequadamente.

Além disso, a rotina é recursiva, aceitando tantos níveis de listas ordenadas quantos houver.

Atenção especial ao estilo padrão, que muda de aparência baseado no nível da lista.

### Tabelas

Tabela em Markdown exige:
- uma e apenas uma linha de cabeçalho
- uma linha abaixo do cabeçalho

Se algo mais for adicionado, será considerado como dados abaixo do cabeçalho.

Markdown não suporta `colspan`/`rowspan` nativo

Para resolver problemas com `colspan` e `rowspan`, foi desenvolvida uma rotina que pré-processa todas as tabelas, tratando essas situações de forma adequada.

No caso de tabelas aninhadas, apenas a mais interior é tratada como tabela com dados, as anteriores são consideradas como **recurso de layout**. Desta forma, o conteúdo de cada célula destas é tratado como conteúdo de um `div`.

Tabelas que contenham qualquer elemento `ol` ou elementos `p` com classes usadas pelo editor SEI para numeração também são consideradas **recursos de layout**, e suas células são convertidas em `div`.

A tabela gerada tem o mínimo possível de caracteres, espaços e traços `"-"`, necessário para caracterizar uma tabela Markdown. Priorizando assim a diminuição do consumo de tokens de IA, em detrimento da legibilidade.

### Parágrafos com classes de numeração e estilo

O processamento de parágrafos analisa sequências de classes para gerar numeração em diversos estilos, conforme o funcionamento padrão do editor SEI.

### Quebra de linha (`br`)

Caso a tag `br` se encontre dentro de alguma tabela ou algum cabeçalho, esta é substituída por um separador _em dash_ `" — "`.

De outra forma, é substituído pelo que caracteriza o `br` em Markdown, dois espaços e uma quebra de linha, `"  \n"`.

## Comparação com versão anterior

### Performance

Com base em mais de 500 mil documentos do SEI HM utilizados como base de testes. O tempo de processamento da nova rotina em sua versão final, depois de retirado o Docling, é aproximadamente 28% mais lenta que a versão anterior. As medidas variaram de 23% a 32%, mas o resultado em torno de 28% foi o mais comum.

### Tamanho do resultado

O novo sistema, apesar de conseguir trazer mais conteúdo com mais marcadores de estilo, acaba gerando uma saída total ligeiramente menor, apenas 2%, praticamente um empate técnico. O ganho que compensa o conteúdo a mais se dá nas tabelas.

### Negrito e citação

**Antigo**: Gera apenas baseado em estilos de parágrafos do editor SEI.
**Novo**: Gera o mesmo, além de todas as ocorrências de tags HTML para essa finalidade, conforme o próximo item.

### Código e pré-formatado

**Antigo**: Apenas renderiza texto no interior da tag. Não utiliza os marcadores padrão do Markdown.
**Novo**: Renderiza com padrão do Markdown.

### Sobrescrito, itálico, tachado, link, imagem...

**Antigo**: Não gera
**Novo**: Gera todos os tipos de elementos abaixo, em qualquer lugar que estejam. Ex.: Em parágrafos, títulos, listas, células de tabela etc. Inclusive uns dentro de outros, como um link em que parte do texto está em negrito.

Elementos renderizados:
- `b`, `strong`: negrito
- `i`, `em`: itálico
- `s`, `del`: tachado
- `a`: link
    - renderiza url, texto do link e título
- `img`, `picture`, `svg`
    - renderiza url, texto alternatico e título
    - em caso de imagem embutida, renderiza texto alternativo e título
    - quanto à tag `svg` apenas cria uma marcação no local que havia a tag
- `audio`
    - renderiza url
- `video`
    - renderiza url
- `sup`, `sub`: sobrescrito e subscrito
    - renderiza no formato LaTeX
- `math`: expressão matemática
    - manter a sintaxe original

### Quebra de linha

**Antigo**: Só renderizava em parágrafos e tabelas. Sendo que em tabela, estas ficavam quebradas.
**Novo**: Renderiza em todos os lugares que aparecer, porém de duas formas distintas:
- Dentro de tabelas ou cabeçalhos HTML (`h1`-`h6`), renderiza como um separador `" — "`.
- Em todos os outros lugares renderiza no padrão Markdown: dois espaços e uma quebra de linha, `"  \n"`

### Caractere especial

**Antigo**: Só tratava cinco caracteres. Uma ligadura e quatro espaçadores.
**Novo**: Normaliza os caracteres evitando alguns grupos específicos. Isso resulta em, por exemplo, tratar todas as ligaduras.

### Linha horizontal

**Antigo**: Trata, porém não prevê o caso especial de `hr` dentro de `select`, onde não significa linha horizontal.
**Novo**: Trata prevendo o caso especial.

### Lista não ordenada

**Antigo**: Só trata um nível de lista ordenada. Tudo dentro de cada item entra como texto do item, ainda que englobe outros níveis de lista.
**Novo**: Trata adequadamente listas, incluindo sub-listas.
- Utiliza como caractere marcador o "traço/menos", `"-"`, independente do estilo indicado no HTML.

### Lista ordenada

**Antigo**: Só trata um nível de lista ordenada. Tudo dentro de cada item entra como texto do item, ainda que englobe outros níveis de lista. Segue o padrão Markdown, em que listas ordenadas sempre são numéricas.
**Novo**: Trata adequadamente listas, incluindo sub-listas.
- Não segue o padrão Markdown.
- Segue o estilo das listas, indicado por classe do editor SEI ou por tipo do padrão HTML, podendo ser numérica, alfabética e romana, e com vários tipos de separador da numeração: ")", "-" ou ".", conforme estilo ou tipo.

### Tabela

**Antigo**: Gera por código, se a tabela não tiver `rowspan` ou `colspan`, ou com auxílio do Pandas, caso contrário. Porém, em nenhuma das duas opções são previstas tabelas aninhadas. Não prevê a tag `caption`. Quando gerado por código, busca economizar _tokens_, quando gerado pelo Pandas, não.
**Novo**: Lida bem com `rowspan` e `colspan`, com tag `caption` e sempre economiza _tokens_.
- Para lidar com tabelas aninhadas utiliza a estratégia de só renderizar como tabela a mais interna, as demais são consideradas como "recurso de layout" e, desta forma suas células são transformados em blocos, `div`, do documento.
- Quebras de linha e de parágrafo são tratadas como separadores especiais, mantendo toda a informação da célula em uma linha, para não quebrar a tabela.

### Parágrafos SEI

**Antigo**: Renderiza adequadamente a numeração e o estilo indicado pelas classes específicas do editor SEI. Porém não trata nenhum elemento HTML interno ao parágrafo.
**Novo**: Renderiza adequadamente a numeração e o estilo indicado pelas classes específicas do editor SEI, e processa recursivamente todos os elementos internos.
