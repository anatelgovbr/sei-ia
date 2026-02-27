# Guia de utilização de certificado SSL proprietário

Este guia tem como objetivo auxiliar na configuração de um certificado SSL proprietário para as aplicações de backend do SEI IA.

### Passos para a configuração do certificado SSL proprietário

**IMPORTANTE:** O usuário que vai executar o script deve ter permissão sudo.

1. **Criar a pasta certificado na raiz do projeto:**

```bash
sudo mkdir certificado
```

2. **Configuração do certificado:**

   **Opção A - Se você já possui um certificado SSL:**

   Copie os arquivos .key e .pem para a pasta certificado:
   ```bash
   cp [caminho do arquivo .key] certificado/seiia.key
   cp [caminho do arquivo .pem] certificado/seiia.pem
   ```

   **Opção B - Se você NÃO possui um certificado SSL:**

   O certificado será criado automaticamente durante a execução do script.

3. **Executar o script de ativação:**

```bash
sudo bash certificado_ssl_proprietario/script_ativar_ssl_proprietario.sh
```
