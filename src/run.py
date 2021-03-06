#!/usr/bin/env python3

import csv
import difflib
import functools
import gizmos.export as export
import gizmos.search
import gizmos.tree
import json
import jwt
import logging
import os
import requests
import sqlite3

from datetime import date, datetime, timezone
from flask import abort, Flask, redirect, render_template, request, Response, session, url_for
from github import Github
from github.GithubException import GithubException
from io import StringIO
from sqlalchemy import create_engine, Column, Integer, MetaData, String, Table
from sqlalchemy.orm import scoped_session, sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from urllib.parse import parse_qs, urlencode, unquote

# Note that the following environment variables must be set:
# DATABASE_URI
# GITHUB_APP_ID
# GITHUB_APP_STATE
# GITHUB_CLIENT_ID
# GITHUB_CLIENT_SECRET
# GITHUB_PRIVATE_KEY
# FLASK_SECRET_KEY
# FLASK_HOST
# OBI_BASE_BRANCH
# OBI_REPO

# Initialize the logger:
logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Check for environment variables, exit if any are missing
DATABASE_URI = os.environ.get("DATABASE_URI")
if not DATABASE_URI:
    raise Exception("DATABASE_URI must be specified")
DROID_PATH = os.environ.get("DROID_PATH")
if not DROID_PATH:
    raise Exception("DROID_PATH must be specified")
GITHUB_APP_ID = os.environ.get("GITHUB_APP_ID")
if not GITHUB_APP_ID:
    raise Exception("GITHUB_APP_ID must be specified")
GITHUB_APP_STATE = os.environ.get("GITHUB_APP_STATE")
if not GITHUB_APP_STATE:
    raise Exception("GITHUB_APP_STATE must be specified")
GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID")
if not GITHUB_CLIENT_ID:
    raise Exception("GITHUB_CLIENT_ID must be specified")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET")
if not GITHUB_CLIENT_SECRET:
    raise Exception("GITHUB_CLIENT_SECRET must be specified")
GITHUB_PRIVATE_KEY = os.environ.get("GITHUB_PRIVATE_KEY")
if not GITHUB_PRIVATE_KEY:
    raise Exception("GITHUB_PRIVATE_KEY must be specified")
FLASK_HOST = os.environ.get("FLASK_HOST")
if not FLASK_HOST:
    raise Exception("FLASK_HOST must be specified")
FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY")
if not FLASK_SECRET_KEY:
    raise Exception("FLASK_SECRET_KEY must be specified")
OBI_BASE_BRANCH = os.environ.get("OBI_BASE_BRANCH")
if not OBI_BASE_BRANCH:
    raise Exception("OBI_BASE_BRANCH must be specified")
OBI_REPO = os.environ.get("OBI_REPO")
if not OBI_REPO:
    raise Exception("OBI_REPO must be specified")

# URLs and functions used for communicating with GitHub:
GITHUB_DEFAULT_API_HEADERS = {
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "obi-demo/1.0",
}
GITHUB_API_URL = "https://api.github.com"
GITHUB_OAUTH_URL = "https://github.com/login/oauth"

# DROID paths to fetch resources
DATABASE_DIR = os.path.join(DROID_PATH, "build")
IMPORTS_DIR = os.path.join(DROID_PATH, "src/ontology/imports")
TEMPLATES_DIR = os.path.join(DROID_PATH, "src/ontology/templates")

# Import source databases
IMPORTS = {
    "chebi": "Chemical Entities of Biological Interest",
    "cl": "Cell Ontology",
    "clo": "Cell Line Ontology",
    "envo": "Environment Ontology",
    "go": "Gene Ontology",
    "hp": "Human Phenotype Ontology",
    "ido": "Infectious Disease Ontology",
    "ncbitaxon": "NCBI Organismal Classification",
    "ogms": "Ontology for General Medical Science",
    "omiabis": "Organized MIABIS",
    "omrse": "Ontology of Medically Related Social Entities",
    "pato": "Phenotype and Trait Ontology",
    "pr": "Protein Ontology",
    "so": "Sequence Ontology",
    "uberon": "Uberon Multi-Species Anatomy Ontology",
    "uo": "Units of Measurement Ontology",
    "vo": "Vaccine Ontology",
}

# Set up the webapp
app = Flask(__name__)
app.secret_key = FLASK_SECRET_KEY

# Setup sqlalchemy to manage the database of logged in users
engine = create_engine(DATABASE_URI, connect_args={"check_same_thread": False})
db_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
Base = declarative_base()
Base.query = db_session.query_property()

# Check for tables and create them if they do not exist
meta = MetaData()
if not engine.dialect.has_table(engine, "users"):
    logging.info("Creating 'users' table...")
    user_table = Table(
        "users",
        meta,
        Column("id", Integer, primary_key=True),
        Column("github_id", Integer),
        Column("github_login", String(255)),
        Column("access_token", String(255)),
    )
    meta.create_all(engine)
if not engine.dialect.has_table(engine, "changes"):
    logging.info("Creating 'changes' table...")
    changes_table = Table(
        "changes",
        meta,
        Column("id", Integer, primary_key=True),
        Column("user_id", Integer),
        Column("file", String(255)),
        Column("file_type", String(255)),
    )
    meta.create_all(engine)
