COMPOSE := docker compose -f docker-compose.yml --env-file default.env --env-file security.env --profile web-search
BUILD_ENV := BUILDX_BUILDER=default COMPOSE_BAKE=false
# Limita somente builds distintos; serviços que compartilham imagem não têm build próprio.
BUILD_PARALLELISM ?= 3
NB_USER := $(shell grep '^NB_USER=' default.env | cut -d'=' -f2- | cut -d'#' -f1 | tr -d '"[:space:]')
NB_UID := $(shell grep '^NB_UID=' default.env | cut -d'=' -f2- | cut -d'#' -f1 | tr -d '"[:space:]')
NB_GID := $(shell grep '^NB_GID=' default.env | cut -d'=' -f2- | cut -d'#' -f1 | tr -d '"[:space:]')
VOL_SEIIA_DIR := $(shell grep '^VOL_SEIIA_DIR=' default.env | cut -d'=' -f2- | cut -d'#' -f1 | tr -d '"[:space:]')

.PHONY: up config down down-volumes check ensure-certs ensure-volumes

up: config ensure-certs ensure-volumes
	$(BUILD_ENV) $(COMPOSE) --parallel $(BUILD_PARALLELISM) build
	$(COMPOSE) up -d --no-build --remove-orphans

config:
	@test -f security.env || (echo "ERRO: copie security_example.env para security.env e preencha a configuração" >&2; exit 2)
	@test -f litellm_config.yaml || (echo "ERRO: copie litellm_config.template.yaml para litellm_config.yaml" >&2; exit 2)
	$(COMPOSE) config --quiet

ensure-volumes:
	@if [ ! -d "$(VOL_SEIIA_DIR)" ]; then \
		echo "$$(date)    ERRO: Pasta de volumes do SEI IA não está criada"; \
		echo "É obrigatório que a pasta $(VOL_SEIIA_DIR) exista e esteja devidamente configurada!"; \
		echo "Você pode usar os seguintes comandos:"; \
		echo "mkdir --parents --mode=750 $(VOL_SEIIA_DIR) && chown $(NB_USER):docker $(VOL_SEIIA_DIR)"; \
		echo ""; \
		echo "============================================="; \
		echo "ATENÇÃO: o deploy do SEI IA foi interrompido!"; \
		echo "============================================="; \
		exit 2; \
	fi
	@echo "$$(date)    INFO: Verificando volumes com permissoes corretas."
	@[ -d "$(VOL_SEIIA_DIR)/airflow_logs_vol" ] || \
		(sudo mkdir --mode=750 "$(VOL_SEIIA_DIR)/airflow_logs_vol" && \
		 sudo chown 50000:0 "$(VOL_SEIIA_DIR)/airflow_logs_vol")
	@[ -d "$(VOL_SEIIA_DIR)/airflow_postgres_vol" ] || \
		(sudo mkdir --mode=700 "$(VOL_SEIIA_DIR)/airflow_postgres_vol" && \
		 sudo chown 999:999 "$(VOL_SEIIA_DIR)/airflow_postgres_vol")
	@[ -d "$(VOL_SEIIA_DIR)/pgvector_all_vol" ] || \
		(sudo mkdir --mode=700 "$(VOL_SEIIA_DIR)/pgvector_all_vol" && \
		 sudo chown 999:999 "$(VOL_SEIIA_DIR)/pgvector_all_vol")
	@[ -d "$(VOL_SEIIA_DIR)/solr_pd_vol" ] || \
		(sudo mkdir --mode=750 "$(VOL_SEIIA_DIR)/solr_pd_vol" && \
		 sudo chown 8983:8983 "$(VOL_SEIIA_DIR)/solr_pd_vol")
	@[ -d "$(VOL_SEIIA_DIR)/session_fs_vol" ] || \
		(sudo mkdir --mode=750 "$(VOL_SEIIA_DIR)/session_fs_vol" && \
		 sudo chown $(NB_UID):$(NB_GID) "$(VOL_SEIIA_DIR)/session_fs_vol")

ensure-certs:
	@bash ops/scripts/ensure_certs.sh .

down:
	$(COMPOSE) down

down-volumes:
	$(COMPOSE) down -v --remove-orphans

check: config ensure-certs
	$(BUILD_ENV) $(COMPOSE) --profile checks run --build --rm --no-deps stack-config-checker
