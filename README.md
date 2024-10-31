# Servidor de Soluções de IA do Módulo SEI IA 

O *Servidor de Soluções de IA* contém as ferramentas necessárias para o funcionamento do [módulo SEI IA](https://github.com/anatelgovbr/mod-sei-ia), composto, de forma simplificada, pelos sub-módulos:
- SEI-IA-SIMILARIDADE: Responsável pela recomendação de processos similares e de documentos similares;
- SEI-IA-ASSISTENTE: Responsável pelo Assistente baseado em Inteligência Artificial Generativa (GenAI), para responder a questionamentos dos usuários e interagir com documentos do SEI.

## Orientações Preliminares

A instalação do *Servidor de Soluções de IA* foi projetada para ser simples, automatizando todos os procedimentos possíveis. No entanto, há alguns procedimentos que, por questões de segurança ou por estarem relacionados ao ambiente onde a instalação está sendo feita, precisam ser realizados manualmente pelo administrador do ambiente computacional. 

Para melhor entendimento do manual, é **mandatório** seja feita uma leitura integral deste README e do MANUAL DE INSTALAÇÃO antes de iniciar a instalação do *Servidor de Soluções de IA*, pois dúvidas que possam surgir no início da instalação podem ser esclarecidas ao longo da leitura das demais orientações contidas nos citados documentos.

## O repositorio

Este repositório no GitHub é o local oficial onde será mantido todo o desenvolvimento do *Servidor de Soluções de IA* do Módulo SEI IA.

## Requisitos Mínimos

Os requisitos aqui apresentados são exclusivamente relacionados ao *Servidor de Soluções de IA*, não se confundindo com a infraestrutura alocada para o core ou módulos do SEI.

O *Servidor de Soluções de IA* é baseado em Docker, com todos os containers instalados e executados em um *Docker Host* de um servidor Linux. Não recomendamos a utilização de servidores Windows com WSL em ambiente produtivo. 

O *Docker Host* deve atender aos requisitos mínimos descritos abaixo. Além disso, a solução foi homologada com uma versão específica do SEI, não sendo uma versão mínima, mas sim a versão exata homologada.
- **Versão homologada do SEI**: SEI 4.0.12.
- **Docker**: Docker Community Edition (versão >= 27.1.1).
- **Servidor Linux com**:
  - **CPU**: 16 cores com 2.10GHz;
  - **RAM**: 128 GB.

## Download

O download do pacote de instalação do *Servidor de Soluções de IA* deve ser obtido na [seção Releases deste projeto no GitHub](https://github.com/anatelgovbr/sei-ia/releases).

## Instalação

As instruções de instalação podem ser encontradas na pasta `docs/` ou diretamente em **[Manual de Instalação](docs/INSTALL.md)**.

## Documentação

Uma documentaçao simplificada das APIS pode ser encontrada na pasta `docs/` ou diretamente em **[Docmentação Simplificada das APIs](docs/API_MANUAL.md)**.

## Suporte

Em caso de dúvidas ou problemas durante o procedimento de atualização, entrar em contato via e-mail com: Nei Jobson - neijobson@anatel.gov.br
