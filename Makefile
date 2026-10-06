ifeq ($(strip $(SEARXNG_SECRET_KEY)),)
unexport SEARXNG_SECRET_KEY
endif

COMPOSE := docker compose -f docker-compose.yml --env-file default.env --env-file security.env --profile web-search
BUILD_ENV := BUILDX_BUILDER=default
# Limita somente builds distintos; serviços que compartilham imagem não têm build próprio.
BUILD_PARALLELISM ?= 3
NB_USER := $(shell grep '^NB_USER=' default.env | cut -d'=' -f2- | cut -d'#' -f1 | tr -d '"[:space:]')
NB_UID := $(shell grep '^NB_UID=' default.env | cut -d'=' -f2- | cut -d'#' -f1 | tr -d '"[:space:]')
NB_GID := $(shell grep '^NB_GID=' default.env | cut -d'=' -f2- | cut -d'#' -f1 | tr -d '"[:space:]')
VOL_SEIIA_DIR := $(shell grep '^VOL_SEIIA_DIR=' default.env | cut -d'=' -f2- | cut -d'#' -f1 | tr -d '"[:space:]')

.PHONY: up config down down-volumes check ensure-certs ensure-volumes

up: config ensure-certs ensure-volumes
	$(BUILD_ENV) python3 ops/scripts/build_images.py --parallel $(BUILD_PARALLELISM) -- $(COMPOSE)
	$(COMPOSE) up -d --no-build --remove-orphans

config:
	@test -f security.env || (echo "ERRO: copie security_example.env para security.env e preencha a configuração" >&2; exit 2)
	@test -f litellm_config.yaml || (echo "ERRO: copie litellm_config.template.yaml para litellm_config.yaml" >&2; exit 2)
	@python3 ops/scripts/ensure_searxng_secret.py security.env
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
	@set -eu; \
	if [ "$$(id -u)" -ne 0 ]; then \
		for directory in airflow_logs_vol airflow_postgres_vol pgvector_all_vol solr_pd_vol session_fs_vol; do \
			if [ ! -d "$(VOL_SEIIA_DIR)/$$directory" ]; then \
				echo "ERRO: a preparação inicial dos volumes exige privilégios administrativos." >&2; \
				echo "Solicite ao administrador: sudo make -C \"$(CURDIR)\" ensure-volumes" >&2; \
				exit 2; \
			fi; \
		done; \
		exit 0; \
	fi; \
	for spec in airflow_logs_vol:750:50000:0 airflow_postgres_vol:700:999:999 pgvector_all_vol:700:999:999 solr_pd_vol:750:8983:8983 session_fs_vol:750:$(NB_UID):$(NB_GID); do \
		directory="$${spec%%:*}"; spec="$${spec#*:}"; \
		mode="$${spec%%:*}"; owner="$${spec#*:}"; \
		if [ ! -d "$(VOL_SEIIA_DIR)/$$directory" ]; then \
			mkdir --mode="$$mode" "$(VOL_SEIIA_DIR)/$$directory"; \
			chown "$$owner" "$(VOL_SEIIA_DIR)/$$directory"; \
		fi; \
	done

ensure-certs:
	@bash ops/scripts/ensure_certs.sh .

down:
	$(COMPOSE) down

down-volumes:
	$(COMPOSE) down -v --remove-orphans

check: config ensure-certs
	$(BUILD_ENV) python3 ops/scripts/build_images.py --service stack-config-checker -- $(COMPOSE) --profile checks
	$(COMPOSE) --profile checks run --no-build --rm --no-deps stack-config-checker