if not engine.dialect.has_table(engine, "exports"):
    logging.info("Creating 'exports' table...")
    exports_table = Table(
        "exports",
        meta,
        Column("id", Integer, primary_key=True),
        Column("user_id", Integer),
        Column("term_id", String(255)),
    )
    meta.create_all(engine)

# Make sure we have the build directory
if not os.path.exists("build"):
    os.mkdir("build")


# Decorators


def verify_logged_in(fn):
    """
    Decorator used to make sure that the user is logged in
    """

    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        # If the user is not logged in, then redirect to the "index" page:
        user_id = session.get("user_id")
        if not user_id:
            return redirect(url_for("index"))
        return fn(*args, **kwargs)

    return wrapped


# ------------------------------- MAIN APP ROUTES -------------------------------


@app.route("/")
def index():
    user_id = session.get("user_id")
    if user_id:
        user = User.query.filter_by(id=user_id).first()
        if not user:
            logging.info(f"No user exists with ID {user_id}, logging out...")
            return redirect(url_for("logout"))
        return render_template("index.html", user=user.github_login)
    return render_template("index.html")


@app.route("/add-term/<template>")
@verify_logged_in
def add_term(template):
    message = ""
    if request.args.get("add"):
        user_id = session.get("user_id")
        message = add_to_template(user_id, template, request.args)
    return build_template(template, message=message)


@app.route("/browse")
def browse_obi():
    return render_tree("obi", None)


@app.route("/browse/<term_id>", methods=["GET", "POST"])
def browse_obi_at(term_id):
    message = ""
    if request.method == "POST":
        term_id = request.form.get("term")
        if not term_id:
            abort(500, "A term ID was not specified")
        # Add term to user's list
        user_id = session.get("user_id")
        exports = Export.query.filter_by(user_id=user_id)
        for e in exports:
            if e.term_id == term_id:
                message = build_message(
                    "warning",
                    "This term already exists in your export! Click 'Export' to view all export terms."
                )
                return render_tree("obi", term_id, message=message)
        e = Export(user_id, term_id)
        db_session.add(e)
        db_session.commit()
        message = build_message("success", "Term added to export! Click 'Export' to view all export terms.")
    return render_tree("obi", term_id, message=message)


