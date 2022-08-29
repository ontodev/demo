#!/bin/sh

#docker build --quiet --tag odd:latest .
docker build --tag odd:latest .

#docker build --no-cache --tag hcc-kb:latest .

docker run --rm -it -p 5004:5000 \
       -e PATH_INFO=/assay \
       -e REQUEST_METHOD=GET \
       -v /var/run/postgresql:/var/run/postgresql \
       -v $(pwd):/work \
       -w /work odd:latest $@
