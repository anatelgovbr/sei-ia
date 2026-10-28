# syntax=docker/dockerfile:1.7

FROM searxng/searxng:latest

COPY ops/searxng/settings.yml /etc/searxng/settings.yml
