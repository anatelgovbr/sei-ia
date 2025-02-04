# Servidor de Soluções de IA do Módulo SEI IA 

O *Servidor de Soluções de IA* contém as ferramentas necessárias para o funcionamento do [Módulo SEI IA](https://github.com/anatelgovbr/mod-sei-ia), composto, de forma simplificada, pelos sub-módulos:
- SEI-IA-SIMILARIDADE: Responsável pela recomendação de processos similares e de documentos similares;
- SEI-IA-ASSISTENTE: Responsável pelo Assistente baseado em Inteligência Artificial Generativa (GenAI), para executar *prompts* dos usuários e interagir com documentos do SEI.

## Orientações Preliminares

A instalação do *Servidor de Soluções de IA* foi projetada para ser simples, automatizando todos os procedimentos possíveis. No entanto, há alguns procedimentos que, por questões de segurança ou por estarem relacionados ao ambiente onde a instalação é realizada, precisam ser realizados manualmente pelo administrador do ambiente computacional. 

Para melhor entendimento do manual, é **mandatório** que seja feita uma leitura integral deste README e do **[Manual de Instalação](docs/INSTALL.md)** antes de iniciar a instalação do *Servidor de Soluções de IA*, pois dúvidas que possam surgir no início da instalação podem ser esclarecidas ao longo da leitura das demais orientações contidas nos citados documentos.

- **ATENÇÃO:** O Servidor a ser instalado NÃO DEVE ser compartilhado com outras soluções.

## Repositorio

Este repositório no GitHub é o local oficial onde será mantido todo o desenvolvimento do *Servidor de Soluções de IA* do Módulo SEI IA.

## Requisitos Mínimos

Os requisitos aqui apresentados são exclusivamente relacionados ao *Servidor de Soluções de IA*, não se confundindo com a infraestrutura alocada para o core do SEI ou seus módulos.

O *Servidor de Soluções de IA* é baseado em Docker, com todos os containers instalados e executados em um *Docker Host* de um servidor Linux. Não recomendamos a utilização de servidores Windows com WSL em ambiente produtivo.

O *Docker Host* deve atender aos requisitos mínimos descritos abaixo:
- **Docker**:
  - Docker Engine (versão >= 27.1.1).
  - Docker Compose (versão >= 2.29).
- **Servidor Linux com**:
  - **CPU**: 16 cores com 2.10GHz.
  - **RAM**: 128 GB.

 **Requisito Mínimo do SEI**: 
  - Versões v4.0.12 ou v4.1.4
  - Não é compatível com versões anteriores do SEI.
  - Para utilizar versões mais recentes do SEI, é necessário conferir previamente a compatibilidade.
  - **Para instalar o *Servidor de Soluções de IA do Módulo SEI IA* é mandatório ter o [Módulo SEI IA](https://github.com/anatelgovbr/mod-sei-ia) previamente instalado e configurado no SEI do ambiente correspondente.**
 > Observação:
 > - A funcionalidade de "Pesquisa de Documentos" (recomendação de documentos similares) somente funcionará depois que configurar pelo menos um Tipo de Documento como Alvo da Pesquisa no menu Administração > Inteligência Artificial > Pesquisa de Documentos (na seção "Tipos de Documentos Alvo da Pesquisa").

## Download

O download do pacote de instalação do *Servidor de Soluções de IA* deve ser obtido na [seção Releases deste projeto no GitHub](https://github.com/anatelgovbr/sei-ia/releases).

## Instalação

As instruções de instalação podem ser encontradas na pasta `docs/` ou diretamente em **[Manual de Instalação](docs/INSTALL.md)**.

## Documentação

Uma documentaçao simplificada das APIs pode ser encontrada na pasta `docs/` ou diretamente em **[Documentação Simplificada das APIs](docs/API_MANUAL.md)**.

## Suporte

Em caso de dúvidas ou problemas durante o procedimento de atualização, entrar em contato via e-mail com: Nei Jobson - neijobson@anatel.gov.br