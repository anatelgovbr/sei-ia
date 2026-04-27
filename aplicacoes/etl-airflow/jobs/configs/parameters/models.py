"""models module."""

from datetime import datetime

from pydantic import BaseModel, Field, validator


class AdmSimilarConfig(BaseModel):
    id_md_ia_adm_config_similar: int = 1
    qtd_process_listagem: int = 5
    orientacoes_gerais: str = (
        '<p data-end="147" data-start="0">Essa funcionalidade sugere processos similares com base no conte&uacute;do '
        "dos documentos e nas informa&ccedil;&otilde;es cadastradas, usando intelig&ecirc;ncia artificial.</p>"
        '¶¶<p data-end="368" data-start="149">A opini&a'
    )
    perc_relev_cont_doc: int = 70
    perc_relev_metadados: int = 30
    dth_alteracao: datetime = datetime(2023, 12, 5, 8, 48, 44)
    sin_exibir_funcionalidade: str = "S"


class FieldEntry(BaseModel):
    weight: float
    variable_subfields: int | None = None

    def __init__(self, **data) -> None:
        data["weight"] /= 100
        super().__init__(**data)

    @validator("weight", pre=False)
    def check_weight(cls, v):
        if v < 0 or v > 1:
            raise ValueError("Weight must be between 0 and 1")
        return v


class Content(BaseModel):
    fields: dict[str, dict]
    weight: float


class Metadata(BaseModel):
    fields: dict[str, FieldEntry]
    weight: float


class RootSchema(BaseModel):
    metadata: Metadata
    content: Content

    def __init__(self, **data) -> None:
        super().__init__(**data)
        if self.metadata.weight + self.content.weight > 1:
            raise ValueError(
                "A soma dos pesos de metadata e content deve ser menor que 1"
            )


class MetadataModel(BaseModel):
    metadata_name_id_type_process: FieldEntry
    metadata_id_unit_process_generator: FieldEntry
    metadata_process_specification: FieldEntry
    metadata_id_contact_interested: FieldEntry
    metadata_info_related_processes: FieldEntry
    metadata_name_id_type_doc_: FieldEntry
    metadata_specification_id_type_doc_: FieldEntry = Field(
        default={"weight": 0, "variable_subfields": 1}
    )
    metadata_citations: FieldEntry

    def update_variable_subfields(self) -> None:
        if self.metadata_name_id_type_doc_:
            self.metadata_name_id_type_doc_.variable_subfields = 1
