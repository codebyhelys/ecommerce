import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  images: {
    // Fotos que o Next pode otimizar: só as do armazenamento de imagens do backend
    remotePatterns: [
      {
        protocol: "http",
        hostname: "127.0.0.1",
        port: "18333",
        pathname: "/ecommerce-media/**",
      },
    ],
    // O Next bloqueia IP local por segurança; em desenvolvimento nosso servidor de imagens é local
    dangerouslyAllowLocalIP: process.env.NODE_ENV !== "production",
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
