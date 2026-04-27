#!/usr/bin/env python3
"""Teste para get_doc_content_lazy com processo 1323495."""

import sys
import os
import dotenv 
dotenv.load_dotenv("../../.env")

from api_sei.db_models.get_content_lazy import get_doc_content_lazy

def test_get_doc_content_lazy():
    """Testa o método get_doc_content_lazy com processo 1323495."""
    processo_id = [
        11798521,
        11798522,
        11798527,
        11828083,
        11828087,
        11828179,
        11971893
    ]
    
    print(f"Testando get_doc_content_lazy para processo {processo_id}")
    
    try:
        # Teste com lista contendo apenas o ID do processo
        resultado = get_doc_content_lazy(processo_id)
        
        print(f"Resultado obtido:")
        print(f"Número de documentos encontrados: {len(resultado)}")
        
        for i, doc in enumerate(resultado):
            print(f"\nDocumento {i+1}:")
            print(f"  ID: {doc['id_document']}")
            print(f"  Conteúdo (primeiros 200 chars): {doc['content'][:200]}...")
            print(f"  Tamanho do conteúdo: {len(doc['content'])} caracteres")
            
    except Exception as e:
        print(f"Erro durante o teste: {e}")
        print(f"Tipo do erro: {type(e).__name__}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_get_doc_content_lazy()