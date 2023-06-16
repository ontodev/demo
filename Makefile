### Workflow
#
# 1. `make load` dependencies, imports, and ontology
# 2. view and edit with
#   - **Nanobot:** `./nanobot.sh` then `make save`
#   - **CGI:** `./cgi.sh` then `make save`
# 3. `make reload` imports and ontology
# 4. check the `git diff`
# 5. `git commit` then `git push` your changes
#
##### Files
#
# - `make build/demo.owl`
# - `make demo.xlsx`
# - validation `make build/messages.tsv`
	

### Configuration
#
# These are standard options to make Make sane:
# <http://clarkgrubb.com/makefile-style-guide#toc2>

MAKEFLAGS += --warn-undefined-variables
.DEFAULT_GOAL := all
.DELETE_ON_ERROR:
.SUFFIXES:
.SECONDARY:

### Definitions

define \n


endef

### Directories
#
# This is a temporary place to put things.
build build/imports/:
	mkdir -p $@

### ROBOT
#
# We use the official development version of ROBOT for most things.
build/robot.jar: | build
	curl -L -o $@ https://github.com/ontodev/robot/releases/download/v1.8.3/robot.jar

ROBOT := java -jar build/robot.jar

### LDTab
#
# Use LDTab to create SQLite databases from OWL files.
build/ldtab.jar: | build
	curl -L -o $@ "https://github.com/ontodev/ldtab.clj/releases/download/v2022-05-23/ldtab.jar"

LDTAB := java -jar build/ldtab.jar

### Nanobot
UNAME := $(shell uname)
ifeq ($(UNAME), Darwin)
    NANOBOT_URL := https://github.com/ontodev/nanobot.rs/releases/download/v0.1.0/nanobot-x86_64-apple-darwin.zip
else
    NANOBOT_URL := https://github.com/ontodev/nanobot.rs/releases/download/v2023-06-14/nanobot-x86_64-unknown-linux-musl
endif
build/nanobot: | build
	rm -f $@ $@-*
	curl -L -o $@ $(NANOBOT_URL)
	chmod +x $@

NANOBOT := build/nanobot

### Databases

TABLES := $(shell cut -f 2 src/tables/table.tsv | tail -n+2)

### Basics

.PHONY: clean
clean:
	rm -rf .nanobot.db build/

.nanobot.db: $(NANOBOT)
	$(NANOBOT) init

.PHONY: serve
serve: .nanobot.db
	$(NANOBOT) serve


### Upstream ontologies for import

build/%.owl.gz: | build
	curl -Lk "http://purl.obolibrary.org/obo/$*.owl" | gzip > $@

build/imports/%.db: build/%.owl.gz src/tables/prefix.tsv | build/ldtab.jar build/imports/
	rm -rf $@
	$(LDTAB) init $@
	sqlite3 $@ "ALTER TABLE statement RENAME TO $*;"
	$(LDTAB) prefix $@ $(word 2,$^)
	gunzip $<
	$(LDTAB) import --streaming --table $* $@ $(basename $<) || { gzip $(basename $<); exit 1; }
	gzip $(basename $<)

build/%_search_view.sql: src/scripts/search_view_template.sql
	sed 's/TABLE_NAME/$*/g' $< > $@

load_%_import: build/demo.db build/%_search_view.sql | build/imports/%.db build/ldtab.jar
	sqlite3 $< "DROP TABLE IF EXISTS $*;"
	sqlite3 build/imports/$*.db '.dump "$*"' | sqlite3 $<
	sqlite3 $< < $(word 2,$^)
	sqlite3 $< "CREATE INDEX idx_$*_subject ON $* (subject);"
	sqlite3 $< "CREATE INDEX idx_$*_predicate ON $* (predicate);"
	sqlite3 $< "CREATE INDEX idx_$*_object ON $* (object);"
	sqlite3 $< "CREATE INDEX idx_$*_datatype ON $* (datatype);"
	sqlite3 $< "ANALYZE;"

.PHONY: load_imports
load_imports: load_cob_import load_obi_import load_uberon_import load_ncbitaxon_import

### Import modules

build/%_imports.ttl: build/demo.db src/tables/import_config.tsv src/tables/import.tsv
	python3 -m gadget.extract \
	--database build/demo.db \
	--statement $* \
	--config src/tables/import_config.tsv \
	--imports src/tables/import.tsv \
	--copy rdfs:label IAO:0000111 \
	--source $*
	rm -f $@ && $(LDTAB) export -t extract $< $@

build/%_imports.owl: build/%_imports.ttl | build/robot.jar
	$(ROBOT) annotate \
	--input $< \
	--ontology-iri "http://example.com/$(notdir $@)" \
	--output $@

export_%:
	python3 -m cmi_pb_script.export data build/demo.db src/tables/ $(subst -,_,$*)

build/messages.tsv: src/tables/ | build
	python3 -m cmi_pb_script.export messages --a1 build/demo.db build assay strain

.PHONY: update_import
update_import:
	python3 -m cmi_pb_script.export data build/demo.db src/tables/ import
	python3 -m cmi_pb_script.export data build/demo.db src/tables/ import_config

.PHONY: save
#save: $(foreach t,$(wildcard src/tables/*),export_$(basename $(notdir $t)))
save: export_table export_column export_import export_assay export_strain


### Ontology

build/strain.tsv: src/tables/strain.tsv
	echo "ID	Label	Species" > $@
	echo "ID	LABEL	SC %" >> $@
	tail -n+2 $< >> $@

build/demo.owl: build/strain.tsv build/ncbitaxon_imports.owl | build/robot.jar
	$(ROBOT) merge \
	--input $(filter %.owl,$^) \
	template \
	--prefix "ex: http://example.com/" \
	--template $< \
	--merge-before \
	--output $@

# Then add OBI using LDTab
.PHONY: load_ontology
load_ontology: build/demo.owl build/demo_search_view.sql build/demo.db | build/ldtab.jar
	sqlite3 build/demo.db "DROP TABLE IF EXISTS demo;"
	sqlite3 build/demo.db "CREATE TABLE demo (assertion INT NOT NULL, retraction INT NOT NULL DEFAULT 0, graph TEXT NOT NULL, subject TEXT NOT NULL, predicate TEXT NOT NULL, object TEXT NOT NULL, datatype TEXT NOT NULL, annotation TEXT);"
	$(LDTAB) import --table demo build/demo.db $<
	sqlite3 build/demo.db < $(word 2,$^)

.PHONY: load
load: load_imports load_ontology

.PHONY: reload
reload: save load_ontology
