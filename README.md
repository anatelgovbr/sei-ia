# Servidor de Soluções de IA do Módulo SEI IA - Aplicações de Backend

O *Servidor de Soluções de IA* do Módulo SEI IA contém as ferramentas necessárias para o funcionamento do [módulo de IA do SEI](https://github.com/anatelgovbr/mod-sei-ia). Este projeto tem como objetivo o funcionamento do backend do Módulo SEI IA, composto, de forma simplificada, pelas ferramentas:
- SEI-IA-SIMILARIDADE: Responsável pela recomendação de processos similares e de documentos similares;
- SEI-IA-ASSISTENTE: Responsável pelo funcionamento do Assistente do Módulo SEI IA, utilizando Inteligência Artificial Generativa (GenAI) para responder a questionamentos dos usuários e interagir com documentos do SEI.

## Orientações Preliminares

A instalação do *Servidor de Soluções de IA* foi projetada com o objetivo principal de simplificar ao máximo o processo, automatizando todos os procedimentos possíveis. No entanto, há alguns procedimentos que, por questões de segurança ou por estarem relacionados ao ambiente de instalação, precisam ser realizados manualmente pelo administrador do ambiente computacional.

Sendo assim, sugere-se fortemente que, antes de iniciar a instalação do *Servidor de Soluções de IA*, seja feita uma leitura integral deste README e do MANUAL DE INSTALAÇÃO, pois dúvidas que possam surgir no início da instalação podem ser esclarecidas pela leitura prévia das orientações contidas nos citados documentos.

## O repositorio

Este repositório no GitHub é o local oficial onde será mantido todo o desenvolvimento do *Servidor de Soluções de IA* do Módulo SEI IA.

## Requisitos Mínimos

A solução é baseada em Docker e todos os containers são instalados e executados em um Docker *Host*. Esse *Host* deve atender aos requisitos mínimos descritos abaixo. Além disso, a solução foi homologada com uma versão específica do SEI, não sendo uma versão mínima, mas sim a versão exata homologada.
- **Versão homologada do SEI**: SEI 4.0.12
- **Docker**: Docker Community Edition (versão >= 27.1.1)
- **Hardware**:
  - **CPU**: Intel(R) Xeon(R) 2.10GHz (16 cores)
  - **RAM**: 128 GB

## Download

O download do pacote de instalação/atualização do *Servidor de Soluções de IA* pode ser encontrado na [seção Releases deste projeto no GitHub](https://github.com/anatelgovbr/sei-ia/releases). 
- **[DOWNLOAD DO PACOTE DE INSTALAÇÃO DO SERVIDOR DE SOLUÇÕES DE IA](https://github.com/anatelgovbr/sei-ia/releases)**

## Documentação

As instruções de instalação e atualização, assim como uma documentaçao simplificada dos endpoints das APIS, podem ser encontradas na pasta `docs/` ou diretamente nos links abaixo:
- **[MANUAL DE INSTALAÇÃO](docs/INSTALL.md)**
- **[DOCUMENTAÇÃO SIMPLIFICADA DAS APIs](docs/API_MANUAL.md)**

## Suporte

Em caso de dúvidas ou problemas durante o procedimento de atualização, entrar em contato com: Nei Jobson - neijobson@anatel.gov.br