@app.route("/export")
@verify_logged_in
def show_export():
    remove_term = request.args.get("remove")
    # Get the terms to display
    user_id = session.get("user_id")
    exports = Export.query.filter_by(user_id=user_id)
    terms = []
    for e in exports:
        if not e.term_id:
            logging.info("Missing term_id, removing export entry")
            db_session.delete(e)
            db_session.commit()
        elif e.term_id == remove_term:
            logging.info("Removing " + remove_term)
            db_session.delete(e)
            db_session.commit()
        else:
            terms.append(e.term_id)
    logging.info(terms)
    if not terms:
        return render_template("base.html", default="There are no terms to export.", user=True)
    terms = sorted(terms)

    # Get annotation properties from OBI
    obi_db = os.path.join(DATABASE_DIR, "obi.db")
    if not os.path.exists(obi_db):
        abort(400, "build/obi.db must exist in DROID directory for exporting")
    with sqlite3.connect(obi_db) as conn:
        cur = conn.cursor()
        aps = get_annotation_properties(cur)
        aps.update({"CURIE": "ontology ID", "rdfs:label": "label", "rdfs:subClassOf": "parent class", "owl:equivalentClass": "equivalent class", "owl:disjointWith": "disjoint class"})
        cur.close()
    with sqlite3.connect(obi_db) as conn:
        # TODO - make display configurable, display as label, IRI, or CURIE
        export_table = export.export_terms(conn, terms, aps.keys(), "tsv", default_value_format="label")

    # Only include headers with values
    f = StringIO(export_table)
    reader = csv.DictReader(f, delimiter="\t")
    headers = set()
    rows = []
    for row in reader:
        new_itm = {}
        for k, v in row.items():
            if v:
                ap_label = aps[k]
                new_itm[ap_label] = v
                headers.add(ap_label)
        rows.append(new_itm)

    # Sort headers alphabetically
    headers = sorted(headers)
    # Place ID first then label
    headers.remove("label")
    headers.insert(0, "label")
    headers.remove("ontology ID")
    headers.insert(0, "ontology ID")

    rows_fixed = []
    for row in rows:
        new_row = []
        term_id = None
        for h in headers:
            if h == "ontology ID":
                term_id = row[h]
            new_row.append(row.get(h, ""))
        new_row.insert(0, f'<a href="export?remove={term_id}">x</a>')
        rows_fixed.append(new_row)
    headers.insert(0, "")

    export_fmt = request.args.get("format")
    if export_fmt:
        fw = StringIO()
        sep = "\t"
        mt = "text/tab-separated-values"
        if export_fmt == "csv":
            sep = ","
            mt = "text/comma-separated-values"
        elif export_fmt != "tsv":
            abort(400, "Not a valid export format: " + export_fmt)
        writer = csv.DictWriter(fw, delimiter=sep, lineterminator="\n", fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
        return Response(fw.getvalue(), mimetype=mt)

    return render_template("table.html", headers=headers, rows=rows_fixed, export=True, user=True)


@app.route("/import/<ns>")
def browse_import(ns):
    return render_tree(ns, None, is_import=True)


@app.route("/import/<ns>/<term_id>")
def browse_import_at(ns, term_id):
    message = ""
    if request.args.get("add"):
        user_id = session.get("user_id")
        message = add_to_import(user_id, ns, term_id, request.args)
    return render_tree(ns, term_id, message=message, is_import=True)


@app.route("/search")
def search():
    text = request.args.get("text", "")
    ns = request.args.get("db")
    if not ns:
        abort(400, "A db parameter is required for search")
    db = os.path.join(DATABASE_DIR, ns + ".db")
    if not os.path.exists(db):
        abort(500, f"A database for {ns} does not exist at {db}")
    conn = sqlite3.connect(db)
    return gizmos.search.search(conn, text, limit=30)


@app.route("/submit")
@verify_logged_in
def submit():
    user_id = session["user_id"]
    if request.args.get("submit", ""):
        user = User.query.filter_by(id=user_id).first()
        inst_token = get_installation_token()
        repo = get_repo(inst_token)

        # Create a new branch (github login + date)
        now = date.today().strftime("%Y-%m-%d")
        branch_name = f"{user.github_login}-{now}"

        # Check if this branch already exists
        try:
            this_branch = repo.get_branch(branch=branch_name)
        except GithubException:
            this_branch = None

        if this_branch:
            # Add the time to the branch name
            now = datetime.now().strftime("%Y-%m-%d-%H%M")
            branch_name = f"{user.github_login}-{now}"

        # Get the base branch to branch off of
        try:
            base = repo.get_branch(branch=OBI_BASE_BRANCH)
        except GithubException:
            abort(500, f"'{OBI_BASE_BRANCH} does not exist in repo {OBI_REPO}")
        logging.info(f"Creating branch {branch_name} from {OBI_BASE_BRANCH}")
        repo.create_git_ref(ref="refs/heads/" + branch_name, sha=base.commit.sha)

        # Programmatically commit changes to the files
        updated_files = commit_changes(user_id, repo, branch_name)

        # Create a new pull request
        body = ["Update files:", ""]
        for uf in updated_files:
            body.append("- " + uf)

        # Switch to user access token for PR (app can't create PRs)
        try:
            repo = get_repo(user.access_token)
        except GithubException as e:
            err = (
                "Unable to create a new pull request.\nCause: "
                + str(e)
                + f"\nPlease go to https://github.com/{OBI_REPO}/compare/master...{branch_name}"
                + " to manually create this PR."
            )
            abort(500, err)
        title = request.args.get("prName") or branch_name
        try:
            pr = repo.create_pull(
                title=title, body="\n".join(body), head=branch_name, base=OBI_BASE_BRANCH
            )
        except GithubException as e:
            err = (
                "Unable to create a new pull request.\nCause: "
                + str(e)
                + f"\nPlease go to https://github.com/{OBI_REPO}/compare/master...{branch_name}"
                + " to manually create this PR."
            )
            abort(500, err)

        html = f'<a href="https://github.com/{OBI_REPO}/pull/{pr.number}">Go to pull request</a>'
        return render_template("base.html", default=html, user=True)

    message = ""
    discard_file = request.args.get("discard")
    if discard_file:
        changed_file = os.path.join("build", str(user_id), discard_file + ".tsv")
        if not os.path.exists(changed_file):
            abort(500, f"Cannot find changed file: {discard_file}.tsv")
        os.remove(changed_file)
        change = Change.query.filter_by(user_id=user_id, file=discard_file + ".tsv").first()
        if change:
            db_session.delete(change)
            db_session.commit()
        else:
            logging.warning(f"A changed file for {discard_file}.tsv exists, but is not recorded.")
        message = build_message("success", f"Sucessfully removed changes to {discard_file}.tsv!")

    # Display a list of changed files with option to submit a new PR
    changed_files = get_changed_files(user_id)
    fname_paths = []
    for cf in changed_files:
        fname = os.path.splitext(os.path.basename(cf))[0]
        fname_paths.append({"name": fname, "path": cf})
    return render_template("submit.html", changes=fname_paths, message=message, user=True)


def get_annotation_properties(cur, labels=True):
    cur.execute(
        """SELECT DISTINCT s2.stanza FROM statements s1
        JOIN statements s2 ON s1.predicate = s2.stanza
        WHERE s1.value IS NOT NULL"""
    )
    if not labels:
        return [x[0] for x in cur.fetchall() if not (
            x[0].startswith("dct:")
            or x[0].startswith("foaf:")
            or x[0].startswith("owl:")
            or x[0].startswith("<")
            or x[0] == "rdfs:label"
        )]
    aps = {}
    for res in cur.fetchall():
        ap_id = res[0]
        # Skip some ontology-level APs, as well as label which we add later
        if (
            ap_id.startswith("dct:")
            or ap_id.startswith("foaf:")
            or ap_id.startswith("owl:")
            or ap_id.startswith("<")
            or ap_id == "rdfs:label"
        ):
            continue
        cur.execute(
            "SELECT value FROM statements WHERE stanza = ? AND predicate = 'rdfs:label' ORDER BY value",
            (ap_id,),
        )
        res = cur.fetchone()
        if res:
            aps[ap_id] = res[0]
        else:
            aps[ap_id] = ap_id
    return aps


@app.route("/update")
@verify_logged_in
def update():
    user_id = session.get("user_id")
    if request.args.get("add"):
        args = request.args
        template = args.get("template")
        term_id = unquote(args.get("ontology-ID"))
        message = add_to_template(user_id, template, args, exists=True)
        return render_tree("obi", term_id, message=message, from_update=True)

    term_id = unquote(request.args.get("term"))
    if not term_id:
        abort(400, "A term is required in the parameters.")
    obi_db = os.path.join(DATABASE_DIR, "obi.db")
    if not os.path.exists(obi_db):
        abort(400, "build/obi.db must exist in DROID directory for term updating")
    message = ""

    # Find the location of this term
    fname, line = locate_term(term_id)

    if fname == "build/obi-edit.db":
        obi_db = os.path.join(DATABASE_DIR, "obi.db")
        if not os.path.exists(obi_db):
            abort(400, "build/obi.db must exist in DROID directory for term updating")
        with sqlite3.connect(obi_db) as conn:
            # Get the annotation properties that we want
            cur = conn.cursor()
            aps = get_annotation_properties(cur)
            # Get the term label
            cur.execute(
                "SELECT value FROM statements WHERE stanza = ? AND predicate = 'rdfs:label'",
                (term_id,),
            )
            res = cur.fetchone()
            label = None
            if res:
                label = res[0]
            # Close the cursor to unlock the database
            cur.close()
            # Export annotations
            annotations = export.export_terms(
                conn, [term_id], sorted(aps.keys()), "tsv", default_value_format="label"
            )
            # Export logic
            logic = export.export_terms(
                conn,
                [term_id],
                ["rdfs:subClassOf", "owl:equivalentClass"],
                "tsv",
                default_value_format="label",
                no_headers=True,
            )
        ann_headers = annotations.split("\n")[0].split("\t")
        ann_details = annotations.split("\n")[1].split("\t")
        logic_details = logic.strip().split("\t")

        metadata_html = []
        # Add the ontology ID element
        field = build_form_field("text", "ontology ID", None, True, value=term_id)
        if field:
            metadata_html.extend(field)
        # Add the label element
        field = build_form_field("text", "label", None, True, value=label)
        if field:
            metadata_html.extend(field)
        # Add the rest of the annotations
        i = 0
        while i < len(ann_headers):
            header = ann_headers[i]
            detail = ann_details[i]
            ap_label = aps[header]
            i += 1
            if header.startswith("<"):
                continue
            field = build_form_field("text", ap_label, None, False, value=detail)
            if not field:
                logging.warning("Could not build field for property: " + ap_label)
                continue
            metadata_html.extend(field)

        logic_html = []
        # TODO: these are not including anon classes, wait for thick triples?
        # Maybe add subclass
        if len(logic_details) == 1:
            field = build_form_field("search", "parent class", None, False, value=logic_details[0])
            if not field:
                logging.warning("Could not build field for parent class")
            else:
                logic_html.extend(field)
        # Maybe add equivalent class
        if len(logic_details) == 2:
            field = build_form_field(
                "search", "equivalent class", None, False, value=logic_details[1]
            )
            if not field:
                logging.warning("Could not build field for equivalent class")
            else:
                logic_html.extend(field)

        if label and " " in label:
            # Encase in single quotes when label has a space
            label = f"'{label}'"
        return render_template(
            "edit-term.html",
            title=f"Update " + label or term_id,
            metadata="\n".join(metadata_html),
            logic="\n".join(logic_html),
            message=message,
            user=True,
        )

    elif fname.startswith(TEMPLATES_DIR):
        # Get the template name & its fields
        template = os.path.splitext(os.path.basename(fname))[0]
        metadata_fields, logic_fields = get_template_fields(template)

        # Get the current values for this term from the template
        with open(fname, "r") as f:
            reader = csv.DictReader(f, delimiter="\t")
            row = next((x for i, x in enumerate(reader) if i == line - 2), None)

        if not row:
            abort(500, f"Unable to find row {line} in " + fname)

        metadata_values = {}
        for field in metadata_fields.keys():
            metadata_values[field] = row.get(field, "")

        logic_values = {}
        for field in logic_fields.keys():
            logic_values[field] = row.get(field, "")

        hidden = {"template": template}
        metadata_html = build_form_html(metadata_fields, values=metadata_values, hidden=hidden)
        logic_html = build_form_html(logic_fields, values=logic_values)

        # Term is in a template file - we will get the details and create the form
        return render_template(
            "edit-term.html",
            title=f"Update " + term_id,
            metadata="\n".join(metadata_html),
            logic="\n".join(logic_html),
            message=message,
            user=True,
        )

    # TODO: Term is in an import file - we give option to update parent or delete
    # We also need to determine how to edit an import term that is a specified descendant/ancestor
    message = build_message("warning", "Unable to edit import terms at this time.")
    return render_tree("obi", term_id, message=message, from_update=True)


@app.route("/submit/<name>")
@verify_logged_in
def view_diff(name):
    # TODO - eventually add support for obi-edit diff here
    user_id = session.get("user_id")
    source_dir = TEMPLATES_DIR
    dir_display = "src/ontology/templates/"
    if name.endswith("_terms"):
        source_dir = IMPORTS_DIR
        dir_display = "src/ontology/imports/"
    source_file = open(os.path.join(source_dir, name + ".tsv"))
    changed_file = open(os.path.join("build", str(user_id), name + ".tsv"))
    diff = difflib.ndiff(source_file.readlines(), changed_file.readlines())
    source_file.close()
    changed_file.close()
    headers = []
    rows = []
    if diff:
        headers = next(diff).strip().split("\t")
        headers.insert(0, "")
        rows = []
        for line in diff:
            if not line.startswith(" ") and not line.startswith("?"):
                change = line[:2].strip()
                contents = line[2:].strip().split("\t")
                contents.insert(0, change)
                if len(contents) < len(headers):
                    diff_len = len(headers) - len(contents)
                    i = 0
                    while i < diff_len:
                        i += 1
                        contents.append("")
                rows.append(contents)
    return render_template(
        "table.html",
        filename=os.path.join(dir_display, name + ".tsv"),
        headers=headers,
        rows=rows,
        user=True,
    )


# ------------------------------- GITHUB APP ROUTES -------------------------------


@app.route("/github_callback")
def github_callback():
    def fetch_access_token(args):
        temporary_code = args.get("code")
        params = {
            "client_id": GITHUB_CLIENT_ID,
            "client_secret": GITHUB_CLIENT_SECRET,
            "code": temporary_code,
            "state": GITHUB_APP_STATE,
            "redirect_uri": f"{FLASK_HOST}/github_callback",
        }

        try:
            response = github_authorize_token(params)
        except requests.HTTPError as e:
            logger.error(e)
            return None

        content = parse_qs(response.text)
        token = content.get("access_token")
        if not token:
            logger.error("Could not retrieve access token")
            return None
        token = token[0]

        token_type = content.get("token_type")
        if not token_type:
            logger.error("No token type returned")
            return None
        token_type = token_type[0]
        if token_type.casefold() != "bearer":
            logger.error("Unexpected token type retrieved: " + token_type)
            return None

        return token

    if request.args.get("state") != GITHUB_APP_STATE:
        logging.error("Received wrong state. Aborting authorization due to possible CSRF attack.")
        return redirect("/logout")

    access_token = fetch_access_token(request.args)
    next_url = request.args.get("next") or url_for("index")
    if access_token is None:
        # If we don't receive a token, just redirect (an error message has already been logged)
        return redirect(next_url)

    github_user = github_call("GET", "/user", access_token)
    user = User.query.filter_by(github_id=github_user["id"]).first()
    if user is None:
        user = User(github_user["id"])
        db_session.add(user)
    else:
        logging.info(f"Logging in existing user with ID {user.id}")

    # Update login & token, in case it has changed
    user.github_login = github_user["login"]
    user.access_token = access_token
    db_session.commit()

    # Add the user to the session
    session["user_id"] = user.id

    return redirect(next_url)


@app.route("/logout")
def logout():
    if session.get("user_id"):
        session.pop("user_id")
    return redirect(url_for("index"))


@app.route("/login")
def login():
    if session.get("user_id") is not None:
        session.pop("user_id")

    params = {
        "client_id": GITHUB_CLIENT_ID,
        "state": GITHUB_APP_STATE,
        "redirect_uri": f"{FLASK_HOST}/github_callback",
    }
    try:
        response = github_authorize(params)
        return redirect(response.url)
    except requests.HTTPError as e:
        logger.error(e)
        return redirect(url_for("logout"))


# ------------------------------- HELPER METHODS -------------------------------


def add_to_import(user_id, ns, term_id, args):
    """Add a new term to an import file based on the request args provided."""
    user_dir = "build/" + str(user_id)
    if not os.path.exists(user_dir):
        os.mkdir(user_dir)

    db = os.path.join(DATABASE_DIR, ns + ".db")
    if not os.path.exists(db):
        abort(500, f"A database for {ns} does not exist at {db}")

    with sqlite3.connect(db) as conn:
        # Get a label to display in import file
        label = ""
        cur = conn.cursor()
        cur.execute(
            "SELECT DISTINCT value FROM statements WHERE stanza = ? AND predicate = 'rdfs:label'",
            (term_id,),
        )
        res = cur.fetchone()
        if res:
            label = res[0]

        # Check for an override parent - this must be a label and must exist in OBI
        parent = args.get("parent", "")
        parent_label = ""
        if parent:
            obi_db = os.path.join(DATABASE_DIR, "obi.db")
            if not os.path.exists(obi_db):
                abort(500, f"A database for obi does not exist at {obi_db}")
            with sqlite3.connect(obi_db) as obi_conn:
                obi_cur = obi_conn.cursor()
                obi_cur.execute(
                    """SELECT DISTINCT stanza FROM statements
                       WHERE predicate = 'rdfs:label' AND value = ?""",
                    (parent,),
                )
                res = obi_cur.fetchone()
                if res:
                    parent_label = res[0]

    if parent and not parent_label:
        return build_message(
            "danger",
            f"'{label}' ({term_id}) could not be added; parent '{parent}' does not exist in OBI.",
        )

    # Check for related entities
    related = args.get("relatedEntities", "")
    if related:
        if related.startswith("["):
            related = related[1:-1].replace('"', "")
    if not parent and "ancestors" not in related:
        # If no parent was provided, we need to include ancestors in order to place the term
        related += " ancestors"
        related = related.lstrip()

    # If a user import file exists, the user has already updated this file
    # Otherwise use the base file and write a new user import file
    base_import_file = os.path.join(IMPORTS_DIR, ns + "_terms.tsv")
    user_import_file = f"{user_dir}/{ns}_terms.tsv"
    import_file = base_import_file
    if os.path.exists(user_import_file):
        import_file = user_import_file

    # Get rows while checking if this term already exists
    rows = []
    with open(import_file, "r") as f:
        exists = False
        reader = csv.DictReader(f, delimiter="\t")
        headers = reader.fieldnames
        for row in reader:
            existing_id = row["ID"]
            if term_id == existing_id:
                exists = True
                break
            rows.append(row)
    if exists:
        return build_message("warning", f"'{label}' ({term_id}) already exists in {db} import.")

    rows.append(
        {
            "Source": ns,
            "ID": term_id,
            "Label": label,
            "Parent ID": parent,
            "Parent Label": parent_label,
            "Related": related,
        }
    )

    # Always write to the user's version of the import file
    with open(user_import_file, "w") as f:
        logging.info(headers)
        writer = csv.DictWriter(f, delimiter="\t", lineterminator="\n", fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)

    # Log the change so we know what was updated (if it's already been logged, do nothing)
    change = Change.query.filter_by(user_id=user_id, file=f"{ns}_terms.tsv").first()
    if not change:
        change = Change(user_id, f"{ns}_terms.tsv", "import")
        db_session.add(change)
        db_session.commit()

    return build_message("success", f"'{label}' ({term_id}) added to {db} import!")


def add_to_template(user_id, template, args, exists=False):
    """Add a new term to the given template based on the request args provided."""
    user_dir = "build/" + str(user_id)
    if not os.path.exists(user_dir):
        os.mkdir(user_dir)

    term_id = args["ontology-ID"]
    term_label = args["label"]

    # If a user template file exists, the user has already updated this file
    # Otherwise use the base file and write a new user template file
    base_template_file = os.path.join(TEMPLATES_DIR, template + ".tsv")
    user_template_file = f"{user_dir}/{template}.tsv"
    template_file = base_template_file
    if os.path.exists(user_template_file):
        template_file = user_template_file

    rows = []
    with open(template_file, "r") as f:
        reader = csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE, escapechar='"')
        headers = reader.fieldnames
        for row in reader:
            if row["ontology ID"] == term_id:
                if exists:
                    # Skip row
                    continue
                else:
                    existing_label = row["label"]
                    return build_message(
                        "danger",
                        f"Cannot add '{term_label}' ({term_id}) to {template} template; "
                        + f"{term_id} already exists in template as '{existing_label}'.",
                    )
            rows.append(row)

    add_row = {}
    bad = []
    for header, value in args.items():
        header = header.replace("-", " ")
        if header == "template":
            continue
        if header not in headers:
            bad.append(header)
            continue
        add_row[header] = value
    rows.append(add_row)

    logging.warning(f"Found {len(bad)} incorrect headers: " + ", ".join(bad))

    # Log the change so we know what was updated (if it's already been logged, do nothing)
    change = Change.query.filter_by(user_id=user_id, file=template + ".tsv").first()
    if not change:
        change = Change(user_id, template + ".tsv", "template")
        db_session.add(change)
        db_session.commit()

    # Sort rows by ID
    robot_template = rows.pop(0)
    rows.sort(key=lambda x: x["ontology ID"])
    rows.insert(0, robot_template)

    # Always write to the user's version of the template file
    with open(user_template_file, "w") as f:
        writer = csv.DictWriter(
            f,
            delimiter="\t",
            lineterminator="\n",
            quoting=csv.QUOTE_NONE,
            escapechar='"',
            fieldnames=headers,
        )
        writer.writeheader()
        writer.writerows(rows)
    if exists:
        verb = "updated"
    else:
        verb = "added"
    return build_message(
        "success", f"Successfully {verb} '{term_label}' ({term_id}) in {template} template!"
    )


