## Backup periódico dos dados do Servidor de Soluções de IA

Um ponto importante em relação ao Servidor de Soluções de IA é a realização de backup periódico, principalmente dos bancos de dados utilizados pelas aplicações. Todos os dados do servidor são armazenados em volumes Docker e, via de regra, estão localizados na pasta `/var/lib/docker/volume`. O comando abaixo lista os volumes relacionados ao servidor:

```bash
docker volume ls | grep "^sei_ia-"
```
## Guia de utilização de certificado SSL proprietário

Após a definição e implementação da rotina de **backup periódico dos dados do Servidor de Soluções de IA**,  leia [Guia de utilização de certificado SSL proprietário](docs/SSL.md)
