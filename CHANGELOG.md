# v1.1.0
# Versão Intermediária - v1.1.0
**[Requisito Mínimo - SEI 4.0.12 (com ajustes em códigos para ativar ponto de extensão de módulo) ou diretamente no SEI 4.1.5 instalado/atualizado] - Não é compatível com versões anteriores e em versões mais recentes é necessário conferir antes se possui compatibilidade**
- **Para instalar o *Servidor de Soluções de IA do Módulo SEI IA* é mandatório ter o [Módulo SEI IA](https://github.com/anatelgovbr/mod-sei-ia) previamente instalado e configurado no SEI do ambiente correspondente.**
- Siga estritamente as instruções do [README.md](https://github.com/anatelgovbr/sei-ia/blob/main/README.md), especialmente a seção **Instalação**, para assegurar uma instalação > bem-sucedida.
- O não cumprimento dessas orientações poderá comprometer qualquer tipo de suporte técnico.

## Correções desta Versão
1. Correção para suportar o funcionamento junto do SEI utilizando banco de dados Oracle.

## Evoluções desta Versão
1. Banco de Dados centralizado para o back-end do SEI IA.
1. Alocação centralizada e padronizada dos volumes nomeados das aplicações.
1. Remoção do armazenamento de arquivos em pasta local (storage).
1. Ativação do protocolo HTTPS para comunicação com o Solr, Airflow, jobs_api, api_sei e api_assistente.
1. Refatoração dos nomes de variáveis de ambiente visando melhoria semântica.
1. Revisão dos comentários orientativos dos arquivos de configuração (env_files).
1. Vetorização para RAG de documentos por demanda via API.
1. Uso de Proxy Reverso da api_assistente visando escalabilidade.
1. Implementação de healthcheck para todos os serviços de back-end do SEI IA.
1. Disponibilização de script de migração de versão do SEI IA 1.0 para versão 1.1.

## Update de versões anteriores
1. Caso possua um ambiente previamente instalado do Servidor de Soluções de IA na v1.0.0, v1.0.1 ou v1.0.2, deve seguir os procedimentos reportados na seção [Update do Manual de Instalação](https://github.com/anatelgovbr/sei-ia/blob/main/docs/INSTALL.md#update).


<hr style="height:3px; background-color:white; border:none;">


# v1.0.2
# Versão Intermediária - v1.0.2
**[Requisito Mínimo - SEI 4.0.12 (com ajustes em códigos para ativar ponto de extensão de módulo) ou diretamente no SEI 4.1.4 instalado/atualizado] - Não é compatível com versões anteriores e em versões mais recentes é necessário conferir antes se possui compatibilidade**
- **Para instalar o *Servidor de Soluções de IA do Módulo SEI IA* é mandatório ter o [Módulo SEI IA](https://github.com/anatelgovbr/mod-sei-ia) previamente instalado e configurado no SEI do ambiente correspondente.**
- Siga estritamente as instruções do [README.md](https://github.com/anatelgovbr/sei-ia/blob/main/README.md), especialmente a seção **Instalação**, para assegurar uma instalação > bem-sucedida.
- O não cumprimento dessas orientações poderá comprometer qualquer tipo de suporte técnico.

## Correções desta Versão
1. Ajustes envolvendo segurança.
2. Correções nas imagens Docker.
3. Remoção de **DAGs** não usadas no AirFlow.
4. Melhorias gerais na documentação.

## Update de versões anteriores
1. Caso possua um ambiente previamente instalado do Servidor de Soluções de IA na v1.0.0 ou v1.0.1, deve seguir os procedimentos reportados na seção [Update do Manual de Instalação](https://github.com/anatelgovbr/sei-ia/blob/main/docs/INSTALL.md#update).
2. Nessa caso, tenha atenção para realizar os ajustes manuais orientados abaixo para Update.

### Ajustes manuais relacionados com o Update da v1.0.0 ou v1.0.1 para v1.0.2

1. Editar o arquivo `security.env` do ambiente, conforme abaixo:
   * Abaixo da variável `LOGLEVEL`, adicionar a linha abaixo:
```bash
export LOGLEVEL=INFO      # Define o nível de log do autodeployer como 'INFO'; opções disponíveis: INFO | DEBUG | WARNING | ERROR. Recomendamos deixar em `ERROR` em produção.
```

   * Remover a linha abaixo:
```bash
export AZURE_OPENAI_ENDPOINT=****             # Endpoint do Azure OpenAI Service. Note que não deve ser posta `/` ao final do endpoint. Exemplo: https://meuendpoint.openai.azure.com
```

3. Ajuste as permissões:
   Execute os comandos abaixo para garantir as permissões corretas no diretório de armazenamento:

```bash
sudo chmod 774 -R /opt/sei-ia-storage
sudo chown 5000:5000 /opt/sei-ia-storage
```

<hr style="height:3px; background-color:white; border:none;">

# v1.0.1
# Versão Intermediária - v1.0.1
**[Requisito Mínimo - SEI 4.0.12 (com ajustes em códigos para ativar ponto de extensão de módulo) ou diretamente no SEI 4.1.4 instalado/atualizado] - Não é compatível com versões anteriores e em versões mais recentes é necessário conferir antes se possui compatibilidade**

- **Para instalar o *Servidor de Soluções de IA do Módulo SEI IA* é mandatório ter o [Módulo SEI IA](https://github.com/anatelgovbr/mod-sei-ia) previamente instalado e configurado no SEI do ambiente correspondente.**
- Siga estritamente as instruções do [README.md](https://github.com/anatelgovbr/sei-ia/blob/main/README.md), especialmente a seção **Instalação**, para assegurar uma instalação bem-sucedida.
	- O não cumprimento dessas orientações poderá comprometer qualquer tipo de suporte técnico.

## Correções desta Versão
1. Corrigido o usuário do `pgvector` para `sei_llm` no security.env.
2. Corrigido o nome do banco de dados do `assistente` para `SEI_LLM`.
3. Corrigido o nome do banco de `similaridades` para `sei_similaridade`.
4. Ajustes e correções nas **DAGs** no AirFlow.
5. Correção para suportar o funcionamento junto do SEI utilizando banco de dados **Oracle**.
6. Melhorias gerais na documentação.

## Evoluções desta Versão
1. Disponibilizada ferramenta de "Health Checker Geral do Ambiente", conforme tópico documentado no [INSTALL.md](https://github.com/anatelgovbr/sei-ia/blob/main/docs/INSTALL.md#health-checker-geral-do-ambiente).


<hr style="height:3px; background-color:white; border:none;">


# v1.0.0
# Versão Principal - v1.0.0
**[Requisito Mínimo - SEI 4.0.12 (com ajustes em códigos para ativar ponto de extensão de módulo) ou diretamente no SEI 4.1.4 instalado/atualizado] - Não é compatível com versões anteriores e em versões mais recentes é necessário conferir antes se possui compatibilidade**

- **Para instalar o *Servidor de Soluções de IA do Módulo SEI IA* é necessário ter o [Módulo SEI IA](https://github.com/anatelgovbr/mod-sei-ia) previamente instalado e configurado no SEI do ambiente correspondente.**
 > Observação:
 > - A funcionalidade de "Pesquisa de Documentos" (recomendação de documentos similares) somente funcionará depois que configurar pelo menos um Tipo de Documento como Alvo da Pesquisa no menu Administração > Inteligência Artificial > Pesquisa de Documentos (na seção "Tipos de Documentos Alvo da Pesquisa").

- Siga estritamente as instruções do [README.md](https://github.com/anatelgovbr/sei-ia/blob/main/README.md), especialmente a seção **Instalação**, para assegurar uma instalação bem-sucedida.
	- O não cumprimento dessas orientações poderá comprometer qualquer tipo de suporte técnico.

## Funcionalidades do Módulo SEI IA na v1.0.0
1. Esta é a primeira versão do Módulo SEI IA.
2. Acesse o [Manual do Usuário do SEI IA](https://docs.google.com/document/d/e/2PACX-1vRsKljzHcKwRfdW7IcnFA1EHNPIInog9Mqpu58xEFzRMfZ5avrLhYbwUjPkXuTDFKFEPnev4ASJ-5Dm/pub "Clique e acesse") para conhecer suas funcionalidades.
3. Abaixo listamos as funcionalidades constantes nessa v1.0.0 do Módulo:
   - **Administração:**
      - **Inteligência Artificial > Configurações de Similaridade:**
            <br>- Definir se a funcionalidade "Processos Similares" será exibida.
            <br>- Definir a quantidade de processos a serem listados na funcionalidade "Processos Similares", sendo o mínimo 1 e o máximo 15. O valor padrão é 5.
            <br>- Definir as orientações que serão exibidas na tela do SEI IA na seção da funcionalidade "Processos Similares".
            <br>- Definir o percentual de relevância do conteúdo dos Documentos, o valor deve ser maior que zero e não pode exceder 100%. O valor padrão é 70%.
            <br>- Definir o percentual de relevância dos Metadados, o valor deve ser maior que zero e não pode exceder 100%. O valor padrão é 100%.
            <br>- Definir os metadados e seu percentual de relevância, o sistema obriga manter o valor de 100% nessa distribuição de percentuais. O percentual de distribuição é sobre o valor do que já foi definido no campo "Percentual de Relevância dos Metadados" Por padrão já são cadastrados na instalação 7 tipos de metadados com seus valores padrões.
      
      - **Inteligência Artificial > Configurações do Assistente IA:**
            <br>- Definir se a funcionalidade "Assistente IA" será exibida.
            <br>- Definir as orientações que serão exibidas no ícone de ajuda no "Assistente IA".
            <br>- Definir o Limite Geral de Tokens que um usuário pode utilizar por dia (milhões de tokens).
            <br>- Caso seja necessário você pode definir um Limite maior de tokens para Usuários específicos.
            <br>- Definir o LLM que deseja utilizar.
            <br>- Definir o Prompt System para o LLM.
      
      - **Inteligência Artificial > Documentos Relevantes:**
            <br>- Parametrizar quais tipos de documentos serão considerados relevantes para a funcionalidade de "Processos Similares".
			<br>- **Atenção**: O script de instalação cria uma lista inicial de Documentos Relevantes baseado em estatística sobre a massa de documentos e tipos de processos existentes na instalação do SEI. O órgão pode revisar a lista, principalmente para cadastrar tipos de documentos aplicáveis a "Todos os Tipos de Processo".
			<br>- **Cuidado**: Não se pode ter todos os tipos de documentos como relevantes, pois isso gera ruído na similaridade de processos. Apenas tipos de documentos relevantes para a instrução processual quanto ao mérito do processo devem ser cadastrados nesse menu.
                        
      - **Inteligência Artificial > Mapeamento das Integrações:**
            <br>- Parametrizar a URL do Endpoint de Autenticação da funcionalidade de "API Interna de interface entre SEI IA e LLM de IA Generativa".
            <br>- Parametrizar a URL do Endpoint de Autenticação da funcionalidade de "Autenticação junto à Solução de Inteligência Artificial do SEI".
			<br>- **Atenção**: As duas URLs acima por enquanto aceita apenas HTTP. Ainda não está aceitando a comunicação interna do SEI com o *Servidor de Soluções de IA* por meio de HTTPS.
            
      - **Inteligência Artificial > Objetivos de Desenvolvimento Sustentável da ONU:**
            <br>- Definir se a funcionalidade "Objetivos de Desenvolvimento Sustentável da ONU" será exibida.
            <br>- Definir se a funcionalidade "Objetivos de Desenvolvimento Sustentável da ONU" será exibida para classificação por Usuários Externos. **Atenção**: Essa marcação somente funcionará com o Módulo de Peticionamento na v4.3.0 em diante.
            <br>- Definir a fase de Avaliação Especializada por Racional, caso esteja ativo irá exigir que o avaliador preencha o campo "Racional" para salvar a Classificação.
            <br>- Definir as orientações que serão exibidas na tela do SEI IA na seção da funcionalidade "Objetivos de Desenvolvimento Sustentável da ONU".
            <br>- Define as unidades o qual serão alertadas em caso de pendência de Classificação ou divergência na Classificação.
            <br>- Define quais metas possuem Forte Relação Temática com o Órgão para fazer pré-filtro de apresentação para os Usuários Externos, caso esteja marcada a opção para exibir a classificação pelas ODS da ONU por Usuários Externos. É uma facilidade para não exibir todas as ODS da ONU de primeira para os Usuários Externos, exibindo em primeiro momento apenas as ODS com forte relação com o Órgão.
                        
      - **Inteligência Artificial > Pesquisa de Documentos:**
            <br>- Definir se a funcionalidade "Pesquisa de Documentos" será exibida.
            <br>- Definir na tela do SEI IA na seção da funcionalidade qual o nome irá ser exibido para o usuário.
            <br>- Definir a quantidade de Documentos a serem Listados.
            <br>- Definir as orientações que serão exibidas na tela do SEI IA na seção da funcionalidade "Pesquisa de Documentos".
            <br>- Definir quais são os Tipos de Documentos Alvo da Pesquisa.
            
   - **Funcionalidades acessadas pelos Usuários por meio do botão "Inteligência Artificial" sobre Processo ou Documento:**
		- **Objetivos de Desenvolvimento Sustentável da ONU:**
			<br>- Funcionalidade do SEI IA que apoia a classificação de processos segundo os Objetivos de Desenvolvimento Sustentável (ODS) definidos pela Organização das Nações Unidas (ONU) para a Agenda 2030. Nesta tela é possível visualizar as classificações e sugestões realizadas e realizar sua própria classificação.
		- **Processos Similares:**
			<br>- Funcionalidade do SEI IA que, utilizando técnicas de inteligência artificial, apresenta recomendação de processos similares a partir do conteúdo dos documentos e metadados. Nesta tela é possível realizar uma avaliação acerca da Similaridade.
		- **Pesquisa de Documentos:**
            <br>- Funcionalidade do SEI IA que, viabiliza a pesquisa por confronto do conteúdo de documentos com documentos, com ou sem a inserção de texto complementar para a pesquisa. Utiliza técnicas de inteligência artificial para que a pesquisa de conteúdo seja mais assertiva comparado com técnicas tradicionais de pesquisa. Nesta tela é possível realizar uma avaliação acerca da sua relevância sobre o conteúdo pesquisado.
   - **Assistente de IA:**
		- Ícone no canto inferior direito apresentado nas principais telas do SEI e Editor de Documentos.
		- O Assistente de IA é amplo e pode ser utilizado em variadas necessidades. Pode copiar e colar textos variados e demandar o que quiser do Assistente, no mesmo estilo do ChatGPT e outros.