# Layered image: add POS Prime to the existing custom ERPNext image WITHOUT
# rebuilding the whole bench. This pins the exact frappe/erpnext/india_compliance/
# express_tally versions already running (no version drift on live data) and just
# adds the pos_prime app.
#
# Two stages:
#   1) frontend  - compiles the Vue SPA from frontend/src with `yarn build` so the
#                  bundle is ALWAYS regenerated from source on every image build.
#                  (No need to run `yarn build` on the host or commit the bundle.)
#   2) final     - layers the app (with the freshly built SPA) onto the base image.
#
# Build:
#   docker build -t frappe-erpnext-custom:v16.18.3-pos -f docker/pos_prime_layer/Dockerfile docker/pos_prime_layer

# BASE_IMAGE is global (declared before the first FROM) so it can be referenced
# in the final stage's FROM line.
ARG BASE_IMAGE=frappe-erpnext-custom:v16.18.3-local

# ---------------------------------------------------------------------------
# Stage 1: build the Vue SPA from source -> pos_prime/public/frontend
# ---------------------------------------------------------------------------
# node 22 matches the host toolchain that produced the committed lockfile.
FROM node:22-bookworm-slim AS frontend
WORKDIR /build
# Copy the whole app so vite can reach ../pos_prime/www/pos_prime.html (indexHtmlPath)
# and emit into ../pos_prime/public/frontend (frappe-ui plugin default outDir).
COPY pos_prime /build
WORKDIR /build/frontend
# yarn.lock is the source of truth; install exactly what it pins.
RUN yarn install --frozen-lockfile \
 && yarn build
# Result lands at /build/pos_prime/public/frontend (hashed JS/CSS + .vite/manifest.json).

# ---------------------------------------------------------------------------
# Stage 2: layer the app onto the running ERPNext image
# ---------------------------------------------------------------------------
FROM ${BASE_IMAGE}

USER root
COPY --chown=frappe:frappe pos_prime /home/frappe/frappe-bench/apps/pos_prime
# Overlay the freshly compiled SPA over whatever bundle shipped in the context,
# so the image always reflects the current frontend/src.
COPY --from=frontend --chown=frappe:frappe \
     /build/pos_prime/public/frontend \
     /home/frappe/frappe-bench/apps/pos_prime/pos_prime/public/frontend
# assets.json ships root-owned in the base image; bench build runs as frappe.
RUN chown -R frappe:frappe /home/frappe/frappe-bench/assets/ 2>/dev/null || true
USER frappe

WORKDIR /home/frappe/frappe-bench
# Rewrite apps.txt canonically (avoids missing-newline concatenation). This file
# is only used at image-build time — at runtime the sites volume's apps.txt wins.
RUN env/bin/pip install --no-cache-dir -e apps/pos_prime \
 && printf 'frappe\nerpnext\nindia_compliance\nexpress_tally\npos_prime\n' > sites/apps.txt \
 && bench build --app pos_prime
# nginx serves /assets from sites/assets, which the persisted sites volume points
# at bench/assets (a non-standard symlink left by an earlier hotfix). `bench build`
# only updates sites/assets, so link the app's public dir into bench/assets too,
# otherwise /assets/pos_prime/* 404s after every container recreation.
RUN ln -sfn /home/frappe/frappe-bench/apps/pos_prime/pos_prime/public \
            /home/frappe/frappe-bench/assets/pos_prime
