# TODO: Below we are temporarily using debian:bullseye instead of obolibrary/odkfull because
# there were some problems compiling the binary on this platform. Before merging to the main
# branch we need to get this to work and switch back to obolibrary/odkfull.

# FROM obolibrary/odkfull
FROM debian:bullseye

# install some more packages from apt
ENV TERM=xterm-256color
RUN apt-get update
# TODO: Not all of these will need to be explicitly installed once we move to obolibrary/odkfull.
RUN apt-get install -y aha curl git python3-pip unzip sqlite3 libpq-dev postgresql-client

# install Rust
WORKDIR /tools
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs > rust.sh
RUN sh rust.sh -y
ENV PATH="/root/.cargo/bin:$PATH"

# install wiring.py using wiring.rs bindings
WORKDIR /tools
RUN git clone https://github.com/ontodev/wiring.py.git
WORKDIR /tools/wiring.py
RUN git clone https://github.com/ontodev/wiring.rs.git
RUN mv python_module.rs wiring.rs/src/
RUN rm wiring.rs/Cargo.toml
RUN mv Cargo.toml wiring.rs/
RUN echo "mod python_module;" >> wiring.rs/src/lib.rs
RUN pip install -U pip maturin
RUN maturin build --release --out dist -m wiring.rs/Cargo.toml
WORKDIR /tools/wiring.py/dist
RUN pip install wiring_rs-0.1.1-cp36-abi3-manylinux_2_28_x86_64.whl

# TODO: Remove the commented-out code below that I was using during dev.
# The commented-out code below is useful for making ad hoc changes to the nanobot, sprocket, and
# gadget repos and testing them out in DROID. Otherwise you would have to push those changes
# first so that ontodev_demo can grab them from GitHub.

# install nanobot
WORKDIR /tools
RUN git clone -b postgres-support https://github.com/ontodev/nanobot.git
WORKDIR /tools/nanobot
## TODO: Remove this copy later that we use to copy over files from the local filesystem (dev only).
#COPY nanobot/nanobot/*.py nanobot/
RUN pip install -e .

# install sprocket
WORKDIR /tools
RUN git clone -b postgres-support https://github.com/ontodev/sprocket.git
WORKDIR /tools/sprocket
## TODO: Remove this copy later that we use to copy over files from the local filesystem (dev only).
#COPY sprocket/sprocket/*.py sprocket/
RUN pip install -e .

# install gadget
WORKDIR /tools
RUN git clone -b postgres-support https://github.com/ontodev/gadget.git
WORKDIR /tools/gadget
## TODO: Remove this copy later that we use to copy over files from the local filesystem (dev only).
#COPY gadget/gadget/*.py gadget/
RUN pip install -e .

# install project Python requirements
WORKDIR /tools
COPY requirements.txt /tools/obi-requirements.txt
COPY run.py /tools/
COPY src src
RUN pip install -r obi-requirements.txt

# restore WORKDIR
WORKDIR /tools