def build_form_field(input_type, column, help_msg, required, value=None):
    """Return an HTML form field for a template field."""
    if required:
        display = column + " *"
    else:
        display = column

    html = [
        '<div class="row mb-3">',
        f'\t<label class="col-sm-2 col-form-label">{display}</label>',
        '\t<div class="col-sm-10">',
    ]

    field_name = column.replace(" ", "-")

    value_html = ""
    if value:
        value_html = f' value="{value}"'
    if not value:
        value = ""

    if input_type == "text":
        if required:
            html.append(
                f'\t\t<input type="text" class="form-control" name="{field_name}" required{value_html}>'
            )
            html.append('\t\t<div class="invalid-feedback">')
            html.append(f"\t\t\t{column} is required")
            html.append("</div>")
        else:
            html.append(
                f'\t\t<input type="text" class="form-control" name="{field_name}"{value_html}>'
            )

    elif input_type == "textarea":
        if required:
            html.append(
                f'\t\t<textarea class="form-control" name="{field_name}" rows="3" required>{value}</textarea>'
            )
            html.append('\t\t<div class="invalid-feedback">')
            html.append(f"\t\t\t{column} is required")
            html.append("</div>")
        else:
            html.append(
                f'\t\t<textarea class="form-control" name="{field_name}" rows="3">{value}</textarea>'
            )

    elif input_type == "search":
        if required:
            html.append(
                f'<input type="text" class="searc form-control" name="{field_name}" '
                + f'id="{field_name}-typeahead-obi" required{value_html}>'
            )
            html.append('\t\t<div class="invalid-feedback">')
            html.append(f"\t\t\t{column} is required")
            html.append("</div>")
        else:
            html.append(
                f'<input type="text" class="typeahead form-control" name="{field_name}" '
                + f'id="{field_name}-typeahead-obi"{value_html}>'
            )

    elif input_type.startswith("select"):
        selects = input_type.split("(", 1)[1].rstrip(")").split(", ")
        html.append(f'\t\t<select class="form-select" name="{field_name}">')
        for s in selects:
            if value and s == value:
                html.append(f'\t\t\t<option value="{s}" selected>{s}</option>')
            else:
                html.append(f'\t\t\t<option value="{s}">{s}</option>')
        html.append("\t\t</select>")

    else:
        return None

    if help_msg:
        html.append(f'\t\t<div class="form-text">{help_msg}</div>')
    html.append("\t</div>")
    html.append("</div>")
    return html


