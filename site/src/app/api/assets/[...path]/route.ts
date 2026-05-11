import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";

/**
 * Serve static assets from the data/ directory.
 * URL pattern: /api/assets/<story-slug>/episodes/<num>/gallery/gallery_01.jpg
 *              /api/assets/<story-slug>/episodes/<num>/poster.png
 *              /api/assets/<story-slug>/episodes/<num>/final/video/episode_1.mp4
 *              /api/assets/<story-slug>/posters/ep1/poster_16_9.jpg
 *
 * Serves image and video files for security.
 */

const DATA_ROOT = path.resolve(process.cwd(), "..", "data", "stories");

const ALLOWED_EXTENSIONS = new Set([".jpg", ".jpeg", ".png", ".webp", ".mp4"]);

const MIME_TYPES: Record<string, string> = {
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".png": "image/png",
  ".webp": "image/webp",
  ".mp4": "video/mp4",
};

export async function GET(
  _request: Request,
  { params }: { params: { path: string[] } }
) {
  const segments = params.path;

  // Validate path segments (prevent directory traversal)
  for (const seg of segments) {
    if (seg === ".." || seg.includes("..") || seg.startsWith("/") || seg.includes("\\")) {
      return NextResponse.json({ error: "Invalid path" }, { status: 400 });
    }
  }

  const filePath = path.join(DATA_ROOT, ...segments);
  const ext = path.extname(filePath).toLowerCase();

  // Only serve allowed image extensions
  if (!ALLOWED_EXTENSIONS.has(ext)) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  // Ensure resolved path is within DATA_ROOT (prevent traversal)
  const resolved = path.resolve(filePath);
  if (!resolved.startsWith(path.resolve(DATA_ROOT))) {
    return NextResponse.json({ error: "Invalid path" }, { status: 400 });
  }

  if (!fs.existsSync(resolved)) {
    return NextResponse.json({ error: "Not found" }, { status: 404 });
  }

  const stat = fs.statSync(resolved);
  const contentType = MIME_TYPES[ext] || "application/octet-stream";

  // ETag based on file mtime + size for cache revalidation
  const etag = `"${stat.mtimeMs.toString(36)}-${stat.size.toString(36)}"`;
  const lastModified = stat.mtime.toUTCString();

  // If client has a matching ETag, return 304
  const ifNoneMatch = _request.headers.get("if-none-match");
  if (ifNoneMatch === etag) {
    return new NextResponse(null, { status: 304, headers: { ETag: etag } });
  }

  // Support Range requests for video seeking
  const rangeHeader = _request.headers.get("range");
  if (rangeHeader && ext === ".mp4") {
    const match = rangeHeader.match(/bytes=(\d+)-(\d*)/);
    if (match) {
      const start = parseInt(match[1], 10);
      const end = match[2] ? parseInt(match[2], 10) : stat.size - 1;
      const chunkSize = end - start + 1;
      const chunk = Buffer.alloc(chunkSize);
      const fd = fs.openSync(resolved, "r");
      fs.readSync(fd, chunk, 0, chunkSize, start);
      fs.closeSync(fd);
      return new NextResponse(chunk, {
        status: 206,
        headers: {
          "Content-Type": contentType,
          "Content-Range": `bytes ${start}-${end}/${stat.size}`,
          "Accept-Ranges": "bytes",
          "Content-Length": String(chunkSize),
          "Cache-Control": "public, no-cache",
          "ETag": etag,
          "Last-Modified": lastModified,
        },
      });
    }
  }

  const buffer = fs.readFileSync(resolved);

  return new NextResponse(buffer, {
    headers: {
      "Content-Type": contentType,
      "Accept-Ranges": "bytes",
      "Content-Length": String(stat.size),
      "Cache-Control": "public, no-cache",
      "ETag": etag,
      "Last-Modified": lastModified,
    },
  });
}
