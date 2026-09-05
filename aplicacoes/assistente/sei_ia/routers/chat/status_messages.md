# Mensagens de Status do Streaming

As mensagens abaixo são enviadas ao usuário durante o processamento das requisições.
Cada contexto possui uma **mensagem de início**, **mensagens intermediárias** (enviadas a cada 30 segundos enquanto o processamento continua) e uma **mensagem de fim**.

---

## Pesquisa na Internet

| Tipo | Mensagem |
|------|----------|
| Início | Pesquisando na Internet |
| Intermediária | Ainda pesquisando na Internet... |
| Intermediária | Aguardando resultados da busca na web |
| Intermediária | Coletando informações da web |
| Intermediária | Consultando fontes online na web |
| Intermediária | Processando resultados da pesquisa na Internet |
| Intermediária | Busca na Internet em andamento |
| Intermediária | Reunindo dados da Internet |
| Intermediária | Aguarde, ainda pesquisando informações na web |
| Fim | Pesquisa na Internet concluída |

---

## Processamento de Documentos

| Tipo | Mensagem |
|------|----------|
| Início | Processando documentos |
| Intermediária | Ainda processando os documentos |
| Intermediária | Análise dos documentos em andamento |
| Intermediária | Lendo os documentos, aguarde |
| Intermediária | Extração de conteúdo em andamento |
| Intermediária | Interpretando o conteúdo dos documentos |
| Intermediária | Processamento dos documentos ainda em curso |
| Intermediária | Documentos sendo lidos e interpretados |
| Intermediária | Aguarde, análise dos documentos em andamento |
| Fim | Documentos processados |

---

## Recuperação do Histórico do Tópico

| Tipo | Mensagem |
|------|----------|
| Início | Recuperando mensagens anteriores do tópico |
| Intermediária | Ainda recuperando o histórico do tópico |
| Intermediária | Carregando mensagens anteriores do tópico |
| Intermediária | Buscando histórico da conversa |
| Intermediária | Recuperação das mensagens do tópico em andamento |
| Intermediária | Carregando contexto da conversa |
| Intermediária | Histórico do tópico ainda sendo recuperado |
| Intermediária | Buscando mensagens do tópico |
| Intermediária | Aguarde, histórico do tópico sendo carregado |
| Fim | Mensagens anteriores do tópico recuperadas |

---

## Vetorização de Documentos

| Tipo | Mensagem |
|------|----------|
| Início | Vetorizando documentos |
| Intermediária | Ainda vetorizando os documentos |
| Intermediária | Vetorização dos documentos em andamento |
| Intermediária | Gerando representações vetoriais dos documentos |
| Intermediária | Processando vetorização dos documentos |
| Intermediária | Aguarde, vetorização dos documentos ainda em curso |
| Intermediária | Convertendo documentos em vetores |
| Intermediária | Indexação vetorial dos documentos em andamento |
| Intermediária | Aguarde, vetorização dos documentos sendo geradas |
| Fim | Documentos vetorizados |

---

## Regras de exibição

- A **mensagem de início** é sempre a primeira exibida ao entrar em um contexto.
- As **mensagens intermediárias** são enviadas a cada **30 segundos** enquanto o processamento ainda está em andamento, escolhidas de forma **aleatória** e **nunca repetindo a mensagem anterior**.
- A **mensagem de fim** é sempre a última exibida ao concluir o contexto.