def build_form_html(fields, values=None, hidden=None):
    html = []
    if hidden:
        for name, value in hidden.items():
            html.append(f'<input type="hidden" name="{name}" value="{value}">')
    for field, details in fields.items():
        input_type = details["type"]
        value = None
        if values:
            value = values[field]
        form_field = build_form_field(
            input_type, field, details["help"], details["required"], value=value
        )
        if not form_field:
            abort(500, f"Unknown input type '{input_type}' for column '{field}'")
        html.extend(form_field)
    return html


def build_message(message_type, message_content):
    """Return a pop-up message to display at the top of the page."""
    message = f'<div class="alert alert-{message_type} alert-dismissible fade show" role="alert">\n'
    message += f'<p class="mb-0">{message_content}</p>\n'
    message += '<button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>\n'
    message += "</div>\n"
    return message


def get_template_fields(template):
    metadata_fields = {}
    logic_fields = {}
    with open("src/field.tsv", "r") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for row in reader:
            tables = row.get("table", "").split("|")
            if (not tables or template not in tables) and tables[0] != "*":
                continue
            column = row.get("column")
            if not column:
                continue
            category = row.get("category")
            if category == "metadata":
                metadata_fields[column] = {
                    "type": row.get("input type").strip(),
                    "help": row.get("help", "").strip(),
                    "required": bool(row.get("required", "false").strip()),
                }
            else:
                logic_fields[column] = {
                    "type": row.get("input type").strip(),
                    "help": row.get("help", "").strip(),
                    "required": bool(row.get("required", "false").strip()),
                }
    return metadata_fields, logic_fields


