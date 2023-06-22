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

# Nanobot WebUI

You can validate your data and view the Nanobot WebUI using `make serve`.
Try browsing to:

- <http://localhost:3000/table> the index table
- <http://localhost:3000/table/row/1?view=form> editing form
- <http://localhost:3000/table/row/1?view=mapping> custom editing form
  defined in `src/templates/mapping.html`

When you update your tables, run `make clean` before running `make serve` again.


# Docker

If you have Docker installed, you should be able to use it to run commands:

```sh
./run.sh make serve
```

