# Vigil dashboard for local Docker Compose: build the React app, serve it with nginx,
# and forward /api to the API container (so the browser sees one origin, no CORS needed).
# On Azure the same build is uploaded to Static Web Apps instead (see deploy.ps1).

FROM node:22-alpine AS build
WORKDIR /src
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 80
