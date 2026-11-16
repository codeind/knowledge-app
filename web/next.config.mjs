/** Static export: `npm run build` writes plain HTML/JS to out/, which the Python API serves. */
const nextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
};

export default nextConfig;
