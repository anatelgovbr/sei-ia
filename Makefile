COMPOSE := docker compose --env-file default.env --env-file security.env
NB_USER := $(shell grep '^NB_USER=' default.env | cut -d'=' -f2- | cut -d'#' -f1 | tr -d '"[:space:]')
VOL_SEIIA_DIR := $(shell grep '^VOL_SEIIA_DIR=' default.env | cut -d'=' -f2- | cut -d'#' -f1 | tr -d '"[:space:]')

.PHONY: up down down-volumes check

up:
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
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

down-volumes:
	$(COMPOSE) down -v --remove-orphans
	sudo rm -rf /var/$(NB_USER)

check:
	$(COMPOSE) --profile checks up --abort-on-container-exit --exit-code-from stack-config-checker stack-config-checker
