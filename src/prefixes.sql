CREATE TABLE IF NOT EXISTS prefix (
  prefix TEXT PRIMARY KEY,
  base TEXT NOT NULL
);

INSERT OR IGNORE INTO prefix VALUES
("rdf", "http://www.w3.org/1999/02/22-rdf-syntax-ns#"),
("rdfs", "http://www.w3.org/2000/01/rdf-schema#"),
("xsd", "http://www.w3.org/2001/XMLSchema#"),
("owl", "http://www.w3.org/2002/07/owl#"),
("oio", "http://www.geneontology.org/formats/oboInOwl#"),
("dce", "http://purl.org/dc/elements/1.1/"),
("dct", "http://purl.org/dc/terms/"),
("foaf", "http://xmlns.com/foaf/0.1/"),
("obo", "http://purl.obolibrary.org/obo/"),

("CHEBI", "http://purl.obolibrary.org/obo/CHEBI_"),
("GO", "http://purl.obolibrary.org/obo/GO_"),
("NCBITaxon", "http://purl.obolibrary.org/obo/NCBITaxon_"),
("ncbit", "http://purl.obolibrary.org/obo/ncbitaxon#"),
("OBI", "http://purl.obolibrary.org/obo/OBI_"),
("PATO", "http://purl.obolibrary.org/obo/PATO_"),
("SO", "http://purl.obolibrary.org/obo/SO_"),
("UO", "http://purl.obolibrary.org/obo/UO_"),
("UBERON", "http://purl.obolibrary.org/obo/UBERON_");
