# Frontend production image: build React app and serve with Nginx

# Build stage
FROM node:24-bookworm-slim AS build
WORKDIR /app

# Lock npm to an explicit version for deterministic CI/build behavior
RUN npm install -g npm@11.17.0

# Install dependencies deterministically
COPY package.json package-lock.json ./
RUN npm ci --legacy-peer-deps

# Copy source
COPY . ./

# Build static assets
RUN npm run build

# Runtime stage
FROM nginx:1.28.0-alpine

# Copy build output to Nginx html directory
COPY --from=build /app/dist /usr/share/nginx/html

# Add SPA-friendly Nginx config (fallback to index.html)
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Default Nginx image listens on 80; used by the proxy service
EXPOSE 80

# No custom config needed; Nginx will serve static files from /usr/share/nginx/html
# SPA fallback is provided via the copied nginx.conf.
