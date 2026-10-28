
import io
import json
import os
import pwd
import shutil
import sys
import time
from shutil import copytree as copy_tree
from shutil import copy as copy_file

import docker
import pandas as pd
import requests

from jobs.dags.database.create_solr_core import \
    create_solr_core as _create_solr_core

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
    os.path.join(os.path.dirname(os.path.dirname(BASE_PATH)), "jobs/configs/solr_core_configs/configsets")))
TEST_SOLR_CONFIGS_DST_PATH = os.path.abspath(os.getenv("TEST_SOLR_CONFIGS_DST_PATH",
    os.path.join(BASE_PATH,"solr_core_configs")))
TEST_SOLR_DOCKERFILE_SRC_PATH = os.path.abspath(os.getenv("TEST_SOLR_DOCKERFILE_SRC_PATH",
    os.path.join(os.path.dirname(os.path.dirname(BASE_PATH)), "jobs/configs/solr.dockerfile")))
TEST_SOLR_DOCKERFILE_DST_PATH = os.path.abspath(os.getenv("TEST_SOLR_DOCKERFILE_DST_PATH",
    os.path.join(BASE_PATH,"solr.dockerfile")))
TEST_SOLR_SEI_PROTOCOLOS_DATA_PATH = os.path.abspath(os.getenv("TEST_SOLR_SEI_PROTOCOLOS_DATA_PATH",
    os.path.join(BASE_PATH,"data/solr_external_docs_test_data.json")))

def copy_solr_core_configs():

    copy_tree(TEST_SOLR_CONFIGS_SRC_PATH, TEST_SOLR_CONFIGS_DST_PATH)


def create_solr_dockerfile():

    if os.path.isfile(TEST_SOLR_DOCKERFILE_SRC_PATH):
        copy_file(TEST_SOLR_DOCKERFILE_SRC_PATH,TEST_SOLR_DOCKERFILE_DST_PATH)

    else:
        content = "FROM solr:9.0.0\n\nCOPY --chown=8983:8983 solr_core_configs /var/solr/configsets"

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


def create_solr_core(core_name,core_conf):

    _create_solr_core(TEST_SOLR_ADDRESS,core_name,f"/var/solr/configsets/{core_conf}")


def populate_solr_core(data,core):

    for d in data:
        doc = {k:d[k] for k in d if k!='_version_'}
        response = requests.post(
            f"{TEST_SOLR_ADDRESS}/solr/{core}/update?wt=json",
            headers={"Content-Type":"application/json; charset=utf-8"},
            data=str({"add": {"doc": doc,"commitWithin":1000}}).encode('utf-8'), 
            timeout=5000
        )
        if response.status_code != 200:
            raise Exception(response.text)

    time.sleep(5)


def setup_solr(core_names):

    remove_solr_container_and_image()
    remove_solr_core_configs_and_dockerfile()

    copy_solr_core_configs()
    create_solr_dockerfile()
    create_solr_image_and_container()
    time.sleep(5)
    for core_name in core_names:
        if core_name == TEST_SOLR_PROCESS_CORE_NAME:
            create_solr_core(core_name,TEST_SOLR_PROCESS_CORE_CONF)
        elif core_name == TEST_SOLR_SEI_PROTOCOLOS_CORE_NAME:
            create_solr_core(core_name,TEST_SOLR_SEI_PROTOCOLOS_CORE_CONF)
        else:
            raise ValueError(f"unknown core name {core_name}")
    
    if TEST_SOLR_SEI_PROTOCOLOS_CORE_NAME in core_names:
        with open(TEST_SOLR_SEI_PROTOCOLOS_DATA_PATH, 
            'r',encoding=sys.getdefaultencoding()) as f_obj:
            data = json.load(f_obj)["response"]["docs"]
        populate_solr_core(data,TEST_SOLR_SEI_PROTOCOLOS_CORE_NAME)


def delete_solr():

    remove_solr_container_and_image()
    remove_solr_core_configs_and_dockerfile()

if __name__ == "__main__":
    setup_solr([TEST_SOLR_PROCESS_CORE_NAME,TEST_SOLR_SEI_PROTOCOLOS_CORE_NAME])
    delete_solr()
    