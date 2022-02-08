#!/bin/bash

touch log_server.txt
touch log_notebook.txt

cd data
python -u -m http.server 8000 2>&1 | tee ../log_server.txt & # -u prevents buffering
jupyter notebook \
    --port 8888 \
    --ip 0.0.0.0 \
    --allow-root \
    --NotebookApp.token='curifactory' 2>&1 | tee ../log_notebook.txt &


exec tail -f ../log_server.txt -f ../log_notebook.txt
