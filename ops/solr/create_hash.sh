#!/bin/bash
PW=$1
SALT=$(pwgen 48 -1)
echo "$(echo -n "$SALT$PW" | sha256sum -b | xxd -r -p | sha256sum -b | xxd -r -p | base64 -w 1024) $(echo -n "$SALT" | base64 -w1024)"