def build_template(template, message=""):
    """Build an HTML form template from the template fields."""
    metadata_fields, logic_fields = get_template_fields(template)

    metadata_html = build_form_html(metadata_fields)
    logic_html = build_form_html(logic_fields)

    return render_template(
        "edit-term.html",
        title=f"New '{template}' Term",
        metadata="\n".join(metadata_html),
        logic="\n".join(logic_html),
        message=message,
        user=True,
    )


def commit_changes(user_id, repo, branch_name):
    """Commit all logged changes to a branch in a repository."""
    changes = Change.query.filter_by(user_id=user_id)
    updated_files = []
    for c in changes:
        if c.file_type == "import":
            repo_path = "src/ontology/imports/" + c.file
        elif c.file_type == "template":
            repo_path = "src/ontology/templates/" + c.file
        else:
            continue
        with open(f"build/{user_id}/{c.file}", "r") as f:
            content = f.read()

        logging.info("Updating " + repo_path)
        cur_file = repo.get_contents(repo_path, ref="refs/heads/" + OBI_BASE_BRANCH)
        repo.update_file(
            path=repo_path,
            message="Update " + c.file,
            content=content,
            sha=cur_file.sha,
            branch=branch_name,
        )

        # Remove record from table
        db_session.delete(c)
        db_session.commit()
        updated_files.append(repo_path)

        # Delete file from user dir
        os.remove(f"build/{user_id}/{c.file}")
    return updated_files


