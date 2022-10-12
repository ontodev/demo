-- Create a view with search labels as LABEL - SYNONYM [TERM ID]
DROP TABLE IF EXISTS TABLE_NAME_search_view;
CREATE TABLE TABLE_NAME_search_view AS
WITH term_ids AS (
    SELECT * FROM (
        SELECT DISTINCT subject AS subject FROM TABLE_NAME
        UNION
        SELECT DISTINCT predicate FROM TABLE_NAME
    ) AS t
),
labels AS (
    SELECT DISTINCT subject, object
    FROM TABLE_NAME WHERE predicate = 'rdfs:label'
),
synonyms AS (
    SELECT * FROM (
      SELECT DISTINCT subject, object
        FROM TABLE_NAME
       WHERE predicate IN (
         -- OBI synonym terms:
         'IAO:0000118',
         'OBI:9991118', -- IEDB alternative term
         'OBI:0001847', -- ISA alternative term
         'OBI:0001886', -- NIAID GSCID-BRC alternative term
         -- NCBITAXON, COB, and UBERON synonym terms
         'oio:hasExactSynonym',
         'oio:hasRelatedSynonym',
         'oio:hasBroadSynonym'
       )
    ) AS t
)
SELECT
    t.subject AS subject,
    COALESCE(l.object, '') || COALESCE(' - ' || s.object, '') || ' [' || t.subject || ']' AS label
FROM term_ids t
LEFT JOIN labels l ON t.subject = l.subject
LEFT JOIN synonyms s ON t.subject = s.subject
UNION
SELECT
    t.subject AS subject,
    l.object || ' [' || t.subject || ']' AS label
FROM term_ids t
JOIN labels l ON t.subject = l.subject
WHERE t.subject IN (SELECT subject FROM synonyms);
