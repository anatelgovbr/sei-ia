#!/usr/bin/env python
"""Modelo de dados para solr knn."""

from pydantic import BaseModel


class SolrKnnConfigModel(BaseModel):
    """solr mlt configuration parameters."""

    field: str = "vector"
    id_field: str = "id"
    url: str
    group_results: bool = False