def get_changed_files(user_id):
    """Get all changed files for a user from the 'changes' table."""
    changes = Change.query.filter_by(user_id=user_id)
    if not changes:
        return []

    changed_files = []
    for c in changes:
        if c.file_type == "import":
            changed_files.append("src/ontology/imports/" + c.file)
        elif c.file_type == "template":
            changed_files.append("src/ontology/templates/" + c.file)
    return changed_files


def get_installation_token():
    """Generate a GitHub installation token which can be used for read/write access to the repo."""
    payload = {
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int((datetime.now(timezone.utc)).timestamp()) + (10 * 60),
        "iss": GITHUB_APP_ID,
    }

    # Create the json web key
    with open(GITHUB_PRIVATE_KEY, "rb") as f:
        secret = f.read()
    jwk = jwt.encode(payload, secret, algorithm="RS256")

    # Retreived the installation ID for this user for this app
    r = requests.get(
        "https://api.github.com/app/installations",
        headers={"Authorization": "Bearer " + jwk, "Accept": "application/vnd.github.v3+json"},
    )
    data = json.loads(r.content)
    if not data:
        abort(500, "Unable to retrieve GitHub installation ID")
    try:
        data = data[0]
    except KeyError:
        pass

    installation_id = data.get("id")
    if not installation_id:
        msg = data.get("message", "cause unknown")
        abort(500, "Unable to retrieve GitHub installation ID: " + msg)

    # Use the installation ID to retrieve the installation token
    r = requests.post(
        f"https://api.github.com/app/installations/{installation_id}/access_tokens",
        headers={"Authorization": "Bearer " + jwk, "Accept": "application/vnd.github.v3+json"},
    )
    data = json.loads(r.content)
    token = data.get("token")
    if not token:
        msg = data.get("message", "cause unknown")
        abort(500, "Unable to retrieve GitHub installation token: " + msg)
    return token


