# nginx serves the page and forwards /api/ to the API. No build step, no framework.
FROM nginx:1.27-alpine

COPY index.html /usr/share/nginx/html/index.html
COPY default.conf.template /etc/nginx/templates/default.conf.template

# Shown on the page: change it at build time to see a rolling update.
ARG WEB_VERSION=v1
ENV WEB_VERSION=${WEB_VERSION}

EXPOSE 80
