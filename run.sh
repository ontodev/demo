#!/bin/sh

docker run --rm -it -p 3000:3000 -v "$(pwd)":/work -w /work obolibrary/odkfull "$@"
