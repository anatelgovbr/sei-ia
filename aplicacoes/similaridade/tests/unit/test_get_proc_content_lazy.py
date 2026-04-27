#!/usr/bin/env python3
"""Teste para get_proc_content_lazy com processo 11798520."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'api_sei'))
import dotenv
dotenv.load_dotenv(".env")

from api_sei.db_models.get_content_lazy import get_proc_content_lazy

def test_get_proc_content_lazy():
    """Testa o método get_proc_content_lazy com processo 11798520."""
    processo_id = 11798520
    
    print(f"Testando get_proc_content_lazy para processo {processo_id}")
    
    try:
        resultado = get_proc_content_lazy(processo_id)
        
        print(f"Resultado obtido:")
        print(f"Número de campos no resultado: {len(resultado)}")
        
        # Mostra metadados do processo
        print(f"\nMetadados do processo:")
        for key, value in resultado.items():
            if key.startswith("metadata_"):
                print(f"  {key}: {value}")
        
        # Mostra tipos de documento encontrados
        content_keys = [key for key in resultado.keys() if key.startswith("content_id_type_doc_")]
        print(f"\nTipos de documento encontrados: {len(content_keys)}")
        
        for content_key in content_keys:
            type_doc_id = content_key.split("_")[-1]
            content_list = resultado[content_key]
            name_key = f"metadata_name_id_type_doc_{type_doc_id}"
            spec_key = f"metadata_specification_id_type_doc_{type_doc_id}"
            
            print(f"\n  Tipo de documento {type_doc_id}:")
            print(f"    Nome: {resultado.get(name_key, 'N/A')}")
            print(f"    Número de documentos: {len(content_list)}")
            print(f"    Especificações: {len(resultado.get(spec_key, []))}")
            
            for i, content in enumerate(content_list[:2]):  # Mostra apenas os 2 primeiros
                print(f"    Documento {i+1} (primeiros 150 chars): {content[:150]}...")
        
        # Mostra citações encontradas
        citations = resultado.get("content_citations", "")
        print(f"\nCitações encontradas: {citations}")
            
    except Exception as e:
        print(f"Erro durante o teste: {e}")
        print(f"Tipo do erro: {type(e).__name__}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_get_proc_content_lazy()