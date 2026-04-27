import os
import requests
import time
from w3lib.html import replace_entities

from api_sei import NER_predict
import unittest

from api_sei.envs import NER_MODEL_PATH
from api_sei.services.NER_Spacy import NER_Spacy_predict

import api_sei.services.citations_search as citations_search

class TestNER_Spacy(unittest.TestCase):

    def test_predict(self):
        text = "regimento interno da anatel, aprovado pela resolução no 612 de 29 de abril de 2013.\
            regulamento de aplicação de sanções administrativas - rasa, aprovado pela resolução nº 589,\
            de 7 de maio de 2012 e resolução no 255 de 29/03/2001. regulamento de gestão de qualidade do serviço móvel pessoal (rgq-smp),\
            aprovado pela resolução n 575 de 28 de outubro de 2011. regulamento de gestão da qualidade\
            (rqual), aprovado pela resolução nº 717, de 23/12/2019. acórdão nº 709, de 23/12/2020\
            (sei nº 6371675). acórdão nº 697, de 21/12/2020 (sei nº 6358816). acórdão nº 485, de 21/09/2020\
            (sei nº 5995158). acórdão nº 677, de 18/12/2020 (sei nº 6349764). acórdão nº 528, de 14/10/2020\
            (sei nº 6075361). acórdão nº 520, de 13/10/2020 (sei nº 6072281). acórdão nº 468, de 31/08/2020\
            (sei nº 5923262). acórdão nº 677, de 18/12/2020 (sei nº 6349764). acórdão nº 578, de 04/11/2020\
            (sei nº 6151585). acórdão nº 596, de 05/11/2020 (sei nº 6158833). acórdão nº 685, de 18/12/2020\
            (sei nº 6352350). acórdão nº 631, de 01/12/2020 (sei nº 6269254). acórdão nº 533, de 14/10/2020\
            (sei nº 6076003). acórdão nº 656, de 02/12/2020 (sei nº 6280344). acórdão 696, de 21/12/2020\
            (sei nº 6358708)."

        result = NER_predict.predict(text)
        assert result is not None
        # print('RESULT Ner -> ',result)

    def clean(self, text):

        filters = ["!", "#", "$", "%", "&", "(", ")", "/", "*", ".", ":", ";", "<", "=", ">", "?", "@", "[",
                "\\", "]", "_", "`", "{", "}", "~", "'", ","]
        for i in text:
            if i in filters:
                text = text.replace(i, " " + i + " ")
                
        text = ' '.join(text.split())
                
        return text


    def load_gt(self, doc_name_list):

        GTs = []
        for doc_name in doc_name_list:

            entities = []
            with open('/home/lx.paulop.colab/api/tests/unit/NER/' + doc_name, 'r', encoding='utf8', errors='ignore') as f:
                lines = f.readlines()
                for i, line in enumerate(lines):
                    row = line.split('#####')
                            
                    anots = row[1]
                    anot_list = anots.split('###')

                    for anot in anot_list:
                        entities.append(anot.split(';')[0].strip(' ,de'))

            GTs.append(entities)

        return GTs
        
    def get_gt(self, doc_ids):

        doc_name_list = []
        for doc_id in doc_ids:
            doc_name_list.append('test_' + str(doc_id) + '.csv')
        GTs = self.load_GT(doc_name_list)

        return GTs
    
    def get_predictions(self, doc_ids):

        NER_predict = NER_Spacy_predict(NER_MODEL_PATH)

        preds = []
        for doc_id in doc_ids:

            content = citations_search.get_doc_content(doc_id)
            content_list = citations_search.get_regex_citations(content, max_words=15)
            
            citations = []
            for c in content_list:
                citations = citations + [citation['text'].strip(' ,de') for citation in NER_predict.predict(self.clean(c))]

            preds.append(citations)

        return preds
    
    def get_metrics(self, list_list_pred, list_list_GT):

        assert len(list_list_pred) == len(list_list_GT)

        ent_intersect = 0
        len_list_pred = 0
        len_list_GT = 0
        for i, doc in enumerate(list_list_pred):

            set_pred = set(list_list_pred[i])
            set_GT = set(list_list_GT[i])

            #print('DOC:', i)
            #print(set_pred)
            #print(set_GT)

            ent_intersect += len(set_pred.intersection(set_GT))

            len_list_pred += len(set_pred)
            len_list_GT += len(set_GT)

        # Precision
        P = ent_intersect/len_list_pred

        # Recall:
        R = ent_intersect/len_list_GT

        # F1
        F1 = 2*P*R / (P+R)

        return P, R, F1
    
    def get_time(self):

        #API_ADDRESS = 'http://rhgiadtsin01:8082'
        API_ADDRESS = 'http://localhost:8082'
        API_NAME = 'document-recommenders/mlt-search-recommender-with-citations/recommendations'

        # response.elapsed.total_seconds()

        doc_ids = [
            5975971,
            2442562,
            2566465,
            6058010,
            11610049,
            6065373,
            6717050,
            5892631,
            5856017,
            9541167
        ]

        for DOC_ID in doc_ids:

            params = [
                ('list_id_doc', str(DOC_ID)),
                ('list_type_id_doc', '7'),
                ('list_type_id_doc', '8'),
                ('list_type_id_doc', '94'),
                ('rows', '10')
            ]

            #start = time.time()

            time.sleep(1.0)
            response = requests.get(
                #f"{API_ADDRESS}/{API_NAME}?list_id_doc={DOC_ID}&list_type_id_doc=7&list_type_id_doc=8&list_type_id_doc=94&rows=10"
                f"{API_ADDRESS}/{API_NAME}", params=params, timeout=60
            )#.json()["response"]["docs"][0]["content"]

            print(f"{DOC_ID}: {response.elapsed.total_seconds()}")

            #end = time.time()
            #print(end - start)

    
    def run_metrics(self):
    
        doc_ids = [
            5975971,
            2442562,
            2566465,
            6058010,
            11610049,
            6065373,
            6717050,
            5892631,
            5856017,
            9541167
        ]

        GT = self.get_GT(doc_ids)
        preds = self.get_predictions(doc_ids)

        print(self.get_metrics(preds, GT))
        #print('abacaxi')

    def process_html_raw(self, text):
    
        text = replace_entities(text)

        return text

    def test_NER_pos(self, file_path=os.path.join(os.path.dirname(os.path.abspath(__file__)),'frag2.html') ):

        with open(file_path, 'r', encoding='utf8', errors='ignore') as f:
            lines = f.read()

        citations = []

        content_list = citations_search.get_regex_citations(self.process_html_raw(lines).lower(), max_words=15)

        for c in content_list:
            citations.extend(NER_predict.predict(c))

        GT1 = self.process_html_raw(lines).lower().find('303, de 2 de julho de 2002.')
        print(GT1)

        GT2 = self.process_html_raw(lines).lower().find('345, de 4 de julho de 2012')
        print(GT2)

        print(citations)

        assert citations[0]['ini'] == GT1
        assert citations[1]['ini'] == GT2


if __name__ == '__main__':
    test = TestNER_Spacy()
    #test.run_metrics()
    #test.get_time()
    test.test_NER_pos('/home/lx.paulop.colab/api/tests/unit/frag2.html')
    #unittest.main()