def get_repo(token):
    """Create the Github object for the target repository."""
    logging.info(token)
    api = Github(token)
    repo = api.get_repo(OBI_REPO)
    return repo


def github_call(method, endpoint, access_token, params=None):
    """
    Call the GitHub REST API at the given endpoint using the given method and passing the given
    params.
    """
    if not params:
        params = {}
    method = method.casefold()
    if method not in ["get", "post", "put"]:
        logger.error(f"Unsupported API method: {method}")
        return {}

    api_headers = GITHUB_DEFAULT_API_HEADERS
    api_headers["Authorization"] = f"token {access_token}"
    if not endpoint.startswith("/"):
        endpoint = "/" + endpoint

    fargs = {"url": GITHUB_API_URL + endpoint, "headers": api_headers, "json": params}
    if method == "get":
        # GET parameters must go in URL - https://developer.github.com/v3/#parameters
        if len(params) > 0:
            fargs["url"] = fargs["url"] + "?" + urlencode(params)
        response = requests.get(**fargs)
    elif method == "post":
        response = requests.post(**fargs)
    elif method == "put":
        response = requests.put(**fargs)
    else:
        logger.error("Unknown response method: " + method)
        return {}

    if not response.ok:
        if response.status_code == 403:
            logger.error(
                f"Received 403 Forbidden from {method} request to endpoint {endpoint}"
                "with params {params}"
            )
        response.raise_for_status()
    return response.json()


def github_authorize(params):
    response = requests.get(GITHUB_OAUTH_URL + "/authorize", params)
    if not response.ok:
        response.raise_for_status()
    return response


def github_authorize_token(params):
    response = requests.post(GITHUB_OAUTH_URL + "/access_token", params)
    if not response.ok:
        response.raise_for_status()
    return response


def locate_term(term_id):
    # TODO - as we move code into OBI, replace this with the actual locate script
    for f in os.listdir(TEMPLATES_DIR):
        if not f.endswith(".tsv"):
            continue
        fname = os.path.join(TEMPLATES_DIR, f)
        with open(fname, "r") as fr:
            reader = csv.DictReader(fr, delimiter="\t")
            i = 1
            for row in reader:
                i += 1
                if term_id == row.get("ontology ID"):
                    return fname, i
    for f in os.listdir(IMPORTS_DIR):
        if not f.endswith(".tsv"):
            continue
        fname = os.path.join(IMPORTS_DIR, f)
        i = 1
        with open(fname, "r") as fr:
            reader = csv.DictReader(fr, delimiter="\t")
            for row in reader:
                i += 1
                if row.get("ID") == term_id:
                    return fname, i
    edit_db = os.path.join(DATABASE_DIR, "obi-edit.db")
    if not os.path.exists(edit_db):
        abort(400, "build/obi-edit.db must exist in DROID directory for term updating")
    with sqlite3.connect(edit_db) as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM statements WHERE stanza = ?", (term_id,))
        res = cur.fetchone()
        if res:
            return "build/obi-edit.db", None
    return None, None


def render_tree(ns, term_id, message="", is_import=False, from_update=False):
    """Render the HTML tree for a given term (or top level, when term_id is None)."""
    db = os.path.join(DATABASE_DIR, ns + ".db")
    if not os.path.exists(db):
        abort(500, f"A database for {ns} does not exist at {db}")
    conn = sqlite3.connect(db)

    base = "browse"
    if is_import:
        base = ns
    if not term_id or from_update:
        href = base + "/{curie}"
    else:
        href = "./{curie}"
    if ns != "obi" and ns not in IMPORTS:
        abort(400, description="Unknown ontology: " + ns)

    title = IMPORTS.get(ns, "Ontology for Biomedical Investigations")

    content = gizmos.tree.tree(conn, ns, term_id, title=title, href=href, standalone=False)
    template_name = "tree.html"
    if is_import:
        template_name = "import.html"
    return render_template(
        template_name,
        ns=ns,
        tree=content,
        message=message,
        user=session.get("user_id"),
    )


# ------------------------------- SQLALCHEMY CLASSES -------------------------------


class Export(Base):
    """
    Saved information for the terms within export lists.
    """

    __tablename__ = "exports"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    term_id = Column(String(255))

    def __init__(self, user_id, term_id):
        self.user_id = user_id
        self.term_id = term_id


class Change(Base):
    """
    Saved information on changed files. This data is erased after submitting a new PR.
    """

    __tablename__ = "changes"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    file = Column(String(255))
    file_type = Column(String(255))

    def __init__(self, user_id, file, file_type):
        self.user_id = user_id
        self.file = file
        self.file_type = file_type


class List(Base):
    """
    Saved information for export lists for users.
    """

    __tablename__ = "lists"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    name = Column(String(255))

    def __init__(self, user_id, name):
        self.user_id = user_id
        self.name = name


class User(Base):
    """
    Saved information for users that have been authenticated to the metadata editor.
    Note that this table preserves historical data (data is not deleted on logout)
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    github_id = Column(Integer)
    github_login = Column(String(255))
    access_token = Column(String(255))

    def __init__(self, github_id):
        self.github_id = github_id
