
import os
import pwd
import shutil
import time
from shutil import copytree as copy_tree
from shutil import copy as copy_file
import unittest

import docker
import requests



USER_HOST = pwd.getpwuid(os.getuid()).pw_name.replace('@','')
TEST_SOLR_CONTAINER_NAME = os.getenv("TEST_SOLR_CONTAINER_NAME", "test-solr")
TEST_SOLR_PORT = os.getenv("TEST_SOLR_PORT","8997")
TEST_SOLR_IMAGE_NAME = os.getenv("TEST_SOLR_IMAGE_NAME","solr:testing")
TEST_SOLR_ADDRESS = os.getenv("TEST_SOLR_ADDRESS","http://localhost:8997")
TEST_SOLR_SEI_PROTOCOLOS_CORE_NAME = os.getenv("TEST_SOLR_SEI_PROTOCOLOS_CORE_NAME","sei_protocolos")
TEST_SOLR_PROCESS_CORE_NAME = os.getenv("TEST_SOLR_PROCESS_CORE_NAME","process")
TEST_SOLR_PROCESS_CORE_CONF = os.getenv("TEST_SOLR_PROCESS_CORE_CONF","process")
TEST_SOLR_SEI_PROTOCOLOS_CORE_CONF = os.getenv("TEST_SOLR_SEI_PROTOCOLOS_CORE_CONF","sei_protocolos")

BASE_PATH = os.path.dirname(os.path.abspath(__file__))
TEST_SOLR_CONFIGS_SRC_PATH = os.path.abspath(os.getenv("TEST_SOLR_CONFIGS_SRC_PATH",
    os.path.join(os.path.dirname(os.path.dirname(BASE_PATH)), "configs/solr_core_configs")))
TEST_SOLR_CONFIGS_DST_PATH = os.path.abspath(os.getenv("TEST_SOLR_CONFIGS_DST_PATH",
    os.path.join(BASE_PATH,"solr_core_configs")))
TEST_SOLR_DOCKERFILE_SRC_PATH = os.path.abspath(os.getenv("TEST_SOLR_DOCKERFILE_SRC_PATH",
    os.path.join(os.path.dirname(os.path.dirname(BASE_PATH)), "configs/solr.dockerfile")))
TEST_SOLR_DOCKERFILE_DST_PATH = os.path.abspath(os.getenv("TEST_SOLR_DOCKERFILE_DST_PATH",
    os.path.join(BASE_PATH,"solr.dockerfile")))
TEST_SOLR_SEI_PROTOCOLOS_DATA_PATH = os.path.abspath(os.getenv("TEST_SOLR_SEI_PROTOCOLOS_DATA_PATH",
    os.path.join(BASE_PATH,"data/solr_external_docs_test_data.json")))

def copy_solr_core_configs():
    print("TEST_SOLR_CONFIGS_SRC_PATH :", TEST_SOLR_CONFIGS_SRC_PATH)
    print("TEST_SOLR_CONFIGS_DST_PATH: ", TEST_SOLR_CONFIGS_DST_PATH)
    copy_tree(TEST_SOLR_CONFIGS_SRC_PATH, TEST_SOLR_CONFIGS_DST_PATH)


def create_solr_dockerfile():

    if os.path.isfile(TEST_SOLR_DOCKERFILE_SRC_PATH):
        copy_file(TEST_SOLR_DOCKERFILE_SRC_PATH,TEST_SOLR_DOCKERFILE_DST_PATH)

    else:
        content = "FROM solr:9.0.0\n\nCOPY --chown=8983:8983 solr_core_configs /var/solr/"

        f = open(TEST_SOLR_DOCKERFILE_DST_PATH, "w+")
        f.write(content)
        f.close()


def create_solr_image_and_container():

    client = docker.from_env()

    client.images.build(
        path = BASE_PATH,
        dockerfile = TEST_SOLR_DOCKERFILE_DST_PATH,
        tag = TEST_SOLR_IMAGE_NAME
    )

    container = client.containers.create(
        TEST_SOLR_IMAGE_NAME,
        name=f"{TEST_SOLR_CONTAINER_NAME}-{USER_HOST}",
        ports={'8983/tcp': TEST_SOLR_PORT},
        network="test_similaridade",
        detach=True)

    container.start()


def remove_solr_container_and_image():

    client = docker.from_env()

    for container in client.containers.list(filters = {"name": f"{TEST_SOLR_CONTAINER_NAME}-{USER_HOST}"} , all=True):
        container.stop()
        container.remove()

    if client.images.list(TEST_SOLR_IMAGE_NAME):
        client.images.remove(TEST_SOLR_IMAGE_NAME)


def remove_solr_core_configs_and_dockerfile():

    if os.path.isdir(TEST_SOLR_CONFIGS_DST_PATH):
        shutil.rmtree(TEST_SOLR_CONFIGS_DST_PATH)

    if os.path.isfile(TEST_SOLR_DOCKERFILE_DST_PATH):
        os.remove(TEST_SOLR_DOCKERFILE_DST_PATH)

def setup_solr(core_names):

    remove_solr_container_and_image()
    remove_solr_core_configs_and_dockerfile()

    copy_solr_core_configs()
    create_solr_dockerfile()
    create_solr_image_and_container()
    time.sleep(5)


def delete_solr():

    remove_solr_container_and_image()
    remove_solr_core_configs_and_dockerfile()

TEST_SOLR_SEI_PROTOCOLOS_CORE_NAME = os.getenv("TEST_SOLR_SEI_PROTOCOLOS_CORE_NAME","sei_protocolos")


class TestDags(unittest.TestCase):
    def setUp(self) -> None:
        setup_solr([TEST_SOLR_PROCESS_CORE_NAME,TEST_SOLR_SEI_PROTOCOLOS_CORE_NAME])
    
    def tearDown(self) -> None:
        delete_solr()
    
    def test_solr_status(self):
        response = requests.get(TEST_SOLR_ADDRESS, timeout=10)
        self.assertEqual(response.status_code, 200, f"O código de status não é 200. Recebido: {response.status_code}")
        self.assertIn("Apache SOLR", response.text, "A resposta não contém 'Apache SOLR'")



