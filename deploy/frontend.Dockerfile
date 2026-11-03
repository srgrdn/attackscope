FROM node:24-alpine@sha256:8a32c8cf649a49915a66e81e7a609223c708d0adabf288ee3f4077d765542f85 AS dependencies
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./

FROM dependencies AS test
RUN chown -R node:node /app
USER node
ENV HOME=/tmp
CMD ["npm", "test"]

FROM dependencies AS build
RUN npm run typecheck && npm run build

FROM nginx:stable-alpine@sha256:0e52bd054126cdc040b1276c0af347aeb02a41b9cfe305d6094767ac30e97949 AS runtime
COPY deploy/nginx.conf /etc/nginx/nginx.conf
COPY deploy/nginx-listen.conf /etc/nginx/attackscope-listen.conf
COPY --from=build /app/dist /usr/share/nginx/html
USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off;"]
