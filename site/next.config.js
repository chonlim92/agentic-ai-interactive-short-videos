const path = require("path");
require("dotenv").config({ path: path.resolve(__dirname, "../config/.env") });

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  experimental: {
    staleTimes: { dynamic: 0, static: 0 },
  },
  webpack: (config) => {
    // Exclude data/store.json from file watching to prevent HMR on DB writes
    config.watchOptions = {
      ...config.watchOptions,
      ignored: /[/\\](node_modules|data[/\\]store\.json)/,
    };
    return config;
  },
};

module.exports = nextConfig;
