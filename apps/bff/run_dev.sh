#!/usr/bin/env bash
pip install -r requirements.txt
uvicorn app.main:APP --host 0.0.0.0 --port 8000 --reload
