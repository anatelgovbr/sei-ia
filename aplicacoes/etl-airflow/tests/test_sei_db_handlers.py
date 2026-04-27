import requests
import pandas as pd
from jobs.db_models.sei_db_handlers import SEIDBHandler, SeiDBAPIError, SeiDBAPIUnavailableError
from jobs.envs import SEI_API_DB_ADDRESS, SEI_API_DB_USER, SEI_API_DB_IDENTIFIER_SERVICE, VERIFY_SSL, SEI_API_DB_TIMEOUT


def test_md_ia_lista_tipo_documento_real_api():
    """Testa se o endpoint md_ia_lista_tipo_documento retorna status 200 com requisição real."""
    
    print("🔄 Testando endpoint md_ia_lista_tipo_documento...")
    
    try:
        # Faz a chamada real para a API
        result = SEIDBHandler.md_ia_lista_tipo_documento()
        
        print("✅ Requisição executada com sucesso!")
        print(f"📊 Tipo do resultado: {type(result)}")
        
        # Verifica se o resultado é um DataFrame
        if isinstance(result, pd.DataFrame):
            print(f"📋 DataFrame retornado com {len(result)} linhas")
            print(f"🏷️ Colunas: {list(result.columns)}")
            
            # Verifica se tem as colunas esperadas
            if "nome" in result.columns and "id_serie" in result.columns:
                print("✅ Colunas corretas encontradas: 'nome' e 'id_serie'")
                
                # Mostra alguns exemplos se existirem dados
                if len(result) > 0:
                    print("📄 Primeiros registros:")
                    for i in range(min(3, len(result))):
                        print(f"   - {result.iloc[i]['nome']} (ID: {result.iloc[i]['id_serie']})")
                else:
                    print("⚠️ DataFrame vazio - sem dados retornados")
            else:
                print(f"❌ Colunas incorretas: {list(result.columns)}")
                return False
        else:
            print(f"❌ Resultado não é um DataFrame: {type(result)}")
            return False
            
        print("✅ Teste passou com sucesso - Endpoint retorna 200!")
        return True
        
    except SeiDBAPIUnavailableError as e:
        print(f"❌ API do SEI indisponível: {e}")
        return False
        
    except SeiDBAPIError as e:
        print(f"❌ Erro na API do SEI (Status {e.status_code}): {e.detail}")
        return False
        
    except Exception as e:
        print(f"❌ Erro inesperado: {type(e).__name__}: {e}")
        return False


def test_direct_api_call():
    """Testa diretamente a API para verificar se está respondendo com 200."""
    
    print("\n🔄 Testando requisição direta à API...")
    
    try:
        # Monta URL e parâmetros como o SEIDBHandler faz
        service_endpoint = "md_ia_lista_tipo_documento"
        url = f"{SEI_API_DB_ADDRESS}/{service_endpoint}"
        params = {
            "servico": service_endpoint,
            "SiglaSistema": SEI_API_DB_USER,
            "IdentificacaoServico": SEI_API_DB_IDENTIFIER_SERVICE,
        }
        
        print(f"🌐 URL: {url}")
        print(f"📝 Parâmetros: {params}")
        
        # Faz a requisição
        response = requests.get(url, params=params, verify=VERIFY_SSL, timeout=SEI_API_DB_TIMEOUT)
        
        print(f"📊 Status Code: {response.status_code}")
        print(f"📄 Content-Type: {response.headers.get('content-type', 'N/A')}")
        
        if response.status_code == 200:
            print("✅ Requisição retornou 200!")
            
            # Tenta fazer parse do JSON
            try:
                json_data = response.json()
                print(f"📋 Dados JSON recebidos com {len(json_data.get('data', []))} registros")
                return True
            except Exception as json_error:
                print(f"⚠️ Erro ao fazer parse do JSON: {json_error}")
                print(f"📄 Conteúdo da resposta (primeiros 200 chars): {response.text[:200]}")
                return False
        else:
            print(f"❌ Status code diferente de 200: {response.status_code}")
            print(f"📄 Resposta: {response.text[:200]}")
            return False
            
    except requests.exceptions.ConnectionError as e:
        print(f"❌ Erro de conexão: {e}")
        return False
        
    except requests.exceptions.Timeout as e:
        print(f"❌ Timeout na requisição: {e}")
        return False
        
    except Exception as e:
        print(f"❌ Erro inesperado: {type(e).__name__}: {e}")
        return False


if __name__ == "__main__":
    print("🧪 Iniciando testes reais da API SEI...")
    print("=" * 50)
    
    # Teste 1: Chamada através do SEIDBHandler
    success1 = test_md_ia_lista_tipo_documento_real_api()
    
    # Teste 2: Chamada direta à API
    success2 = test_direct_api_call()
    
    print("\n" + "=" * 50)
    print("📊 RESUMO DOS TESTES:")
    print(f"   SEIDBHandler: {'✅ PASSOU' if success1 else '❌ FALHOU'}")
    print(f"   API Direta:   {'✅ PASSOU' if success2 else '❌ FALHOU'}")
    
    if success1 and success2:
        print("\n🎉 Todos os testes passaram! O endpoint está funcionando corretamente.")
    else:
        print("\n⚠️ Alguns testes falharam. Verifique a configuração da API.")
        exit(1)