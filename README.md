# OntoDev Demo

A demonstration of the [OntoDev Suite](https://ontodev.com) of ontology development and data integration tools.

## Overview

- `src/tables/` contains the project data
    - `strain.tsv` lists 10,000 (fictional) rodent strains
    - `assay.tsv` demonstrates basic validation
    - `prefix.tsv` declares namespaces to use throughout
    - `table.tsv`, `column.tsv`, `datatype.tsv` configure [VALVE](https://github.com/ontodev/valve)
    - `import_config.tsv`, `import.tsv` configure [Gadget](https://github.com/ontodev/gadget)
- `Makefile` configures various build tasks
- `Dockerfile` configures a portable Docker image

## Online Development with DROID

<https://droid.ontodev.com/ODD>

[DROID](https://github.com/ontodev/droid) is our web-based workflow execution tool. You can look around, but to do anything very interesting, you need `write` permissions on this GitHub repository. Contact james@overton.ca with your GitHub username to request access.

## Local Development with Docker

This demonstration requires a range of different software that can be difficult to install. We provide a Docker image to take care of those installation details. You should be able to `git clone` this repository and then execute development tasks inside a Docker container. The `run.sh` script tries to make this even easier:

- `./run.sh`

The `run.sh` is Unix-specific, but Docker shoud work the same under Windows.

The Dockerfile is probably specific to `x86` CPU architectures. We would like to support `arm64` -- help would be appreciated!

## Development Tasks

TODO: See the `Makefile` for now.

