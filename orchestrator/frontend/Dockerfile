# ==============================================================================
# AI Engineering Copilot - Frontend React Multi-Stage Dockerfile
# Stage 1: Build static assets using Node.js
# Stage 2: Serve via high-performance, lightweight Nginx Alpine
# ==============================================================================

# Stage 1: Build
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies
COPY package.json package-lock.json ./
RUN npm ci --silent || npm install --silent

# Copy frontend source files
COPY public/ ./public/
COPY src/ ./src/

# Build optimized production bundle
RUN npm run build

# Stage 2: Production Nginx Server
FROM nginx:1.25-alpine

# Remove default nginx website
RUN rm -rf /usr/share/nginx/html/*

# Copy custom Nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy build artifacts from builder stage
COPY --from=builder /app/build /usr/share/nginx/html

# Expose HTTP port
EXPOSE 80

# Healthcheck
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost/ || exit 1

# Start Nginx
CMD ["nginx", "-g", "daemon off;"]
