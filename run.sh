#!/bin/bash


# Activar entorno virtual
source ./venv/bin/activate
#ejecutar uvicorn
uvicorn main:app --host 0.0.0.0 --port 5000 --reload