#!/bin/sh

docker build --quiet --tag odd:latest .
#docker build --no-cache --tag hcc-kb:latest .
docker run --rm -it -p 5004:5000 -v $(pwd):/work -w /work odd:latest $@
